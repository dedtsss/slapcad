#!/usr/bin/env python3
"""Non-LLM end-to-end verification of Bruce -> Hangar persistent native MCP bridge.
Intentionally uses no credential. Calls same API surface as Sol tool calls.
"""
import importlib.util
import json
import math
spec=importlib.util.spec_from_file_location("pilot","/opt/opencadstudio-pilot/sol_mcp_agent.py")
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)
b=pilot.Bridge()
events=[]
def call(tool, **args):
    r=b.call(tool,args)
    if not r.get("ok"):raise RuntimeError(tool+" rejected: "+str(r.get("error")))
    data=r.get("data",{})
    events.append((tool,data.get("status"),data.get("count")))
    return data
def execute(request):
    d=call("execute",request=request)
    if d.get("status")!="completed":raise RuntimeError("execute incomplete: "+json.dumps(d)[:500])
    return d
def handles():
    return [x["handle"] for x in call("query",type="3DSolid")["entities"]]
try:
    call("commands",name="BOX")
    call("commands",name="CYLINDER")
    call("inspect")
    initial=[
      "BOX 0,0,0 160,100,0 10",
      "BOX 0,88,10 160,100,10 60",
      "BOX 20,60,10 30,90,10 35",
      "BOX 130,60,10 140,90,10 35",
    ]
    execute({"op":"batch","steps":[{"op":"run","cmd":s} for s in initial]})
    union_list=handles()
    if len(union_list)!=4:raise ValueError("four solids required before union")
    execute({"op":"batch","steps":[
      {"op":"select","clear":True},
      {"op":"start","cmd":"UNION"},
      {"op":"input","kind":"selection","handles":union_list},
      {"op":"input","kind":"enter"}
    ]})
    unioned=handles()
    if len(unioned)!=1:raise ValueError("union was not one 3D solid")
    cutters=[
     "CYLINDER 45,20,-1 5 12",
     "CYLINDER 115,20,-1 5 12",
     "CYLINDER 45,70,-1 5 12",
     "CYLINDER 115,70,-1 5 12",
     "BOX 65,87,30 95,87,30 1", # zero thickness placeholder removed below
    ]
    cutters[-1]="BOX 65,87,30 95,101,30 24"
    execute({"op":"batch","steps":[{"op":"run","cmd":s} for s in cutters]})
    operands=handles()
    cut_handles=[x for x in operands if x not in unioned]
    if len(cut_handles)!=5:raise ValueError("five cutter solids required")
    r=execute({"op":"batch","steps":[
       {"op":"select","clear":True},
       {"op":"start","cmd":"SUBTRACT"},
       {"op":"input","kind":"selection","handles":unioned},
       {"op":"input","kind":"enter"},
       {"op":"input","kind":"selection","handles":cut_handles},
       {"op":"input","kind":"enter"},
    ]})
    final=handles()
    if len(final)!=1:raise ValueError("expected one B-rep solid, got "+str(final))
    measure=call("measure",handles=final)
    entry=measure["measurements"][0]
    volume=entry["mesh"]["volume"]
    bounds=entry["bounds"]
    expected=160*100*10 +160*12*60 + 2*10*30*35 - 2*10*2*35 - 4*math.pi*5*5*10 -30*12*24
    print("TEST_RESULT",json.dumps({"volume":volume,"expected":expected,"relative_error":abs(expected-volume)/expected,
                 "bounds":bounds},ensure_ascii=False),flush=True)
    if not (0<abs(expected-volume)/expected<.006):raise ValueError("unexpected relative volume mismatch")
    audit=call("audit")
    if audit.get("summary",{}).get("errors",1)!=0:raise ValueError("CAD audit")
    finalsave=call("finish")
    print("FILES",json.dumps(finalsave,ensure_ascii=False),flush=True)
    assert finalsave["finished"] and finalsave["dwg"] and finalsave["png"]
    print("BRIDGE_MCP_TEST_PASS",len(events),"model_input_none",flush=True)
finally:
    b.close()