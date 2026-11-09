#!/usr/bin/env python3
"""GPT-6.1 Sol writes a bounded CAD 3D plan; Hangar executes with zero API credentials."""
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

MODEL="gpt-6.1-sol"
ENDPOINT="https://api.openai.com/v1/responses"
SYSTEM=(
 "Ты ИИ-инженер для настоящего 3D CAD, а не художник. Выдай исключительно JSON, "
 "без Markdown и пояснений. Схема строго: "
 '{"units":"mm","primitives":[{"id":"unique","shape":"box","origin":[x,y,z],"size":[dx,dy,dz]},'
 '{"id":"unique","shape":"cylinder_z","center":[x,y,z],"radius":r,"height":h}],'
 '"operations":[{"op":"union","inputs":["id1","id2"],"out":"newid"},'
 '{"op":"subtract","base":"newid","cutters":["id3"],"out":"finalid"}],"final":"finalid"}. '
 "Это иллюстрация схемы, а не готовый ответ. "
 "Для каждого примитива используй только его подходящие поля, без дополнительных. "
 "Все длины мм, не перепутай радиус и диаметр. "
 "Габаритные прямоугольники задаются origin и size; у цилиндров только вертикальная ось Z. "
 "Переходи от отдельных тел к одному через union, затем вычитай цилиндры через subtract. "
 "Под сквозное отверстие создавай цилиндр, проходящий за обе наружные грани минимум на 1 мм. "
 "Никаких одиночных окружностей без реального вычитания. "
 "В primitives 2..16 позиций, в operations 1..5 операций, итоговое одно тело. "
 "Не выдумывай недостающие размеры. Если запрос несовместим с такими примитивами, "
 'ответь {"error":"unsupported"} вместо фиктивного чертежа.'
)
SSH=[
 "/usr/bin/ssh","-F","/dev/null","-T",
 "-i","/root/.ssh/hangarvps_ed25519",
 "-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
 "-o","HostKeyAlias=64.235.37.125",
 "-o","UserKnownHostsFile=/root/.ssh/known_hosts",
 "-o","ConnectTimeout=9","-o","ClearAllForwardings=yes",
 "-o","ForwardAgent=no","-o","ForwardX11=no",
 "root@100.79.53.90",
 "runuser -u ocstest -- /usr/bin/python3 /home/ocstest/opencadstudio/cad_build_3d.py"
]
def end(message,code=2):
 print(json.dumps({"ok":False,"error":str(message)[:230]},ensure_ascii=False))
 sys.exit(code)

def independently_verify_plan(plan):
 if not isinstance(plan,dict) or set(plan)!={"units","primitives","operations","final"}:
  raise ValueError("incomplete structured design")
 if plan["units"]!="mm":raise ValueError("wrong units")
 parts=plan["primitives"]
 if not isinstance(parts,list):raise ValueError("missing primitives")
 boxes=[v for v in parts if v.get("shape")=="box"]
 cutters=[v for v in parts if v.get("shape")=="cylinder_z"]
 if len(boxes)!=2 or len(cutters)!=5:
  raise ValueError("expected two bodies and five actual bore cutters")
 def eq(a,b):
  return abs(float(a)-float(b))<.001
 def vec(a,b):
  return len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b))
 target_b=[([0,0,0],[180,130,12]),([30,25,12],[120,80,28])]
 for pos, size in target_b:
  if not any(vec(b.get("origin",[]),pos) and vec(b.get("size",[]),size) for b in boxes):
   raise ValueError("box geometry differs from assignment")
 holes=[(90,65,15,40),(18,18,5,12),(162,18,5,12),(162,112,5,12),(18,112,5,12)]
 for x,y,r,top in holes:
  present=False
  for b in cutters:
   c=b.get("center",[])
   if len(c)!=3:continue
   if eq(c[0],x) and eq(c[1],y) and eq(b.get("radius",-1),r):
    low=float(c[2]);upper=low+float(b.get("height",0))
    if low<=-1 and upper>=top+1:present=True
  if not present:raise ValueError("missing or insufficiently deep real bore")
 operations=plan["operations"]
 if len(operations)!=2 or operations[0].get("op")!="union" or operations[1].get("op")!="subtract":
  raise ValueError("require union followed by subtraction")
 if len(operations[1].get("cutters",[]))!=5:
  raise ValueError("not all holes subtracted")

