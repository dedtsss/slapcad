#!/usr/bin/env python3
"""Regenerate verifiable 2D SECTION VIEWS from a saved OpenCADStudio 3D DWG.

No invented geometry: all contours originate from the OpenCADStudio SECTION
command run on the actual 3D solid. This is a SOURCE-LINKED REGENERATOR, not
native associative projections: rerun it after every 3D save.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path("/home/ocstest/opencadstudio")
ENGINE = ROOT/"OpenCADStudio-v2026.45-linux-x86_64.AppImage"
SOURCES = ROOT/"results"/"sol-pilot"
OUT_DIR = SOURCES/"derived-sections"
EXPECTED_AXES = (("Z",6.0),("Y",70.0),("X",100.0))

def fail(message):
    raise RuntimeError(message)

def pretty(x):
    return format(float(x),".6f").rstrip("0").rstrip(".") if x else "0"

def point(x):
    return tuple(round(float(c),5) for c in x)

def segments_to_loops(edges,axis):
    ind = {"Z":(0,1),"Y":(0,2),"X":(1,2)}[axis]
    adj=collections.defaultdict(list)
    source_edges=set()
    for e in edges:
        a=point(e["start"][i] for i in ind)
        b=point(e["end"][i] for i in ind)
        if a==b:
            fail("SECTION returned a zero-length segment")
        key=tuple(sorted([a,b]))
        if key in source_edges:
            fail("SECTION returned duplicate segments")
        source_edges.add(key)
        adj[a].append(b)
        adj[b].append(a)
    if not adj or any(len(v)!=2 for v in adj.values()):
        fail("SECTION is not a set of closed, degree-2 loops on "+axis)
    visited=set()
    loops=[]
    for start in sorted(adj):
        if start in visited:continue
        pts=[start]
        visited.add(start)
        prev=None
        cur=start
        for _ in range(len(adj)+1):
            options=[v for v in adj[cur] if v!=prev]
            if len(options)!= (2 if prev is None else 1):
                fail("branched section")
            nxt=sorted(options)[0]
            prev,cur=cur,nxt
            if cur==start:break
            if cur in visited:fail("premature cycle")
            visited.add(cur)
            pts.append(cur)
        else:fail("unclosed section")
        if len(pts)<3:fail("short loop")
        loops.append(pts)
    if len(visited)!=len(adj):fail("missed vertices")
    return loops

def simplified(vertices):
    pts=list(vertices)
    changed=True
    while changed and len(pts)>3:
        changed=False; result=[]
        for i,c in enumerate(pts):
            a=pts[i-1];b=pts[(i+1)%len(pts)]
            cross=(c[0]-a[0])*(b[1]-a[1])-(c[1]-a[1])*(b[0]-a[0])
            ab=math.hypot(b[0]-a[0],b[1]-a[1])
            ac=(c[0]-a[0])*(b[0]-a[0])+(c[1]-a[1])*(b[1]-a[1])
            if ab>1e-8 and abs(cross)/ab<0.0001 and 0<=ac<=ab*ab:
                changed=True
            else:result.append(c)
        if len(result)>=3:pts=result
        else:break
    return pts

def circle_from_loop(pts):
    if len(pts)<24:return None
    xs=[v[0] for v in pts];ys=[v[1] for v in pts]
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
    rx=(maxx-minx)/2; ry=(maxy-miny)/2
    if rx<.2 or abs(rx-ry)>max(.02,rx*.006):return None
    cx=(maxx+minx)/2;cy=(maxy+miny)/2
    r=(rx+ry)/2
    errors=[abs(math.hypot(x-cx,y-cy)-r) for x,y in pts]
    if max(errors)>max(.035,.012*r):return None
    return (cx,cy,r,max(errors))

class CAD:
    def __init__(self):
        self.p=subprocess.Popen([str(ENGINE),"--serve"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,text=True,bufsize=1,cwd=str(ROOT))
        ready=json.loads(self.p.stdout.readline())
        if not ready.get("ready") or ready.get("version")!="2026.45":
            fail("Unexpected OpenCADStudio engine")
        self.num=0
    def op(self,command):
        self.p.stdin.write(json.dumps(command,separators=(",",":"),ensure_ascii=False)+"\n")
        self.p.stdin.flush()
        raw=self.p.stdout.readline()
        if not raw:fail("Editor ended unexpectedly")
        r=json.loads(raw)
        if not r.get("ok") or r.get("status")=="failed":
            fail(str(command.get("op"))+": "+str(r.get("error"))[:180])
        return r
    def close(self):
        self.p.terminate()
        try:self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:self.p.kill()
    def selection(self,handle):
        self.num+=1
        return self.op({"protocol":1,"op":"select","request_id":"view-select-"+str(self.num),
                        "document_id":1,"clear":True,"handles":[handle]})
    def section(self,source,axis,height):
        self.op({"op":"open","path":str(source)})
        ss=self.op({"op":"query","type":"3DSolid","limit":50})["entities"]
        if len(ss)!=1:fail("A single 3D Solid is required")
        self.selection(ss[0]["handle"])
        self.op({"op":"run","cmd":"SECTION "+axis+" "+pretty(height)})
        all_lines=self.op({"op":"query","type":"Line","limit":10000})["entities"]
        loops=segments_to_loops(all_lines,axis)
        return loops,len(all_lines)
    def draw(self,cmd):
        r=self.op({"op":"run","cmd":cmd})
        if r.get("status")!="completed" or r.get("unconsumed"):
            fail("Drawing command incomplete: "+cmd[:100])
    def save(self,path):
        s=self.op({"protocol":1,"op":"state"})
        state=s.get("state",s)
        self.num+=1
        r=self.op({"protocol":1,"op":"save_verified","request_id":"section-save-"+str(self.num),
                   "document_id":state["document_id"],"revision":state["revision"],
                   "path":str(path),"target_format":"dwg","target_version":"2018","overwrite":False})
        if not r.get("result",{}).get("verified"):fail("DWG verification failed")

def main():
    if len(sys.argv)!=2:fail("Usage: regenerate_sections.py /absolute/path/source.dwg")
    source=Path(sys.argv[1])
    if not source.is_absolute() or source.suffix.lower()!=".dwg":
        fail("An existing absolute DWG is required")
    source=source.resolve(strict=True)
    if source.parent!=SOURCES:
        fail("Input must reside in the approved CAD results directory")
    original=source.read_bytes()
    sha=hashlib.sha256(original).hexdigest()
    stat=source.stat()
    identifier=re.sub(r"[^a-zA-Z0-9_-]","-",source.stem)[:52]
    prefix=identifier+"-source-sections-v2-"+sha[:12]
    OUT_DIR.mkdir(mode=0o750,parents=True,exist_ok=True)
    dwg=OUT_DIR/(prefix+".dwg")
    pdf=OUT_DIR/(prefix+".pdf")
    manifest=OUT_DIR/(prefix+".json")
    if dwg.exists() or pdf.exists() or manifest.exists():
        if not (dwg.is_file() and pdf.is_file() and manifest.is_file()):
            fail("Incomplete older output; do not overwrite")
        old=json.loads(manifest.read_text())
        if old.get("source_sha256")!=sha:fail("Existing output source SHA mismatch")
        print(json.dumps({"ok":True,"reused":True,"source_sha256":sha,"paths":old["paths"],
                          "sections":old["sections"]},ensure_ascii=False))
        return
    client=CAD()
    try:
        measurements={}
        first=client.op({"op":"open","path":str(source)})
        hs=client.op({"op":"query","type":"3DSolid"})["entities"]
        if len(hs)!=1:fail("Expected one 3D solid")
        m=client.op({"protocol":1,"op":"measure","request_id":"section-source-1",
                    "document_id":1,"handles":[hs[0]["handle"]]})
        entry=m["measurements"][0]
        volume=entry["mesh"]["volume"]
        bounds=entry["bounds"]
        if not volume>100:fail("Invalid source volume")
        raw={}
        for axis,plane in EXPECTED_AXES:
            loop,ns=client.section(source,axis,plane)
            raw[axis]=loop
            measurements[axis]={"plane_mm":plane,"raw_edges":ns,"closed_contours":len(loop),
                                "vertices":sum(len(x) for x in loop)}
        if tuple(len(raw[x]) for x in ("Z","Y","X"))!=(6,2,2):
            fail("Unexpected sectional topology for acceptance part")
        client.op({"op":"new"})
        counts=collections.Counter()
        summary={}
        for axis,loops in raw.items():
            produced=[]
            for loop in loops:
                if axis=="Z":
                    circle=circle_from_loop(loop)
                    if circle:
                        x,y,r,dev=circle
                        client.draw("CIRCLE "+pretty(x)+","+pretty(y)+" "+pretty(r))
                        counts["Circle"]+=1
                        produced.append({"type":"Circle","center":[x,y],"radius":r,
                                         "max_radial_deviation":dev})
                        continue
                coords=simplified(loop)
                if axis=="Z": pts=coords
                elif axis=="Y":pts=[(x,z-220) for x,z in coords]
                else:pts=[(y+265,z-220) for y,z in coords]
                text="PLINE "+" ".join(pretty(x)+","+pretty(y) for x,y in pts)+" C"
                client.draw(text)
                counts["Polyline"]+=1
                produced.append({"type":"Polyline","points":len(pts),"bbox":
                    [min(x for x,y in pts),min(y for x,y in pts),
                     max(x for x,y in pts),max(y for x,y in pts)]})
            summary[axis]=produced
        if counts["Circle"]!=5 or counts["Polyline"]!=5:
            fail("Unexpected drawing profile: "+str(counts))
        x0,y0,z0=(float(v) for v in bounds["min"])
        x1,y1,z1=(float(v) for v in bounds["max"])
        for cmd in [
            f"DIMLINEAR {pretty(x0)},{pretty(y0)} {pretty(x1)},{pretty(y0)} {pretty((x0+x1)/2)},{pretty(y0-25)}",
            f"DIMLINEAR {pretty(x0)},{pretty(y0)} {pretty(x0)},{pretty(y1)} {pretty(x0-25)},{pretty((y0+y1)/2)}",
            f"DIMLINEAR {pretty(x0)},{pretty(z0-220)} {pretty(x0)},{pretty(z1-220)} {pretty(x0-20)},{pretty((z0+z1)/2-220)}",
            f"DIMLINEAR {pretty(y0+265)},{pretty(z0-220)} {pretty(y0+265)},{pretty(z1-220)} {pretty(y0+245)},{pretty((z0+z1)/2-220)}",
        ]:
            client.draw(cmd)
            counts["Dimension"]+=1
        for cmd in [
            "TEXT 0,157 5 0 СЕЧЕНИЕ_Z6_ИЗ_3D",
            "TEXT 0,-163 5 0 СЕЧЕНИЕ_Y70_ИЗ_3D",
            "TEXT 265,-163 5 0 СЕЧЕНИЕ_X100_ИЗ_3D",
            "TEXT 0,-267 3 0 ИСТОЧНИК_SHA256_"+sha[:12],
            "TEXT 0,-275 3 0 АВТООБНОВЛЕНИЕ_ПРИ_ПОВТОРНОМ_ЗАПУСКЕ",
            "TEXT 0,-283 3 0 ДЕМО_НЕ_ДЛЯ_ИЗГОТОВЛЕНИЯ",
        ]:
            client.draw(cmd)
            counts["Text"]+=1
        dims=client.op({"op":"entities"}).get("by_type",{})
        if dims.get("Circle")!=5 or dims.get("Polyline")!=5 or dims.get("Dimension")!=4:
            fail("Drawing entities mismatch")
        audit=client.op({"protocol":1,"op":"audit","target_format":"dwg","target_version":"2018"})
        if audit.get("status")!="passed" or audit.get("summary",{}).get("errors")!=0:
            fail("Drafting audit failed")
        client.save(dwg)
        active=client.op({"protocol":1,"op":"state"})
        document_id=active.get("state",active)["document_id"]
        plot=client.op({"protocol":1,"op":"plot","request_id":"source-section-pdf-1","path":str(pdf),"document_id":document_id,"layout":"Model","fit":True,"center":True})
        d=pdf.read_bytes() if pdf.exists() else b""
        if not d.startswith(b"%PDF-") or b"%%EOF" not in d[-190:]:
            fail("PDF plot produced invalid data")
        if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
            fail("Source changed while regenerating; output is invalid")
        result={
          "ok":True,"reused":False,"engine":"OpenCADStudio 2026.45","generator_version":"2",
          "source":str(source),"source_sha256":sha,
          "source_size":stat.st_size,"source_volume_mm3":volume,"source_bounds":bounds,
          "sections":measurements,"generated":summary,
          "entity_counts":dict(counts),"verified_save":True,
          "audit":audit.get("summary"),"paths":{"dwg":str(dwg),"pdf":str(pdf),"report":str(manifest)},
          "sizes":{"dwg":dwg.stat().st_size,"pdf":pdf.stat().st_size},
          "created_at":datetime.now(timezone.utc).isoformat(),
          "limitations":"Regenerated source-dependent SECTION contours, not native associative or conventional orthographic views. Regenerate after changes."
        }
        manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False))
    finally:
        client.close()

if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"ok":False,"error":str(e)[:280]},ensure_ascii=False),flush=True)
        sys.exit(2)