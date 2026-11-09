#!/usr/bin/env python3
"""Bounded, non-secret OpenCADStudio 2D drawing worker (v2026.45)."""
import json
import math
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

BASE = Path("/home/ocstest/opencadstudio")
ENGINE = BASE / "OpenCADStudio-v2026.45-linux-x86_64.AppImage"
RESULTS = BASE / "results" / "sol-pilot"
RESULTS.mkdir(mode=0o750, parents=True, exist_ok=True)

def fail(message):
    print(json.dumps({"ok": False, "error": str(message)[:280]}, ensure_ascii=False))
    sys.exit(2)

try:
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192:
        fail("plan exceeds size limit")
    plan = json.loads(raw)
    if not isinstance(plan, dict) or plan.get("shape") != "rectangular_plate":
        fail("only rectangular_plate supported")
    def number(name, bottom, top):
        v = plan.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("invalid numeric parameter: " + name)
        v = float(v)
        if v < bottom or v > top:
            raise ValueError("value out of limits: " + name)
        return v
    w = number("width_mm", 30, 2000)
    h = number("height_mm", 30, 2000)
    dia = number("hole_diameter_mm", 2, 300)
    off = number("hole_offset_mm", 2, 500)
    r = dia / 2
    if off <= r + 1 or w - 2 * off <= dia + 2 or h - 2 * off <= dia + 2:
        fail("holes must fit within plate and not overlap")
    def f(v):
        return format(v, ".6g")
    coords = [(off, off), (w-off, off), (w-off, h-off), (off, h-off)]
    stem = "sol-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    dwg = RESULTS / (stem + ".dwg")
    dxf = RESULTS / (stem + ".dxf")
    pdf = RESULTS / (stem + ".pdf")
    report = RESULTS / (stem + ".json")
    errfile = RESULTS / (stem + ".stderr.log")
    with errfile.open("w") as err:
        proc = subprocess.Popen([str(ENGINE), "--serve"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=err, text=True, bufsize=1, cwd=str(BASE))
        try:
            banner = json.loads(proc.stdout.readline())
            if not banner.get("ready"):
                raise RuntimeError("CAD engine not ready")
            def ask(obj):
                proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("CAD engine closed response stream")
                result = json.loads(line)
                if not result.get("ok"):
                    raise RuntimeError("CAD operation failed: " + str(result.get("code",result.get("error")))[:110])
                return result
            ask({"op":"new"})
            rect = f"PLINE 0,0 {f(w)},0 {f(w)},{f(h)} 0,{f(h)} C"
            cmds = [rect] + [f"CIRCLE {f(x)},{f(y)} {f(r)}" for x,y in coords]
            for cmd in cmds:
                out=ask({"op":"run","cmd":cmd})
                if out.get("status") != "completed":
                    raise RuntimeError("CAD command not completed")
            entities=ask({"op":"entities"})
            if entities.get("by_type") != {"Circle":4,"Polyline":1}:
                raise RuntimeError("entity manifest mismatch")
            circles=ask({"op":"query","type":"Circle"})
            if circles.get("count")!=4:
                raise RuntimeError("circle query mismatch")
            audit=ask({"protocol":1,"op":"audit","target_format":"dwg","target_version":"2018"})
            if audit.get("status")!="passed" or audit.get("summary",{}).get("errors")!=0:
                raise RuntimeError("CAD audit failed")
            state=ask({"protocol":1,"op":"state"})
            info=state.get("state",state)
            doc=info["document_id"]
            rev=info["revision"]
            saved=ask({"protocol":1,"op":"save_verified","request_id":stem+"-save",
                     "document_id":doc,"revision":rev,
                     "path":str(dwg),"target_format":"dwg",
                     "target_version":"2018","overwrite":False})
            if not saved.get("result",{}).get("verified"):
                raise RuntimeError("DWG not verified")
            plot=ask({"protocol":1,"op":"plot","request_id":stem+"-plot",
                      "document_id":doc,"path":str(pdf),
                      "layout":"Model","fit":True,"center":True})
        finally:
            proc.stdin.close()
            proc.terminate()
            try: proc.wait(timeout=4)
            except subprocess.TimeoutExpired: proc.kill()
    conversion=subprocess.run([str(ENGINE),"--export",str(dwg),str(dxf)],
                              capture_output=True,text=True,timeout=65,cwd=str(BASE))
    if conversion.returncode:
        raise RuntimeError("DXF export failed with exit " + str(conversion.returncode))
    sizes={p.suffix.lstrip("."):p.stat().st_size if p.exists() else 0 for p in [dwg,dxf,pdf]}
    if min(sizes.values())<=0:
        raise RuntimeError("missing output file")
    result={"ok":True,"engine_version":"2026.45","type":"2D outline with circular contours",
            "note":"Circles are 2D hole callouts; no 3D boolean cut verified",
            "parameters": {"width_mm":w,"height_mm":h,
                           "hole_diameter_mm":dia,"hole_offset_mm":off},
            "entities":entities.get("by_type"),
            "audit_errors":audit.get("summary",{}).get("errors"),
            "paths":{"dwg":str(dwg),"dxf":str(dxf),"pdf":str(pdf)},
            "bytes":sizes}
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
except Exception as exc:
    fail(type(exc).__name__ + ": " + str(exc)[:220])