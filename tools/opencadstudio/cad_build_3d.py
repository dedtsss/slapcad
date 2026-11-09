#!/usr/bin/env python3
"""Execute an explicitly bounded 3D CAD solid plan; never accepts shell code."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path("/home/ocstest/opencadstudio")
ENGINE = ROOT / "OpenCADStudio-v2026.45-linux-x86_64.AppImage"
OUT = ROOT / "results" / "sol-pilot"
ID = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
os.umask(0o077)

def die(e):
    print(json.dumps({"ok":False,"error":str(e)[:300]},ensure_ascii=False),flush=True)
    sys.exit(2)

def number(v, lo=-1000, hi=1500):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
        raise ValueError("invalid number")
    f=float(v)
    if not lo <= f <= hi:
        raise ValueError("coordinate outside limits")
    return f

def vec(v, n, lo=-1000, hi=1500):
    if not isinstance(v,list) or len(v)!=n:
        raise ValueError("vector requires "+str(n)+" coordinates")
    return [number(x,lo,hi) for x in v]

def fmt(x):
    return format(x,'.8f').rstrip('0').rstrip('.') if x != 0 else '0'

def valid_id(s):
    if not isinstance(s,str) or not ID.fullmatch(s):
        raise ValueError("invalid identifier")
    return s

def request_plan():
    raw=sys.stdin.buffer.read(16385)
    if len(raw)>16384:
        raise ValueError("input too large")
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)!={"units","primitives","operations","final"}:
        raise ValueError("plan keys invalid")
    if data["units"]!="mm":
        raise ValueError("millimeter units mandatory")
    ps=data["primitives"]
    ops=data["operations"]
    if not isinstance(ps,list) or not 2 <= len(ps)<=16:
        raise ValueError("expected 2..16 primitives")
    if not isinstance(ops,list) or not 1 <= len(ops)<=5:
        raise ValueError("expected 1..5 boolean operations")
    seen=set()
    commands=[]
    for item in ps:
        if not isinstance(item,dict) or "id" not in item or "shape" not in item:
            raise ValueError("bad primitive")
        ident=valid_id(item["id"])
        if ident in seen:
            raise ValueError("duplicate primitive")
        seen.add(ident)
        shape=item["shape"]
        if shape=="box":
            if set(item)!={"id","shape","origin","size"}:
                raise ValueError("box keys invalid")
            x,y,z=vec(item["origin"],3)
            dx,dy,dz=vec(item["size"],3,.1,800)
            if any(x>1500 for x in (x+dx,y+dy,z+dz)):
                raise ValueError("box exceeds limits")
            cmd=f"BOX {fmt(x)},{fmt(y)},{fmt(z)} {fmt(x+dx)},{fmt(y+dy)},{fmt(z)} {fmt(dz)}"
        elif shape=="cylinder_z":
            if set(item)!={"id","shape","center","radius","height"}:
                raise ValueError("cylinder keys invalid")
            x,y,z=vec(item["center"],3)
            radius=number(item["radius"],.2,300)
            height=number(item["height"],.2,800)
            cmd=f"CYLINDER {fmt(x)},{fmt(y)},{fmt(z)} {fmt(radius)} {fmt(height)}"
        else:
            raise ValueError("unsupported primitive "+str(shape)[:50])
        commands.append((ident,cmd))
    live=set(seen)
    for op in ops:
        if not isinstance(op,dict):
            raise ValueError("bad boolean")
        kind=op.get("op")
        target=valid_id(op.get("out"))
        if target in seen or target in live:
            raise ValueError("duplicate output")
        if kind=="union":
            if set(op)!={"op","inputs","out"}:
                raise ValueError("union keys invalid")
            refs=op["inputs"]
            if not isinstance(refs,list) or not 2<=len(refs)<=12 or len(refs)!=len(set(refs)):
                raise ValueError("union needs distinct operands")
            if any(x not in live for x in refs):
                raise ValueError("unknown union operands")
        elif kind=="subtract":
            if set(op)!={"op","base","cutters","out"}:
                raise ValueError("subtract keys invalid")
            refs=[op["base"]]+op["cutters"]
            if not isinstance(op["cutters"],list) or not 1<=len(op["cutters"])<=12:
                raise ValueError("subtract needs cutters")
            if len(refs)!=len(set(refs)) or any(x not in live for x in refs):
                raise ValueError("unknown subtract operands")
        else:
            raise ValueError("unsupported boolean")
        for x in refs:
            live.remove(x)
        live.add(target)
        seen.add(target)
    if valid_id(data["final"]) not in live or len(live)!=1:
        raise ValueError("plan must finish as exactly one body")
    return data,commands

def run(plan, commands):
    OUT.mkdir(parents=True, exist_ok=True, mode=0o750)
    token="sol-3d-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-"+uuid.uuid4().hex[:8]
    dwg=OUT/(token+".dwg")
    dxf=OUT/(token+".dxf")
    pdf=OUT/(token+".pdf")
    report=OUT/(token+".json")
    stderr=OUT/(token+".stderr.log")
    events=[]
    with stderr.open("w") as err:
        p=subprocess.Popen([str(ENGINE),"--serve"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                           stderr=err, text=True,bufsize=1,cwd=str(ROOT))
        counter=0
        def ask(obj):
            nonlocal counter
            counter+=1
            if obj["op"] in ("start","input","measure","audit","save_verified","plot","select"):
                obj.setdefault("protocol",1)
                obj.setdefault("request_id",token+"-"+str(counter))
                obj.setdefault("document_id",1)
            p.stdin.write(json.dumps(obj,separators=(",",":"))+"\n")
            p.stdin.flush()
            line=p.stdout.readline()
            if not line:
                raise RuntimeError("CAD engine returned EOF")
            resp=json.loads(line)
            if not resp.get("ok") or resp.get("status")=="failed":
                raise RuntimeError("CAD "+obj["op"]+" error "+str(resp.get("code",resp.get("error")))[:160])
            return resp
        def handles():
            r=ask({"op":"query","type":"3DSolid"})
            return [e["handle"] for e in r.get("entities",[])]
        def select(handles_to_pick):
            r=ask({"op":"input","kind":"selection","handles":handles_to_pick})
            if r.get("status")!="waiting_input":
                raise RuntimeError("selection did not remain active")
        try:
            b=json.loads(p.stdout.readline())
            if not b.get("ready") or b.get("version")!="2026.45":
                raise RuntimeError("unexpected CAD engine version or state")
            ask({"op":"new"})
            names={}
            for label,cmd in commands:
                before=set(handles())
                result=ask({"op":"run","cmd":cmd})
                after=set(handles())
                fresh=after-before
                if result.get("status")!="completed" or result.get("unconsumed") or len(fresh)!=1:
                    raise RuntimeError("primitive did not create exactly one solid")
                names[label]=next(iter(fresh))
                events.append({"type":"primitive","id":label,"command":cmd,"handle":names[label]})
            doc=1
            for op in plan["operations"]:
                typ=op["op"]
                before=set(handles())
                ask({"op":"select","clear":True})
                result=ask({"op":"start","cmd":typ.upper()})
                if result.get("status")!="waiting_input":
                    raise RuntimeError("boolean failed to start")
                if typ=="union":
                    inputs=op["inputs"]
                    select([names[x] for x in inputs])
                    result=ask({"op":"input","kind":"enter"})
                else:
                    inputs=[op["base"]]+op["cutters"]
                    select([names[op["base"]]])
                    second=ask({"op":"input","kind":"enter"})
                    if second.get("status")!="waiting_input":
                        raise RuntimeError("subtract base selection refused")
                    select([names[x] for x in op["cutters"]])
                    result=ask({"op":"input","kind":"enter"})
                if result.get("status")!="completed":
                    raise RuntimeError("boolean incomplete")
                after=set(handles())
                old={names[x] for x in inputs}
                if len(after)!=(len(before)-len(inputs)+1) or (old & after and typ=="union"):
                    raise RuntimeError("unexpected boolean solid count")
                if typ=="union":
                    final=after-before
                    if len(final)!=1:
                        raise RuntimeError("union did not create new solid")
                    final_handle=next(iter(final))
                else:
                    base=names[op["base"]]
                    if base in after:
                        final_handle=base
                    else:
                        final=after-before
                        if len(final)!=1:
                            raise RuntimeError("subtract did not preserve or replace base")
                        final_handle=next(iter(final))
                    if any(names[x] in after for x in op["cutters"]):
                        raise RuntimeError("cutting solids remain")
                for x in inputs:
                    del names[x]
                names[op["out"]]=final_handle
                events.append({"type":typ,"out":op["out"],"handle":final_handle,
                               "consumed":inputs,
                               "changes":result.get("changes",[])})
            if set(names)!={plan["final"]}:
                raise RuntimeError("more than one final named solid")
            final_handle=names[plan["final"]]
            if handles()!=[final_handle]:
                raise RuntimeError("final handle mismatch")
            ms=ask({"op":"measure","handles":[final_handle]})
            measure=ms.get("measurements",[])
            if len(measure)!=1 or not measure[0].get("mesh"):
                raise RuntimeError("no measurable solid")
            mesh=measure[0]["mesh"]
            volume=mesh.get("volume")
            bounds=measure[0].get("bounds")
            if not isinstance(volume,(int,float)) or volume<=0 or not bounds:
                raise RuntimeError("invalid final volume")
            audit=ask({"op":"audit","target_format":"dwg","target_version":"2018"})
            if audit.get("status")!="passed" or audit.get("summary",{}).get("errors")!=0:
                raise RuntimeError("DWG audit failed")
            st=ask({"protocol":1,"op":"state"})
            state=st.get("state",st)
            saved=ask({"op":"save_verified","path":str(dwg),
                       "document_id":state["document_id"],"revision":state["revision"],
                       "target_format":"dwg","target_version":"2018","overwrite":False})
            if not saved.get("result",{}).get("verified"):
                raise RuntimeError("DWG verification failed")
            plotted=ask({"op":"plot","path":str(pdf),"document_id":state["document_id"],
                         "layout":"Model","fit":True,"center":True})
        finally:
            p.stdin.close()
            p.terminate()
            try: p.wait(timeout=4)
            except subprocess.TimeoutExpired: p.kill()
    conv=subprocess.run([str(ENGINE),"--export",str(dwg),str(dxf)],
                        capture_output=True,text=True,timeout=85,cwd=str(ROOT))
    if conv.returncode:
        raise RuntimeError("DXF conversion rc="+str(conv.returncode))
    sizes={k:Path(v).stat().st_size if Path(v).is_file() else 0
           for k,v in {"dwg":dwg,"dxf":dxf,"pdf":pdf}.items()}
    if min(sizes.values())<=0:
        raise RuntimeError("missing CAD export file")
    final={
        "ok":True,"version":"2026.45","is_3d":True,
        "one_brep_solid":True,"plan":plan,"events":events,
        "final_handle":final_handle,"volume_mm3":volume,"bounds_mm":bounds,
        "mesh_triangles":mesh.get("triangles"),"audit":audit.get("summary"),
        "paths":{"dwg":str(dwg),"dxf":str(dxf),"pdf":str(pdf)},
        "bytes":sizes,
        "limitations":"Volume estimated from triangulation; independent reopen of DXF not yet verified."
    }
    report.write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(final,ensure_ascii=False))

if __name__=="__main__":
    try:
        plan,commands=request_plan()
        run(plan,commands)
    except Exception as e:
        die(type(e).__name__+": "+str(e))