def main():
 if len(sys.argv)!=2 or len(sys.argv[1])>2500:
  end("provide exactly one Russian engineering assignment")
 key=os.environ.get("OPENAI_API_KEY")
 if not key:end("OPENAI_API_KEY was not injected from Bruce Secrets")
 task=sys.argv[1]
 messages=[{"role":"system","content":SYSTEM},{"role":"user","content":task}]
 usage_all=[]
 plan=None
 for attempt in range(3):
  payload={"model":MODEL,"input":messages,"max_output_tokens":2200}
  req=urllib.request.Request(ENDPOINT,data=json.dumps(payload).encode(),
       headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},
       method="POST")
  try:
   with urllib.request.urlopen(req,timeout=78) as r:
    response=json.load(r)
  except urllib.error.HTTPError as err:
   end("OpenAI API returned HTTP "+str(err.code))
  except Exception as exc:
   end("OpenAI transport error "+type(exc).__name__)
  usage_all.append(response.get("usage",{}))
  if response.get("status")!="completed":
   end("OpenAI did not finish")
  body="".join(c.get("text","") for o in response.get("output",[])
        for c in o.get("content",[]) if c.get("type")=="output_text")
  try:
   plan=json.loads(body)
   independently_verify_plan(plan)
   break
  except Exception as exc:
   if attempt==2:
    end("model failed validation after 3 attempts: "+type(exc).__name__+": "+str(exc))
   messages.extend([
     {"role":"assistant","content":body},
     {"role":"user","content":
       "Проверяющая система отклонила предыдущий план: "+str(exc)+". "
       "Исправь только фактические ошибки, сохрани исходные размеры и полную "
       "объёмную геометрию. Все пять режущих цилиндров должны пересекать "
       "всю свою толщину и выступать не менее 1 мм с ОБЕИХ сторон: "
       "центральное отверстие — через Z=0..40; крепёжные — через Z=0..12. "
       "Не заменяй отверстия окружностями. Верни исправленный чистый JSON."
     }
   ])
 clean_env={"HOME":"/root","PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C"}
 try:
  ret=subprocess.run(SSH,input=json.dumps(plan,ensure_ascii=False,separators=(",",":")).encode(),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=115,env=clean_env)
 except subprocess.TimeoutExpired:
  end("remote CAD operation timed out")
 if ret.returncode:
  try: e=json.loads(ret.stdout.decode()).get("error","")
  except Exception:e=""
  end("CAD worker failure, exit="+str(ret.returncode)+" "+str(e))
 try: cad=json.loads(ret.stdout.decode())
 except Exception:end("CAD worker invalid JSON")
 if not cad.get("ok") or not cad.get("one_brep_solid") or not cad.get("is_3d"):
  end("CAD worker did not prove one 3D solid")
 expected=180*130*12+120*80*28-math.pi*15**2*40-4*math.pi*5**2*12
 obtained=cad["volume_mm3"]
 bounds=cad["bounds_mm"]
 if not math.isfinite(obtained) or abs(obtained-expected)/expected>.003:
  end("independent volume check failed")
 if any(abs(float(a)-float(b))>.01 for a,b in
        zip(bounds["min"]+bounds["max"],[0,0,0,180,130,40])):
  end("independent 3D bounding box check failed")
 if cad.get("audit",{}).get("errors") or cad.get("audit",{}).get("warnings"):
  end("CAD audit failed")
 print(json.dumps({
  "ok":True,"model":MODEL,"autonomously_planned_primitives":len(plan["primitives"]),
  "booleans":plan["operations"],
  "model_plan":plan,
  "body_verified":cad["one_brep_solid"],
  "volume_mm3":obtained,"analytic_expected_mm3":expected,
  "relative_error_pct":100*abs(obtained-expected)/expected,
  "bounds_mm":bounds,
  "mesh_triangles":cad.get("mesh_triangles"),
  "audit":cad["audit"],"paths":cad["paths"],"bytes":cad["bytes"],
  "api_usage":usage_all,"planning_attempts":len(usage_all),
  "security":"OpenAI credential remained on Bruce. Hangar received numeric bounded plan only.",
 },ensure_ascii=False))

if __name__=="__main__":
 try:main()
 except Exception as exc:end(type(exc).__name__+": "+str(exc))