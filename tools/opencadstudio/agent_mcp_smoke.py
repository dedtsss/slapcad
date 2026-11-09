#!/usr/bin/env python3
"""Integration test: JSON bridge -> native MCP -> actual 3D geometry -> verify DWG."""
import json
import subprocess
import sys
import time

BRIDGE="/home/ocstest/opencadstudio/agent_mcp_bridge.py"
p=subprocess.Popen(["/usr/bin/python3",BRIDGE],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
n=0
def ask(tool,**args):
 global n
 n+=1
 p.stdin.write(json.dumps({"tool":tool,"args":args})+"\n")
 p.stdin.flush()
 line=p.stdout.readline()
 if not line:raise RuntimeError("MCP bridge ended")
 r=json.loads(line)
 if not r.get("ok"):
  raise RuntimeError("MCP "+tool+" error: "+str(r.get("error")))
 d=r["data"]
 print("CALL",n,tool,"STATUS",d.get("status","ok"),"CHANGES",len(d.get("changes",[])),
       "SOLIDS",d.get("count",""),"PROMPT",d.get("state",{}).get("command",{}).get("prompt","")[:65] if isinstance(d.get("state",{}).get("command"),dict) else "",flush=True)
 return d

def execute(**q):
 return ask("execute",request=q)
def handles():
 r=ask("query",type="3DSolid")
 return [x["handle"] for x in r["entities"]]

try:
 banner=json.loads(p.stdout.readline())
 print("BANNER",banner,flush=True)
 assert banner.get("mcp") and banner.get("ok")
 ask("commands",name="BOX")
 ask("inspect")
 # This test is not an LLM. It verifies the real tool roundtrip for the future LLM.
 r=execute(op="run",cmd="BOX 0,0,0 160,110,0 10")
 assert r.get("status")=="completed"
 r=execute(op="run",cmd="BOX 30,20,10 130,90,10 22")
 assert r.get("status")=="completed"
 first=handles()
 assert len(first)==2, first
 execute(op="select",clear=True)
 r=execute(op="start",cmd="UNION")
 assert r.get("status")=="waiting_input"
 execute(op="input",kind="selection",handles=first)
 r=execute(op="input",kind="enter")
 assert r.get("status")=="completed"
 main=handles()
 assert len(main)==1, main
 r=execute(op="run",cmd="CYLINDER 80,55,-1 11 34")
 assert r.get("status")=="completed"
 solids=handles()
 cutter=next(x for x in solids if x!=main[0])
 execute(op="select",clear=True)
 execute(op="start",cmd="SUBTRACT")
 execute(op="input",kind="selection",handles=main)
 execute(op="input",kind="enter")
 execute(op="input",kind="selection",handles=[cutter])
 r=execute(op="input",kind="enter")
 assert r.get("status")=="completed"
 solids=handles()
 assert len(solids)==1, solids
 q=ask("measure",handles=solids)
 val=q["measurements"][0]["mesh"]["volume"]
 print("SOLID_VOLUME",val,flush=True)
 assert 250000<val<500000, val
 audit=ask("audit")
 assert audit.get("summary",{}).get("errors")==0
 f=ask("finish")
 assert f["finished"] and f["dwg"]
 print("RESULT",json.dumps(f,ensure_ascii=False),flush=True)
finally:
 p.stdin.close()
 try:
  p.wait(timeout=15)
 except subprocess.TimeoutExpired:
  p.kill()
  p.wait(timeout=5)