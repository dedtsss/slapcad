#!/usr/bin/env python3
"""Natural language -> GPT-6.1 Sol -> validated 2D CAD on HangarVPS.
OpenAI credentials stay on BruceVPS; only numeric geometry crosses SSH.
"""
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

MODEL = "gpt-6.1-sol"
API_ENDPOINT = "https://api.openai.com/v1/responses"
SSH = [
    "/usr/bin/ssh", "-F", "/dev/null", "-T",
    "-i", "/root/.ssh/hangarvps_ed25519",
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "HostKeyAlias=64.235.37.125",
    "-o", "UserKnownHostsFile=/root/.ssh/known_hosts",
    "-o", "ConnectTimeout=9",
    "-o", "ForwardAgent=no",
    "-o", "ForwardX11=no",
    "-o", "ClearAllForwardings=yes",
    "root@100.79.53.90",
    "runuser -u ocstest -- /usr/bin/python3 /home/ocstest/opencadstudio/cad_build.py",
]
INSTRUCTION = (
    "You are a precise CAD drawing planner. Convert user instructions into "
    "exactly ONE valid JSON object and no markdown. This pilot supports only "
    "a 2D rectangular plate with four circular hole outlines, one at each "
    "corner with the same offset from each adjacent edge. "
    "Use keys exactly: shape, width_mm, height_mm, "
    "hole_diameter_mm, hole_offset_mm. "
    "The shape must be rectangular_plate. All four measurements must be "
    "numeric in millimeters; never invent missing measurements. "
    "If information is missing or a different geometry is requested, "
    "return exactly {\"error\":\"missing_or_unsupported_geometry\"}. "
    "Do not claim to cut 3D holes. "
)

def stop(message, code=2):
    print(json.dumps({"ok":False,"error":message[:280]},ensure_ascii=False))
    sys.exit(code)

if len(sys.argv)!=2 or not sys.argv[1].strip() or len(sys.argv[1])>3000:
    stop("Expected one natural language CAD task <=3000 characters")
key = os.environ.get("OPENAI_API_KEY","")
if not key:
    stop("OPENAI_API_KEY not injected by trusted secret manager")
os.umask(0o077)
payload = {
    "model": MODEL,
    "input": [
        {"role":"system","content":INSTRUCTION},
        {"role":"user","content":sys.argv[1]}
    ],
    "max_output_tokens": 512,
}
req=urllib.request.Request(
    API_ENDPOINT,
    data=json.dumps(payload,separators=(",",":")).encode(),
    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req,timeout=55) as stream:
        response=json.load(stream)
except urllib.error.HTTPError as exc:
    stop("OpenAI returned HTTP "+str(exc.code))
except Exception as exc:
    stop("OpenAI transport error: "+type(exc).__name__)

if response.get("status")!="completed":
    stop("OpenAI response not completed")
raw="".join(c.get("text","") for item in response.get("output",[])
            for c in item.get("content",[]) if c.get("type")=="output_text")
try:
    plan=json.loads(raw)
except Exception:
    stop("Model returned invalid JSON")
expected={"shape","width_mm","height_mm","hole_diameter_mm","hole_offset_mm"}
if not isinstance(plan,dict) or set(plan)!=expected or plan["shape"]!="rectangular_plate":
    stop("Model plan unsupported or incomplete")
for field in expected-{"shape"}:
    v=plan[field]
    if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v):
        stop("Model returned invalid numeric parameter "+field)
    if v<0 or v>2000:
        stop("Model numeric parameter outside pilot limit")
# Never pass API credentials or user's text into the remote process.
clean_env={"HOME":"/root","PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C"}
try:
    remote=subprocess.run(
        SSH, input=json.dumps(plan,separators=(",",":")).encode(),
        capture_output=True, timeout=100, env=clean_env,
        check=False,
    )
except subprocess.TimeoutExpired:
    stop("Remote CAD worker timed out")
if remote.returncode!=0:
    stop("Remote CAD worker failed with exit "+str(remote.returncode))
try:
    cad=json.loads(remote.stdout.decode())
except Exception:
    stop("Remote CAD worker returned invalid JSON")
if not cad.get("ok"):
    stop("Remote CAD worker rejected geometry: "+str(cad.get("error","unknown")))
print(json.dumps({
    "ok":True,"model":MODEL,"cad_engine":cad.get("engine_version"),
    "model_plan":plan,"drawing":cad,
    "openai_usage":response.get("usage",{}),
    "credential_handling":"OpenAI key remained on BruceVPS; only numeric plan sent to HangarVPS",
},ensure_ascii=False))