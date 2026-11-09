#!/usr/bin/env python3
"""Safe, persistent JSON-line bridge to *real* OpenCADStudio GUI/MCP tools.
Only numeric CAD commands and controlled editing operations may cross SSH.
API credentials never appear on HangarVPS.
"""
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

BASE=Path("/home/ocstest/opencadstudio")
OUT=BASE/"results"/"sol-pilot"
sys.path.insert(0,str(BASE))
from mcp_eval import Client, META

ENGINE=BASE/"OpenCADStudio-v2026.45-linux-x86_64.AppImage"
SAFE_CMDS={
    "BOX","CYLINDER","CONE","SPHERE","WEDGE","TORUS",
    "LINE","PLINE","CIRCLE","ARC","RECTANG","POLYGON",
    "EXTRUDE","REVOLVE","REGION","UNION","SUBTRACT","INTERSECT",
    "MOVE","COPY","ROTATE3D","3DROTATE","3DMOVE","ROTATE",
    "FILLET","CHAMFER","FILLETEDGE","CHAMFEREDGE",
    "DIMLINEAR","DIMALIGNED","DIMRADIUS","DIMDIAMETER",
    "ZOOM","-VIEW",
}
NUMERIC_TEXT=re.compile(r"^[\x20-\x7e]{1,350}$")
HEX=re.compile(r"^(?:0[xX])?[0-9a-fA-F]{1,16}$")
SIMPLE_ID=re.compile(r"^[A-Z0-9_-]{1,32}$")
MAX_CALLS=100

def check_command(text):
    if not isinstance(text,str) or not NUMERIC_TEXT.fullmatch(text):
        raise ValueError("CAD command must be printable and <=350 ASCII characters")
    bits=text.split(maxsplit=1)
    name=bits[0].upper()
    if name not in SAFE_CMDS:
        raise ValueError("CAD command is not in safe allowlist: "+name[:40])
    rest=bits[1] if len(bits)>1 else ""
    if name in {"ZOOM","-VIEW"}:
        if not re.fullmatch(r"[0-9A-Za-z_+\-., ]{0,80}",rest):
            raise ValueError("unsafe viewport command")
    elif not re.fullmatch(r"[0-9eE+\-., ]{0,300}",rest):
        raise ValueError("geometry command accepts numeric arguments only")
    return text

def check_handles(x):
    if not isinstance(x,list) or len(x)>30 or not all(isinstance(h,str) and HEX.fullmatch(h) for h in x):
        raise ValueError("invalid entity handle list")
    return x

def check_request(obj):
    if not isinstance(obj,dict):
        raise ValueError("execute request must be object")
    op=obj.get("op")
    if op=="batch":
        if set(obj)-{"op","steps","request_id"}:
            raise ValueError("unexpected batch fields")
        steps=obj.get("steps")
        if not isinstance(steps,list) or not 1<=len(steps)<=12:
            raise ValueError("batch needs 1..12 steps")
        return {"op":"batch","steps":[check_request(s) for s in steps]}
    if op=="run":
        return {"op":"run","cmd":check_command(obj.get("cmd"))}
    if op=="start":
        command=str(obj.get("cmd","")).upper()
        if command not in {"SUBTRACT","UNION","INTERSECT","FILLETEDGE","CHAMFEREDGE"}:
            raise ValueError("interactive command not allowed")
        return {"op":"start","cmd":command}
    if op=="input":
        kind=obj.get("kind")
        if kind=="selection":return {"op":"input","kind":"selection","handles":check_handles(obj.get("handles"))}
        if kind=="enter":return {"op":"input","kind":"enter"}
        if kind=="point":
            value=obj.get("point")
            if not isinstance(value,list) or len(value) not in (2,3) or not all(isinstance(v,(int,float)) and abs(v)<5000 for v in value):
                raise ValueError("bad point")
            return {"op":"input","kind":"point","point":value}
        raise ValueError("only selection, point, enter input allowed")
    if op=="select":
        x={"op":"select","clear":bool(obj.get("clear",False))}
        if "handles" in obj:x["handles"]=check_handles(obj["handles"])
        return x
    if op in ("undo","redo"):
        return {"op":op}
    if op=="action":
        if obj.get("name") not in {"zoom_extents","view_home","command_escape"}:
            raise ValueError("action not allowed")
        return {"op":"action","name":obj["name"]}
    raise ValueError("operation not permitted: "+str(op)[:50])

