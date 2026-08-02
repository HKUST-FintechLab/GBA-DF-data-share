"""Measure "phantom limbs": pose landmarks the client would DRAW while they sit outside the frame.

The complaint that started this study was about td_02 — MediaPipe painted legs that are not in
the camera view. That is not a bug in the client, it is what MediaPipe Pose does: it regresses
all 33 landmarks whether or not they are visible, so normalised x/y routinely leave [0,1] and the
visibility score for an *occluded-but-inferred* joint stays well above the drawing threshold.

The metric therefore has to match what the audience sees, not what is "wrong" in the abstract:

    a landmark is a PHANTOM in a frame iff
        visibility >= 0.25          <- the exact gate in static/client.js::paintSkeleton
      AND (x < 0 or x > 1 or y < 0 or y > 1)   <- outside the rendered image

Layout is confirmed from the repo rather than assumed:
  - rehearsal_studies/metric_response/extract_pose.py writes [p.x, p.y, p.z, p.visibility]
    straight off `res.pose_landmarks.landmark` -> NORMALISED, channel 3 = visibility.
  - static/client.js::poseArray does the same for the browser path, and paintSkeleton multiplies
    x,y by canvas width/height at draw time -> the stored numbers are normalised there too.
  - static/client.js::POSE_CONNECTIONS is the standard MediaPipe Pose 33-point topology.

Usage:  ../../.venv/Scripts/python.exe phantom_limbs.py
Writes results.json next to this file and prints the ranking table.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
NPZ = os.path.join(REPO, "demo_videos", "npz")

DRAW_VIS = 0.25          # static/client.js::paintSkeleton
STRICT_VIS = 0.50        # "the model is sure", not merely above the drawing gate

LOWER = list(range(23, 33))          # hips 23/24, knees 25/26, ankles 27/28, feet 29-32
FEET = list(range(27, 33))           # ankles + heels + foot index - the part that dangles
POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
]
LOWER_BONES = [(a, b) for a, b in POSE_CONNECTIONS if a >= 23 or b >= 23]


def overshoot(x, y):
    """Distance outside the unit box, in normalised units (0 inside). Chebyshev-style:
    how far past the nearest edge, which is what a viewer reads as 'off the picture'."""
    dx = np.maximum(np.maximum(-x, x - 1.0), 0.0)
    dy = np.maximum(np.maximum(-y, y - 1.0), 0.0)
    return np.maximum(dx, dy)


def analyse(path):
    body = np.load(path)["body"].astype(np.float64)      # (T,33,4)
    T = body.shape[0]
    x, y, vis = body[..., 0], body[..., 1], body[..., 3]
    outside = (x < 0) | (x > 1) | (y < 0) | (y > 1)
    over = overshoot(x, y)
    drawn = vis >= DRAW_VIS
    sure = vis >= STRICT_VIS
    phantom = drawn & outside                            # (T,33) what the eye actually catches

    def rate(idx, mask):
        return float(mask[:, idx].mean())

    ph_low = phantom[:, LOWER]
    ph_low_sure = (sure & outside)[:, LOWER]
    over_low = over[:, LOWER]
    sev = over_low[ph_low]                               # overshoot of the phantom slots only

    # a bone is drawn iff BOTH endpoints clear the gate; it reads as invented if either end is out
    bone_ph = 0
    bone_drawn = 0
    for a, b in LOWER_BONES:
        d = drawn[:, a] & drawn[:, b]
        bone_drawn += int(d.sum())
        bone_ph += int((d & (outside[:, a] | outside[:, b])).sum())

    return {
        "T": T,
        # headline: share of drawn-and-outside lower-body landmark slots
        "phantom_rate_lower": rate(LOWER, phantom),
        "phantom_rate_lower_strict": float(ph_low_sure.mean()),
        "phantom_rate_feet": rate(FEET, phantom),
        "phantom_rate_all33": float(phantom.mean()),
        # how much of the clip is affected at all
        "phantom_frames_pct": float((ph_low.sum(axis=1) > 0).mean()),
        "phantom_frames_ge3_pct": float((ph_low.sum(axis=1) >= 3).mean()),
        # how far off the picture it goes (normalised units; 1.0 = a whole frame height/width)
        "max_overshoot_lower": float(over_low.max()),
        "median_overshoot_phantom": float(np.median(sev)) if sev.size else 0.0,
        "p90_overshoot_phantom": float(np.percentile(sev, 90)) if sev.size else 0.0,
        # separate "genuinely out of frame" from "drawn anyway"
        "oof_rate_lower_any_vis": rate(LOWER, outside),
        "mean_vis_lower_when_outside": (
            float(vis[:, LOWER][outside[:, LOWER]].mean()) if outside[:, LOWER].any() else 0.0),
        "mean_vis_lower": float(vis[:, LOWER].mean()),
        # bone-level view (what the skeleton lines look like)
        "phantom_bone_rate": (bone_ph / bone_drawn) if bone_drawn else 0.0,
        # upper body, as a control: is this clip broken everywhere or only below the waist?
        "phantom_rate_upper": rate(list(range(0, 23)), phantom),
    }


def main():
    rows = []
    for cls in ("asd", "td"):
        folder = os.path.join(NPZ, cls)
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".npz"):
                continue
            clip = name[len("upload_"):-len(".npz")] if name.startswith("upload_") else name[:-4]
            r = analyse(os.path.join(folder, name))
            r["clip"] = clip
            r["cls"] = cls.upper()
            rows.append(r)

    rows.sort(key=lambda r: (-r["phantom_rate_lower"], -r["max_overshoot_lower"]))
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    hdr = ("clip", "T", "phantom%", "strict%", "frames%", ">=3 %", "maxOver", "medOver",
           "oof%", "vis|oof", "bone%", "upper%")
    print(f"{hdr[0]:<7}{hdr[1]:>5}{hdr[2]:>10}{hdr[3]:>9}{hdr[4]:>9}{hdr[5]:>8}"
          f"{hdr[6]:>9}{hdr[7]:>9}{hdr[8]:>8}{hdr[9]:>9}{hdr[10]:>8}{hdr[11]:>8}")
    for r in rows:
        print(f"{r['clip']:<7}{r['T']:>5}{100*r['phantom_rate_lower']:>9.1f}%"
              f"{100*r['phantom_rate_lower_strict']:>8.1f}%"
              f"{100*r['phantom_frames_pct']:>8.1f}%"
              f"{100*r['phantom_frames_ge3_pct']:>7.1f}%"
              f"{r['max_overshoot_lower']:>9.3f}{r['median_overshoot_phantom']:>9.3f}"
              f"{100*r['oof_rate_lower_any_vis']:>7.1f}%"
              f"{r['mean_vis_lower_when_outside']:>9.3f}"
              f"{100*r['phantom_bone_rate']:>7.1f}%"
              f"{100*r['phantom_rate_upper']:>7.1f}%")

    vals = np.array([r["phantom_rate_lower"] for r in rows])
    print(f"\nn={len(rows)}  median {100*np.median(vals):.1f}%  mean {100*vals.mean():.1f}%")
    for r in rows:
        z = (r["phantom_rate_lower"] - vals.mean()) / (vals.std(ddof=1) or 1.0)
        print(f"  {r['clip']:<7} phantom {100*r['phantom_rate_lower']:>5.1f}%  z={z:+.2f}")

    # Could a renderer tweak fix this instead of dropping the clip? Two candidate fixes:
    #   (a) raise the visibility gate above the current 0.25
    #   (b) clip the skeleton at the frame box (never draw a landmark outside [0,1])
    print("\n=== fix option (a): raise the visibility gate ===")
    print(f"{'clip':<7}" + "".join(f"{g:>9.2f}" for g in
                                   (0.25, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)))
    for cls in ("asd", "td"):
        for name in sorted(os.listdir(os.path.join(NPZ, cls))):
            clip = name[len("upload_"):-len(".npz")]
            if not clip.startswith("td_"):
                continue
            b = np.load(os.path.join(NPZ, cls, name))["body"].astype(np.float64)
            x, y, v = b[..., 0], b[..., 1], b[..., 3]
            out = ((x < 0) | (x > 1) | (y < 0) | (y > 1))[:, LOWER]
            vl = v[:, LOWER]
            print(f"{clip:<7}" + "".join(f"{100*((vl >= g) & out).mean():>8.1f}%"
                                        for g in (0.25, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)))
    # Cross-check against what is actually staged for the live demo. demo_nodes/node_N holds
    # browser-extracted copies (client.js path, slightly different frame sampling) rather than the
    # extract_pose.py pool, so the numbers are close but not identical.
    staged = os.path.join(REPO, "demo_nodes")
    if os.path.isdir(staged):
        print("\n=== cross-check: clips actually staged in demo_nodes/ (browser-extracted) ===")
        for node in sorted(os.listdir(staged)):
            for cls in ("ASD", "TD"):
                d = os.path.join(staged, node, cls)
                if not os.path.isdir(d):
                    continue
                for name in sorted(os.listdir(d)):
                    if not name.startswith("upload_"):
                        continue
                    b = np.load(os.path.join(d, name))["body"].astype(np.float64)
                    x, y, v = b[..., 0], b[..., 1], b[..., 3]
                    out = ((x < 0) | (x > 1) | (y < 0) | (y > 1))[:, LOWER]
                    ph = (v[:, LOWER] >= DRAW_VIS) & out
                    print(f"  {node} {name:<22} T={b.shape[0]:>4}  phantom {100*ph.mean():>5.1f}%"
                          f"  frames {100*(ph.sum(1) > 0).mean():>5.1f}%")

    print("\n=== fix option (b): clip the skeleton at the frame box ===")
    print("share of drawn bones (all 35) that would disappear")
    for cls in ("asd", "td"):
        for name in sorted(os.listdir(os.path.join(NPZ, cls))):
            clip = name[len("upload_"):-len(".npz")]
            b = np.load(os.path.join(NPZ, cls, name))["body"].astype(np.float64)
            x, y, v = b[..., 0], b[..., 1], b[..., 3]
            out = (x < 0) | (x > 1) | (y < 0) | (y > 1)
            drawn = v >= DRAW_VIS
            tot = lost = 0
            for a, bb in POSE_CONNECTIONS:
                d = drawn[:, a] & drawn[:, bb]
                tot += int(d.sum())
                lost += int((d & (out[:, a] | out[:, bb])).sum())
            print(f"  {clip:<7} {100*lost/max(tot,1):>5.1f}%")


if __name__ == "__main__":
    main()
