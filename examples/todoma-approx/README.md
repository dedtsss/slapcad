# TODOMA — photographed concept, 2026-10-29

Two **unmeasured** engineering shapes created in AgentCAD 0.7.0 (build123d) on BrainVPS, not final design:

- `todoma_approx.py` — single editable Python source, geometry inferred from nine photos; parameters P/CENTERLINE have **illustrative values only**.
- `as_found.glb` — existing frame approximation: two folded C profiles with plan bends, round and oblong web holes, bolted splice plates, hitch placeholder and **existing transverse square beam**. The crossbeam is **not an axle**.
- `with_new_axle.glb` — same frame plus **separately introduced** axle, spring packs, hub placeholders and mounts. Only a visual conceptual alternative, no engineering sizing or location validation.
- `compare.png` — side-by-side conceptual visualization (A/B).
- Canonical project source and versioned STEP/GLB on BrainVPS:
  - `/home/brainremote/kolkhozcad/todoma/todoma_approx.py`
  - `/home/brainremote/kolkhozcad/todoma/build/v2_photo_approx_base/output.step`
  - `/home/brainremote/kolkhozcad/todoma/build/v3_suspension_concept/output.step`

**Not verified:** numeric dimensions, true 3D stamp/bend transitions, exact hole centres/dimensions, bolts/thread, spring stiffness/strength, axle placement, wheel track, load and handling, ground clearance, structural compliance. Even visually identified features remain approximate. **DO NOT FABRICATE FROM THESE FILES.**

Both runs returned `status=success`, `metrics.is_valid=true`, `validation.is_valid=true`, with STEP and GLB exported (headless; no viewer service). Test only proves geometric software execution, not physical correspondence.

Next: user annotates photo(s) in ChatGPT with pairs of points/lengths. Update P and local features in Python script; rebuild both variants, compare actual photo projection, keep crossbeam and new axle separate.
