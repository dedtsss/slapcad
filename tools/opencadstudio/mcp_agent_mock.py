#!/usr/bin/env python3
"""Mock LLM function-call protocol, real MCP/CAD. NEVER uses or requests API credentials."""
import importlib.util
import itertools
import json
import os
import sys

spec=importlib.util.spec_from_file_location("controller","/opt/opencadstudio-pilot/sol_mcp_agent.py")
cad=importlib.util.module_from_spec(spec);spec.loader.exec_module(cad)
count=0
old=[]
ids=itertools.count(1)
stage=0
main_solid=None
cutter=None

def response(name,args):
    i=next(ids)
    return {"id":"MOCK_response_"+str(i),
            "status":"completed",
            "usage":{"input_tokens":0,"output_tokens":0},
            "output":[{"type":"function_call","name":name,
                       "call_id":"MOCK_call_"+str(i),"arguments":json.dumps(args)}]}

def fake_api(payload,irrelevant):
    global stage,old,main_solid,cutter
    if stage:
        answers=[json.loads(a["output"]) for a in payload["input"] if a["type"]=="function_call_output"]
        if len(answers)!=1:raise RuntimeError("previous_response_id feedback did not preserve tool output")
        ans=answers[0]
        if not ans.get("ok"):
            raise RuntimeError("mock CAD function failed at stage "+str(stage)+": "+str(ans.get("error")))
        if stage in (4,6):
            return_handles=ans["data"]["entities"]
            if stage==4:
                old=[x["handle"] for x in return_handles]
            else:
                main_solid=return_handles[0]["handle"]
        if stage==8:
            cutter=next(x["handle"] for x in ans["data"]["entities"] if x["handle"]!=main_solid)
    actions=[
      ("cad_inspect",{}),
      ("cad_help",{"name":"BOX"}),
      ("cad_edit",{"request":{"op":"batch","steps":[
          {"op":"run","cmd":"BOX 0,0,0 120,90,0 10"},
          {"op":"run","cmd":"BOX 20,20,10 100,70,10 24"}]}}),
      ("cad_query",{"type":"3DSolid"}),
      ("cad_edit",{"request":{"op":"batch","steps":[
          {"op":"select","clear":True},
          {"op":"start","cmd":"UNION"},
          {"op":"input","kind":"selection","handles":old},
          {"op":"input","kind":"enter"}]}}),
      ("cad_query",{"type":"3DSolid"}),
      ("cad_edit",{"request":{"op":"run","cmd":"CYLINDER 60,45,-1 12 36"}}),
      ("cad_query",{"type":"3DSolid"}),
      ("cad_edit",{"request":{"op":"batch","steps":[
          {"op":"select","clear":True},
          {"op":"start","cmd":"SUBTRACT"},
          {"op":"input","kind":"selection","handles":[main_solid]},
          {"op":"input","kind":"enter"},
          {"op":"input","kind":"selection","handles":[cutter]},
          {"op":"input","kind":"enter"}]}}),
      ("cad_query",{"type":"3DSolid"}),
      ("cad_measure",{"handles":[main_solid]}),
      ("cad_audit",{}),
      ("cad_finish",{})
    ]
    if stage>=len(actions):raise RuntimeError("mock test overshot goal")
    item=actions[stage]
    stage+=1
    return response(*item)

if __name__=="__main__":
    cad.MODEL="MOCK_NO_LLM"
    cad.call_openai=fake_api
    # Solely a mock sentinel. No HTTP API is ever called.
    os.environ["OPENAI_API_KEY"]="MOCK_KEY_NOT_A_REAL_SECRET"
    sys.argv=[sys.argv[0],"Dummy test: create 3D plate with one real hole through the center."]
    cad.main()
    if stage!=13:
        raise RuntimeError("not all mock model-directed function calls executed: "+str(stage))
    print("CONTROLLER_PROTOCOL_MOCK_PASS",stage,"LLM_CALLS_ZERO",flush=True)