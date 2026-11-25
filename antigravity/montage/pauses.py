#!/usr/bin/env python3
"""Remove the pauses that break a sentence in an already-edited video, without touching anything else.

MAIN WAY (an export whose "pauses" are filled with sound: stretched syllables, breaths, "اااه"):

  python pauses.py prep  "<edited>.mp4" --out "_pauses"
      Cuts the video into 20 s review chunks (540p) with the SOURCE time burned into the picture, so the
      agent reads exact times off the frame instead of guessing them.

  (the agent listens to every chunk and writes _pauses/remove.json:
      {"remove": [{"start": 4.26, "end": 4.95, "what": "stretched 'ه' + breath", "before": "وصديقه", "after": "هيرب"}]}
   times in source seconds, read from the burned-in clock)

  python pauses.py cut   "<edited>.mp4" --out "_pauses" [--preview]
      Moves each edge to the quietest point within 0.12 s (the gap between two words), removes the spans and
      writes <edited>_tight.mp4 at full quality + report.md.

OTHER WAY (an export with real silent gaps):

  python pauses.py find  "<edited>.mp4" --out "_pauses"
      Finds every dip in the voice (measured against the loudness AROUND it, so a noisy or denoised export
      still shows its gaps) and writes _pauses/candidates.json + candidates.md: id, start, end, length.

  (the agent listens to each candidate and writes _pauses/decisions.json:
      {"decisions": [{"id": 12, "action": "join"}, {"id": 13, "action": "shrink"}, {"id": 14, "action": "keep"}]}
   join   = the pause is inside one sentence / phrase: close it to --join-gap (default 0.10 s)
   shrink = between two sentences of the same paragraph: shorten it to --shrink-gap (default 0.25 s)
   keep   = leave it (end of a paragraph, a deliberate beat, a laugh, a reaction)
   An id that is not listed is kept.)

  python pauses.py apply "<edited>.mp4" --out "_pauses" [--preview]
      Writes <edited>_tight.mp4 at full quality, removed.json (what went, in source seconds), report.md,
      and with --preview a light 720p copy.

Needs Python 3.9+, numpy, ffmpeg/ffprobe on PATH. Fails loudly; never cuts a word on its own: it only removes
time inside a measured dip, keeping a margin of voice tail and breath-in on both sides.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

SR = 16000
HOP = 0.01


def die(m: str) -> None:
    sys.exit(f"STOP: {m}")


def run(cmd: list[str]) -> bytes:
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        die(f"{cmd[0]} failed: {p.stderr.decode(errors='replace')[-800:]}")
    return p.stdout


def fps_of(v: Path) -> Fraction:
    st = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=avg_frame_rate,r_frame_rate", "-of", "json", str(v)]))["streams"][0]
    f = Fraction(st.get("avg_frame_rate") or st["r_frame_rate"])
    for std in (Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                Fraction(50), Fraction(60000, 1001), Fraction(60)):
        if abs(float(f - std)) < 0.15:
            return std
    return f.limit_denominator(1001)


def envelope(v: Path) -> np.ndarray:
    raw = run(["ffmpeg", "-v", "error", "-i", str(v), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
               "-af", "highpass=f=80,lowpass=f=6000", "-f", "s16le", "-"])
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = int(SR * HOP)
    k = len(a) // n
    db = 20 * np.log10(np.sqrt((a[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)
    return np.convolve(db, np.ones(3) / 3, mode="same")


def rolling_pct(x: np.ndarray, win: int, q: float, step: int = 10) -> np.ndarray:
    idx = np.arange(0, len(x), step)
    vals = np.array([np.percentile(x[max(0, i - win // 2): i + win // 2 + 1], q) for i in idx])
    return np.interp(np.arange(len(x)), idx, vals)


def find(a) -> None:
    env = envelope(a.video)
    floor = rolling_pct(env, int(4 / HOP), 5)
    talk = rolling_pct(env, int(4 / HOP), 90)
    span = np.maximum(talk - floor, 1e-3)
    quiet = (env < floor + a.depth * span) & (env < talk - a.min_drop_db)
    cands, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            s, e = i * HOP, j * HOP
            if e - s >= a.min_gap:
                cands.append({"start": round(s, 2), "end": round(e, 2), "length": round(e - s, 2),
                              "drop_db": round(float(np.median(talk[i:j]) - np.median(env[i:j])), 1)})
            i = j
        else:
            i += 1
    for k, c in enumerate(cands, 1):
        c["id"] = k
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "candidates.json").write_text(json.dumps({"video": a.video.name, "candidates": cands},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Pause candidates in {a.video.name}", "",
          f"{len(cands)} dips of at least {a.min_gap:.2f} s. Listen to each one (2 s before to 2 s after) and decide.",
          "", "| id | start | end | length s | mm:ss |", "|---|---|---|---|---|"]
    md += [f"| {c['id']} | {c['start']:.2f} | {c['end']:.2f} | {c['length']:.2f} | "
           f"{int(c['start'] // 60)}:{c['start'] % 60:05.2f} |" for c in cands]
    (a.out / "candidates.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    hist = np.histogram([c["length"] for c in cands], bins=[0, .25, .4, .7, 1.5, 99])[0]
    print(f"{len(cands)} candidates  (<0.25s {hist[0]} | 0.25-0.4 {hist[1]} | 0.4-0.7 {hist[2]} | "
          f"0.7-1.5 {hist[3]} | >1.5 {hist[4]}) -> {a.out}")


def apply(a) -> None:
    cj, dj = a.out / "candidates.json", a.out / "decisions.json"
    for p in (a.video, cj, dj):
        if not p.exists():
            die(f"file not found: {p}")
    cands = {c["id"]: c for c in json.loads(cj.read_text(encoding="utf-8"))["candidates"]}
    dec = json.loads(dj.read_text(encoding="utf-8")).get("decisions") or die("decisions.json has no decisions")
    fps = fps_of(a.video)
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(a.video)]))
    cut, notes = [], []
    for d in dec:
        c = cands.get(d.get("id"))
        if c is None:
            die(f"decision for unknown candidate id {d.get('id')}")
        act = d.get("action", "keep")
        if act == "keep":
            continue
        if act not in ("join", "shrink"):
            die(f"candidate {c['id']}: action must be join, shrink or keep (got {act})")
        leave = a.join_gap if act == "join" else a.shrink_gap
        if c["length"] <= leave + 0.04:
            continue
        # keep the voice tail on the left and the breath-in on the right; remove the middle of the dip
        tail = min(leave * 0.45, 0.06)
        s, e = c["start"] + tail, c["end"] - (leave - tail)
        fs, fe = int(round(s * fps)), int(round(e * fps))
        if fe - fs >= 2:
            cut.append((fs, fe))
            notes.append((c["id"], act, c["start"], c["end"], (fe - fs) / fps))
    cut.sort()
    keep, pos = [], 0
    for fs, fe in cut:
        if fs > pos:
            keep.append((pos, fs))
        pos = max(pos, fe)
    last = int(dur * fps)
    if pos < last:
        keep.append((pos, last))
    removed = float(sum(fe - fs for fs, fe in cut) / fps)

    stem = a.video.stem
    tight = a.out / f"{stem}_tight.mp4"
    lst = a.out / "_keep.ffconcat"
    src = a.video.resolve().as_posix().replace("'", r"'\''")
    lst.write_text("ffconcat version 1.0\n" + "".join(
        f"file '{src}'\ninpoint {float(x / fps):.5f}\noutpoint {float(y / fps):.5f}\n" for x, y in keep), encoding="utf-8")
    print(f"removing {len(cut)} pauses, {removed:.1f} s; writing {tight.name} (full quality, takes a while)")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", f"fps={float(fps):.5f}", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "256k", "-ar", "48000", str(tight)])
    if a.preview:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(tight), "-vf", "scale=-2:720", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "128k", str(a.out / f"{stem}_tight_preview.mp4")])
    lst.unlink()
    (a.out / "removed.json").write_text(json.dumps(
        {"fps": str(fps), "removed": [{"id": i, "action": k, "dip": [s, e], "removed_s": round(float(r), 3)}
                                      for i, k, s, e, r in notes]}, indent=1), encoding="utf-8")
    new_dur = dur - removed
    md = [f"# Pauses removed from {a.video.name}", "",
          f"{len(cut)} pauses, {removed:.1f} s removed: {dur / 60:.2f} min -> {new_dur / 60:.2f} min.", "",
          "| id | action | dip in source | removed s |", "|---|---|---|---|"]
    md += [f"| {i} | {k} | {s:.2f}–{e:.2f} | {r:.2f} |" for i, k, s, e, r in notes]
    (a.out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"done: {tight}")


def prep(a) -> None:
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(a.video)]))
    d = a.out / "chunks"
    d.mkdir(parents=True, exist_ok=True)
    font = a.font or next((f for f in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
                                       "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                                       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if Path(f).exists()), None)
    if not font:
        die("no font found for the burned-in clock; pass --font <path to a .ttf>")
    ff = font.replace("\\", "/").replace(":", "\\:")
    n, t = 0, 0.0
    while t < dur - 0.5:
        n += 1
        out = d / f"chunk_{n:03d}_{int(t // 60):02d}m{int(t % 60):02d}s.mp4"
        clock = (f"drawtext=fontfile='{ff}':text='%{{eif\\:(t+{t:.3f})\\:d}}.%{{eif\\:mod((t+{t:.3f})*100\\,100)\\:d\\:2}}':"
                 "x=w-tw-24:y=24:fontsize=54:fontcolor=yellow:box=1:boxcolor=black@0.7:boxborderw=10")
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-t", f"{a.chunk + 1:.3f}", "-i", str(a.video),
             "-vf", f"scale=-2:540,setpts=PTS-STARTPTS,{clock}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
             "-c:a", "aac", "-b:a", "128k", str(out)])
        t += a.chunk
    print(f"{n} chunks of {a.chunk:.0f} s (1 s overlap) with the source clock burned in -> {d}")


def cut(a) -> None:
    rj = a.out / "remove.json"
    for p in (a.video, rj):
        if not p.exists():
            die(f"file not found: {p}")
    spans = json.loads(rj.read_text(encoding="utf-8")).get("remove")
    if spans is None:
        die("remove.json has no 'remove' list")
    fps = fps_of(a.video)
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(a.video)]))
    env = envelope(a.video)
    w = int(a.snap / HOP)

    def quietest(t: float) -> float:
        i = int(t / HOP)
        lo, hi = max(0, i - w), min(len(env), i + w + 1)
        return (lo + int(np.argmin(env[lo:hi]))) * HOP

    cutf, notes = [], []
    for k, r in enumerate(sorted(spans, key=lambda r: r["start"]), 1):
        s0, e0 = float(r["start"]), float(r["end"])
        if not (0 <= s0 < e0 <= dur + 0.2):
            die(f"span {k} ({s0}-{e0}) is outside the video or reversed")
        if e0 - s0 > 4:
            die(f"span {k} ({s0}-{e0}) is longer than 4 s: that is not a pause; check it")
        s, e = quietest(s0) + a.margin, quietest(e0) - a.margin
        fs, fe = int(round(s * fps)), int(round(e * fps))
        flag = ""
        if abs(s - s0) > a.snap * 0.9 or abs(e - e0) > a.snap * 0.9:
            flag = "edge moved to the limit: listen"
        if fe - fs < 2:
            notes.append((k, r, s0, e0, 0.0, "too short after snapping: kept"))
            continue
        cutf.append((fs, fe))
        notes.append((k, r, s, e, (fe - fs) / fps, flag))
    cutf.sort()
    keep, pos = [], 0
    for fs, fe in cutf:
        if fs > pos:
            keep.append((pos, fs))
        pos = max(pos, fe)
    end_f = int((min(dur, a.until) if a.until else dur) * fps)
    if pos < end_f:
        keep.append((pos, end_f))
    keep = [(x, min(y, end_f)) for x, y in keep if x < end_f]
    removed = float(sum(fe - fs for fs, fe in cutf) / fps)
    tight = a.out / f"{a.video.stem}_tight.mp4"
    lst = a.out / "_keep.ffconcat"
    src = a.video.resolve().as_posix().replace("'", r"'\''")
    lst.write_text("ffconcat version 1.0\n" + "".join(
        f"file '{src}'\ninpoint {float(x / fps):.5f}\noutpoint {float(y / fps):.5f}\n" for x, y in keep), encoding="utf-8")
    print(f"removing {len(cutf)} spans, {removed:.1f} s; writing {tight.name} (full quality, takes a while)")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", f"fps={float(fps):.5f}", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "256k", "-ar", "48000", str(tight)])
    lst.unlink()
    if a.preview:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(tight), "-vf", "scale=-2:720", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "128k", str(a.out / f"{a.video.stem}_tight_preview.mp4")])
    md = [f"# Spans removed from {a.video.name}", "",
          f"{len(cutf)} spans, {removed:.1f} s removed: {dur / 60:.2f} min -> {(dur - removed) / 60:.2f} min.", "",
          "| # | agent span | cut (after snapping) | removed s | what | words | check |", "|---|---|---|---|---|---|---|"]
    md += [f"| {k} | {float(r['start']):.2f}–{float(r['end']):.2f} | {s:.2f}–{e:.2f} | {x:.2f} | {r.get('what', '')} | "
           f"{r.get('before', '')} … {r.get('after', '')} | {f} |" for k, r, s, e, x, f in notes]
    (a.out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"done: {tight}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("video", type=Path)
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--min-gap", type=float, default=0.18, help="shortest dip worth listing (s)")
    f.add_argument("--depth", type=float, default=0.35, help="how far down from speech to the local floor")
    f.add_argument("--min-drop-db", type=float, default=10.0, help="a dip must be at least this far below speech")
    p = sub.add_parser("apply")
    p.add_argument("video", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--join-gap", type=float, default=0.10)
    p.add_argument("--shrink-gap", type=float, default=0.25)
    p.add_argument("--preview", action="store_true")
    q = sub.add_parser("prep")
    q.add_argument("video", type=Path)
    q.add_argument("--out", type=Path, required=True)
    q.add_argument("--chunk", type=float, default=20.0)
    q.add_argument("--font", help="a .ttf for the burned-in clock (found automatically on Windows/macOS)")
    c = sub.add_parser("cut")
    c.add_argument("video", type=Path)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--snap", type=float, default=0.12, help="how far an edge may move to the quietest point (s)")
    c.add_argument("--margin", type=float, default=0.03, help="kept on each side of the cut (s)")
    c.add_argument("--preview", action="store_true")
    c.add_argument("--until", type=float, help="test: only write the first N seconds of the source")
    a = ap.parse_args(argv)
    if not a.video.exists():
        die(f"file not found: {a.video}")
    {"find": find, "apply": apply, "prep": prep, "cut": cut}[a.cmd](a)


if __name__ == "__main__":
    main()
