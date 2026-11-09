#!/usr/bin/env python3
"""Model-directed OpenCADStudio GUI/MCP agent, OpenAI API only on BruceVPS.
Safe bridge on Hangar receives ONLY tool names + sanitized geometry commands.
Run from an approved secret-aware local context with OPENAI_API_KEY set.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

MODEL="gpt-6.1-sol"
API="https://api.openai.com/v1/responses"
MAX_ROUNDS=30
MAX_TOOL_CALLS=48
MAX_TOTAL_TOKENS=40000
MAX_INPUT_CHARS=3500
SESSION_COMMAND=[
 "/usr/bin/ssh","-F","/dev/null","-T",
 "-i","/root/.ssh/hangarvps_ed25519",
 "-o","BatchMode=yes",
 "-o","StrictHostKeyChecking=yes",
 "-o","HostKeyAlias=64.235.37.125",
 "-o","UserKnownHostsFile=/root/.ssh/known_hosts",
 "-o","ConnectTimeout=10",
 "-o","ForwardAgent=no","-o","ForwardX11=no","-o","ClearAllForwardings=yes",
 "root@100.79.53.90",
 "runuser -u ocstest -- /usr/bin/xvfb-run -a -s '-screen 0 1440x960x24' /usr/bin/python3 /home/ocstest/opencadstudio/agent_mcp_bridge.py"
]
TOOLS=[
 {"type":"function","name":"cad_inspect","description":"Read the live OpenCADStudio GUI editor state. Call at the beginning and after errors.",
  "parameters":{"type":"object","properties":{},"required":[],"additionalProperties":False}},
 {"type":"function","name":"cad_help","description":"Ask OpenCADStudio MCP for the syntax and prompt-manifest of a CAD command.",
  "parameters":{"type":"object","properties":{"name":{"type":"string","description":"e.g. BOX, CYLINDER, UNION or SUBTRACT"}},"required":["name"],"additionalProperties":False}},
 {"type":"function","name":"cad_edit","description":"Execute actual native CAD commands through MCP. Each call persists state. Efficient batch example: {'request':{'op':'batch','steps':[{'op':'run','cmd':'BOX 0,0,0 100,70,0 10'}, ...]}}. To UNION: query handles; batch select clear, start UNION, input selection handles, input enter. To SUBTRACT: select clear, start SUBTRACT, input selection BASE, input enter, input selection CUTTERS, input enter. Only safe CAD commands are permitted.",
  "parameters":{"type":"object","properties":{"request":{"type":"object","description":"A single OpenCADStudio execute operation: op=run/start/input/select/undo/redo or op=batch with steps. Request must include exact command syntax.","additionalProperties":True}},"required":["request"],"additionalProperties":False}},
 {"type":"function","name":"cad_query","description":"List actual entities and handles in the active OpenCADStudio drawing. For all solids use type='3DSolid'.",
  "parameters":{"type":"object","properties":{"type":{"type":"string","description":"Entity type: 3DSolid, Line, Circle, Polyline, Arc or Dimension"}},"required":["type"],"additionalProperties":False}},
 {"type":"function","name":"cad_measure","description":"Measure one or more exact CAD entity handles; returns bounds and geometric mesh volume. Check after boolean operations.",
  "parameters":{"type":"object","properties":{"handles":{"type":"array","items":{"type":"string"}}},"required":["handles"],"additionalProperties":False}},
 {"type":"function","name":"cad_audit","description":"Run DWG 2018 compatibility and geometry audit; require zero errors.",
  "parameters":{"type":"object","properties":{},"required":[],"additionalProperties":False}},
 {"type":"function","name":"cad_finish","description":"When exactly one positive-volume 3D Solid remains and audit passes, save verified DWG, PDF and isometric screenshot. No path or other sensitive options can be provided.",
  "parameters":{"type":"object","properties":{},"required":[],"additionalProperties":False}}
]
INSTRUCTIONS=(
 "Ты самостоятельный исполнитель САПР с настоящим управлением OpenCADStudio v2026.45 через MCP, "
 "а не генератор JSON-плана. Перед тобой чистый чертёж. "
 "Сначала вызови cad_inspect и при необходимости cad_help. "
 "Сам выбирай последовательность реальных CAD-команд BOX, CYLINDER, UNION, SUBTRACT и др. "
 "В cad_edit обёртка request содержит op='run', cmd='BOX ...' "
 "или op='batch', steps=[{op:'run',cmd:'...'}, ...]. В одном batch <=12 шагов. "
 "Команды BOX: 'BOX x1,y1,z1 x2,y2,z1 HEIGHT', "
 "CYLINDER: 'CYLINDER x,y,z RADIUS HEIGHT'. "
 "Запроси cad_query с type='3DSolid', чтобы получить реальные handles, "
 "затем делай UNION и SUBTRACT с интерактивным выбором. "
 "Критически важно: перед UNION/SUBTRACT выполняй select(clear=true), иначе выбор переключит выделение. "
 "Для UNION используй один cad_edit batch из steps: "
 "{'op':'select','clear':true}, {'op':'start','cmd':'UNION'}, "
 "{'op':'input','kind':'selection','handles':['...']}, {'op':'input','kind':'enter'}. "
 "Для SUBTRACT аналогично, но два этапа выбора — сперва BASE, ENTER, затем CUTTERS, ENTER. "
 "Числа в миллиметрах. В CYLINDER задаётся РАДИУС, не диаметр. "
 "Отверстия делай как полное 3D-вычитание, цилиндры выступают минимум на 1 мм с обеих сторон нужной стенки. "
 "Не считай текстовый ответ успешным выполнением! После создания запроси cad_query, cad_measure, cad_audit, "
 "затем cad_finish для настоящего DWG/PDF/PNG. Если инструмент ответил ошибкой, изучи и исправь, "
 "возможно через cad_inspect или cad_edit undo. Не выполняй опасные команды, никаких файловых/сетевых операций. "
 "Не утверждай, что поддерживаются фаски/кривые, пока не проверено. "
 "Если задание невыполнимо или бюджет действий исчерпан, объясни конкретный блокер. "
 "Всегда отвечай на русском."
)

class Bridge:
 def __init__(self):
  clean={"PATH":"/usr/bin:/bin","HOME":"/root","LANG":"C","LC_ALL":"C"}
  self.p=subprocess.Popen(SESSION_COMMAND,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,text=True,bufsize=1,env=clean)
  line=self.p.stdout.readline()
  if not line:
   raise RuntimeError("remote MCP bridge did not start")
  response=json.loads(line)
  if not response.get("ok") or not response.get("mcp"):
   raise RuntimeError("unexpected MCP bridge reply")

 def call(self,tool,args=None):
  request={"tool":tool,"args":args or {}}
  raw=json.dumps(request,ensure_ascii=False)
  if len(raw)>16000:
   return {"ok":False,"error":"request too large"}
  self.p.stdin.write(raw+"\n")
  self.p.stdin.flush()
  line=self.p.stdout.readline()
  if not line:
   return {"ok":False,"error":"remote MCP bridge closed unexpectedly"}
  return json.loads(line)

 def close(self):
  try:
   if self.p.stdin:self.p.stdin.close()
   self.p.wait(timeout=15)
  except Exception:
   self.p.terminate()
   try:self.p.wait(timeout=3)
   except Exception:self.p.kill()

def call_openai(payload,secret):
 req=urllib.request.Request(API,data=json.dumps(payload,ensure_ascii=False).encode(),
      method="POST",headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=85) as r:
   return json.load(r)
 except urllib.error.HTTPError as e:
  raise RuntimeError("OpenAI response HTTP "+str(e.code))
 except Exception as e:
  raise RuntimeError("OpenAI transport failure: "+type(e).__name__)

def perform_tool(bridge,name,args):
 if name=="cad_inspect":return bridge.call("inspect")
 if name=="cad_help":return bridge.call("commands",{"name":args.get("name")})
 if name=="cad_edit":return bridge.call("execute",{"request":args.get("request")})
 if name=="cad_query":return bridge.call("query",{"type":args.get("type")})
 if name=="cad_measure":return bridge.call("measure",{"handles":args.get("handles")})
 if name=="cad_audit":return bridge.call("audit")
 if name=="cad_finish":return bridge.call("finish")
 return {"ok":False,"error":"model attempted unknown function"}

def main():
 if len(sys.argv)!=2 or not (0<len(sys.argv[1])<=MAX_INPUT_CHARS):
  raise ValueError("Expected one detailed engineering assignment (<=3500 chars)")
 task=sys.argv[1]
 key=os.environ.get("OPENAI_API_KEY")
 if not key:raise RuntimeError("Secret-aware OpenAI key is required, only locally on BruceVPS")
 start=time.monotonic()
 bridge=Bridge()
 events=[]
 result=None
 failure=None
 usage=[]
 try:
  r=call_openai({"model":MODEL,"store":True,"instructions":INSTRUCTIONS,
       "input":task,"tools":TOOLS,"max_output_tokens":1800},key)
  for turn in range(MAX_ROUNDS):
   usage.append(r.get("usage",{}))
   if sum(x.get("total_tokens",0) for x in usage)>MAX_TOTAL_TOKENS:
    failure="Model token budget exhausted"
    break
   if r.get("status") not in ("completed",):
    failure="OpenAI response status: "+str(r.get("status"))
    break
   calls=[x for x in r.get("output",[]) if x.get("type")=="function_call"]
   if not calls:
    content=" ".join(c.get("text","") for x in r.get("output",[])
                    for c in x.get("content",[]) if c.get("type")=="output_text")
    failure="Model ended without confirmed drawing: "+content[:500]
    break
   outputs=[]
   for fc in calls:
    if len(events)>=MAX_TOOL_CALLS or time.monotonic()-start>560:
     failure="MCP tool/time budget exhausted"
     break
    try:
     args=json.loads(fc.get("arguments","{}"))
     if not isinstance(args,dict):args={}
     ans=perform_tool(bridge,fc.get("name"),args)
    except Exception as exc:
     ans={"ok":False,"error":type(exc).__name__+": "+str(exc)[:240]}
    event={"round":turn+1,"name":fc.get("name"),"ok":bool(ans.get("ok")),
           "error":ans.get("error") if not ans.get("ok") else None}
    events.append(event)
    if fc.get("name")=="cad_finish" and ans.get("ok") and ans.get("data",{}).get("finished"):
     result=ans["data"]
    if fc.get("name")=="cad_edit" and ans.get("ok"):
     req=args.get("request",{})
     steps=req.get("steps",[]) if req.get("op")=="batch" else [req]
     event["cad_actions"]=[str(x.get("cmd") or x.get("op"))[:180] for x in steps if isinstance(x,dict)][:12]
    outputs.append({"type":"function_call_output","call_id":fc["call_id"],
                    "output":json.dumps(ans,ensure_ascii=False)[:13000]})
    if result:break
   if failure or result:
    break
   if not outputs:
    failure="No CAD tool replies"
    break
   r=call_openai({"model":MODEL,"store":True,"instructions":INSTRUCTIONS,
          "previous_response_id":r["id"],"input":outputs,
          "tools":TOOLS,"max_output_tokens":1800},key)
  else:failure="Maximum model rounds exceeded"
 finally:
  bridge.close()
 report={"ok":bool(result),"model":MODEL,"result":result,"failure":failure,
         "steps":events,"mcp_tool_calls":len(events),
         "api_rounds":len(usage),"usage":usage,
         "duration_sec":round(time.monotonic()-start,1),
         "credentials":"OpenAI key stayed on BruceVPS. Hangar received only MCP tool operations."}
 log_dir=Path("/opt/opencadstudio-pilot/reports")
 log_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
 file=log_dir/("mcp-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-"+uuid.uuid4().hex[:6]+".json")
 file.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 os.chmod(file,0o600)
 print(json.dumps({"ok":report["ok"],"model":MODEL,"result":result,
       "failure":failure,"mcp_tool_calls":len(events),"api_rounds":len(usage),
       "duration_sec":report["duration_sec"],"report_path":str(file)},ensure_ascii=False))
 if not result:sys.exit(2)


def preflight():
 bridge=Bridge()
 try:
  checks={}
  for tool,args in (("inspect",{}),("commands",{"name":"BOX"}),("query",{"type":"3DSolid"})):
   resp=bridge.call(tool,args)
   checks[tool] = bool(resp.get("ok"))
  print(json.dumps({"ok":all(checks.values()),"mode":"preflight-no-api-no-secrets",
                    "transport":"BruceVPS SSH to HangarVPS","mcp":checks},ensure_ascii=False))
 finally:bridge.close()

if __name__=="__main__":
 if sys.argv[1:]==["--preflight"]:
  try:preflight()
  except Exception as e:
   print(json.dumps({"ok":False,"mode":"preflight-no-api","error":str(e)[:220]}))
   sys.exit(2)
  sys.exit(0)
 try:main()
 except Exception as e:
  print(json.dumps({"ok":False,"error":type(e).__name__+": "+str(e)[:350]},ensure_ascii=False))
  sys.exit(2)