def compact(obj,limit=6500):
    if not isinstance(obj,dict):return obj
    if obj.get("status") in ("waiting_input","completed") and "state" in obj:
        st=obj.get("state",{})
        return {"ok":obj.get("ok"),"status":obj.get("status"),
                "error":obj.get("error"),"code":obj.get("code"),
                "changes":obj.get("changes",[]),
                "result":obj.get("result",{}),
                "state":{"document_id":st.get("document_id"),
                         "revision":st.get("revision"),
                         "selection":st.get("selection"),
                         "command":st.get("command")}}
    text=json.dumps(obj,ensure_ascii=False,separators=(",",":"))
    if len(text)>limit:return {"ok":True,"truncated":True,"summary":text[:limit]}
    return obj

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    client=Client(ENGINE)
    try:
        sessions=client.tool("ocs_sessions",{"launch_if_none":True})["result"]
        if not sessions:raise RuntimeError("MCP returned no CAD sessions")
        session=sessions[0]["session_id"]
        while sessions[0].get("modal"):
            client.tool("ocs_execute",{"ocs_session_id":session,
                "request":{"op":"action","request_id":"init-"+uuid.uuid4().hex,"name":"close_modal"}})
            sessions=client.tool("ocs_sessions",{"launch_if_none":False})["result"]
        client.tool("ocs_new",{"ocs_session_id":session})
        print(json.dumps({"ok":True,"type":"ready","engine":"OpenCADStudio",
                          "version":"2026.45","mcp":True,"session_ready":True}),flush=True)
        calls=0
        for line in sys.stdin:
            calls+=1
            if calls>MAX_CALLS:
                print(json.dumps({"ok":False,"error":"session call budget exhausted"}),flush=True)
                break
            try:
                if len(line)>16384:raise ValueError("tool input too long")
                q=json.loads(line)
                name=q.get("tool")
                args=q.get("args",{})
                if not isinstance(args,dict):raise ValueError("tool args must be object")
                if name=="inspect":
                    result=client.tool("ocs_inspect",{"ocs_session_id":session})
                elif name=="commands":
                    command=args.get("name")
                    if not isinstance(command,str) or command.upper() not in SAFE_CMDS:
                        raise ValueError("command help only for allowlisted commands")
                    result=client.tool("ocs_commands",{"ocs_session_id":session,"name":command.upper()})
                elif name=="query":
                    clean={"ocs_session_id":session,"limit":30}
                    if args.get("type") is not None:
                        if args["type"] not in ["3DSolid","3D Solid","Line","Circle","Polyline","Arc","Dimension"]:
                            raise ValueError("unapproved query type")
                        clean["type"]=args["type"]
                    if "handles" in args:clean["handles"]=check_handles(args["handles"])
                    result=client.tool("ocs_query",clean)
                elif name=="measure":
                    clean={"ocs_session_id":session}
                    if "handles" in args:clean["handles"]=check_handles(args["handles"])
                    result=client.tool("ocs_measure",clean)
                elif name=="execute":
                    rq=check_request(args.get("request"))
                    rq["request_id"]="agent-"+uuid.uuid4().hex
                    result=client.tool("ocs_execute",{"ocs_session_id":session,"request":rq,
                                          "response_detail":"compact","wait_seconds":27})
                elif name=="audit":
                    result=client.tool("ocs_audit",{"ocs_session_id":session,
                                     "target_format":"dwg","target_version":"2018"})
                elif name=="finish":
                    solids=client.tool("ocs_query",{"ocs_session_id":session,"type":"3DSolid","limit":30})
                    if solids.get("count")!=1:
                        raise ValueError("finish requires exactly one 3D Solid (got "+str(solids.get("count"))+")")
                    handle=solids["entities"][0]["handle"]
                    measure=client.tool("ocs_measure",{"ocs_session_id":session,"handles":[handle]})
                    entry=measure.get("measurements",[{}])[0]
                    mesh=entry.get("mesh",{})
                    if not isinstance(mesh.get("volume"),(float,int)) or mesh["volume"]<=100:
                        raise ValueError("3D volume failed verification")
                    audit=client.tool("ocs_audit",{"ocs_session_id":session,
                                            "target_format":"dwg","target_version":"2018"})
                    if audit.get("status")!="passed" or audit.get("summary",{}).get("errors")!=0:
                        raise ValueError("audit failed")
                    ident="mcp-agent-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-"+uuid.uuid4().hex[:8]
                    dwg=OUT/(ident+".dwg")
                    pdf=OUT/(ident+".pdf")
                    png=OUT/(ident+".png")
                    saved=client.tool("ocs_save_verified",{"ocs_session_id":session,"path":str(dwg),
                                      "target_format":"dwg","target_version":"2018","overwrite":False})
                    if not saved.get("result",saved).get("verified"):
                        raise ValueError("DWG roundtrip verification failed")
                    for cmd in ("-VIEW _SWISO","ZOOM E","ZOOM 0.75X"):
                        client.tool("ocs_run",{"ocs_session_id":session,"command":cmd})
                    image=client.rpc("tools/call",{"name":"ocs_capture",
                         "arguments":{"ocs_session_id":session,"scope":"viewport","max_dimension":1200},
                         "_meta":META})
                    bitmap=next((p for p in image.get("content",[]) if p.get("type")=="image"),None)
                    if bitmap:
                        png.write_bytes(base64.b64decode(bitmap["data"],validate=True))
                    state=client.tool("ocs_inspect",{"ocs_session_id":session})
                    # Plot is optional and may not support complex 3D in some versions.
                    pdf_error=None
                    try:
                        plotted=client.tool("ocs_execute",{"ocs_session_id":session,
                            "request":{"op":"plot","path":str(pdf),"layout":"Model","fit":True,
                            "center":True,"request_id":"plot-"+uuid.uuid4().hex}})
                    except Exception as e:pdf_error=str(e)[:130]
                    result={"ok":True,"finished":True,
                            "dwg":str(dwg),"png":str(png) if png.exists() else None,
                            "pdf":str(pdf) if pdf.exists() else None,
                            "plot_error":pdf_error,"volume_mm3":mesh["volume"],
                            "bounds_mm":entry.get("bounds"),"triangles":mesh.get("triangles"),
                            "solids":solids.get("count"),"audit":audit.get("summary")}
                    (OUT/(ident+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2))
                else:raise ValueError("unknown tool "+str(name)[:90])
                print(json.dumps({"ok":True,"tool":name,"data":compact(result)},ensure_ascii=False),flush=True)
            except Exception as e:
                print(json.dumps({"ok":False,"tool":q.get("tool") if isinstance(q,dict) else None,
                                  "error":type(e).__name__+": "+str(e)[:550]},ensure_ascii=False),flush=True)
    finally:
        client.close()

if __name__=="__main__":
    main()