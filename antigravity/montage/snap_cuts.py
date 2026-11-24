#!/usr/bin/env python3
"""Turn a take list (takes.json, written by the montage agent) into frame-exact cuts.

The agent's times say WHICH take and roughly where; they can drift by a second. This script moves every
cut to the real edge of speech in the voice audio, so a cut never clips a word and never sits on a
dead pause. Outputs, all in --out:
  cuts.json         final cuts (video seconds, frame-aligned)
  cuts_report.md    every cut, how far it moved, and anything that needs a human look
  timeline.fcpxml   import into DaVinci Resolve: File > Import > Timeline
  preview.mp4       (with --preview) light 720p review copy, colours not graded

Needs only Python 3.9+, numpy, and ffmpeg/ffprobe on PATH.
Fails loudly: if a file is missing or a cut cannot be placed it says so; it never invents a cut.
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
HOP = 0.01  # 10 ms analysis frames


def die(msg: str) -> None:
    sys.exit(f"STOP: {msg}")


def run(cmd: list[str]) -> bytes:
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        die(f"{cmd[0]} failed: {p.stderr.decode(errors='replace')[-800:]}")
    return p.stdout


def probe_fps(video: Path) -> Fraction:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=avg_frame_rate,r_frame_rate", "-of", "json", str(video)])
    st = json.loads(out)["streams"][0]
    fps = Fraction(st.get("avg_frame_rate") or st["r_frame_rate"])
    # phone footage is variable frame rate; snap to the standard rate it is closest to
    for std in (Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                Fraction(50), Fraction(60000, 1001), Fraction(60)):
        if abs(float(fps - std)) < 0.15:
            return std
    return fps.limit_denominator(1001)


def duration(p: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


def load_audio(p: Path) -> np.ndarray:
    raw = run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
               "-f", "s16le", "-"])
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def envelope_db(a: np.ndarray) -> np.ndarray:
    n = int(SR * HOP)
    k = len(a) // n
    rms = np.sqrt(np.mean(a[: k * n].reshape(k, n) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


def find_offset(video_env: np.ndarray, voice_env: np.ndarray, span_s: float = 240) -> tuple[float, float]:
    """voice_time = video_time + offset. Cross-correlates the loudness envelopes."""
    m = int(span_s / HOP)
    a = video_env[:m] - video_env[:m].mean()
    b = voice_env[: m * 2] - voice_env[: m * 2].mean()
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    xc = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    lags = np.r_[np.arange(0, len(b)), np.arange(-len(a) + 1, 0)]
    vals = np.r_[xc[: len(b)], xc[n - len(a) + 1:]]
    lag = int(lags[int(np.argmax(vals))])
    lo_b, hi_b = max(0, lag), min(len(b), lag + len(a))
    x, y = a[lo_b - lag: hi_b - lag], b[lo_b:hi_b]
    if len(x) < len(a) // 3:
        return 0.0, 0.0
    c = float(np.dot(x - x.mean(), y - y.mean()) / (np.std(x) * np.std(y) * len(x) + 1e-9))
    return lag * HOP, c


def speech_mask(env: np.ndarray) -> tuple[np.ndarray, float]:
    floor = float(np.percentile(env, 10))
    peak = float(np.percentile(env, 95))
    thr = max(floor + 0.35 * (peak - floor), floor + 8)
    sp = env > thr
    # close tiny gaps (inside words) and drop tiny blips (clicks)
    def runs(mask, val):
        out, i = [], 0
        while i < len(mask):
            if mask[i] == val:
                j = i
                while j < len(mask) and mask[j] == val:
                    j += 1
                out.append((i, j)); i = j
            else:
                i += 1
        return out
    for i, j in runs(sp, False):
        if (j - i) * HOP < 0.08:
            sp[i:j] = True
    for i, j in runs(sp, True):
        if (j - i) * HOP < 0.05:
            sp[i:j] = False
    return sp, thr


def onset_near(sp: np.ndarray, t: float, before: float, after: float, quiet: float = 0.15) -> float | None:
    """Speech start nearest to t: speech begins after at least `quiet` s of silence."""
    lo, hi = max(1, int((t - before) / HOP)), min(len(sp) - 1, int((t + after) / HOP))
    q = int(quiet / HOP)
    cands = [i for i in range(lo, hi) if sp[i] and not sp[i - 1] and not sp[max(0, i - q):i].any()]
    if not cands:
        return None
    return min(cands, key=lambda i: abs(i * HOP - t)) * HOP


def offset_near(sp: np.ndarray, t: float, before: float, after: float, quiet: float = 0.20) -> float | None:
    """Speech end nearest to t: speech stops and stays silent for at least `quiet` s."""
    lo, hi = max(1, int((t - before) / HOP)), min(len(sp) - 1, int((t + after) / HOP))
    q = int(quiet / HOP)
    cands = [i for i in range(lo, hi) if sp[i - 1] and not sp[i] and not sp[i:i + q].any()]
    if not cands:
        return None
    return min(cands, key=lambda i: abs(i * HOP - t)) * HOP


def inner_pauses(sp: np.ndarray, s: float, e: float, max_pause: float) -> list[tuple[float, float]]:
    lo, hi = int(s / HOP), int(e / HOP)
    out, i = [], lo
    while i < hi:
        if not sp[i]:
            j = i
            while j < hi and not sp[j]:
                j += 1
            if (j - i) * HOP > max_pause and i > lo and j < hi:
                out.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    return out


def fr(t: float, fps: Fraction) -> int:
    return int(round(t * fps))


def rt(frames: int, fps: Fraction) -> str:
    """FCPXML rational time."""
    d = 1 / fps
    v = d * frames
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"


def write_fcpxml(cuts: list[dict], video: Path, voice: Path | None, off: float, fps: Fraction,
                 vdur: float, adur: float, out: Path, name: str) -> None:
    from xml.sax.saxutils import quoteattr as qa
    fd = 1 / fps
    fdur = f"{fd.numerator}/{fd.denominator}s"
    total = sum(c["out_f"] - c["in_f"] for c in cuts)
    L = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.9">', "<resources>",
         f'<format id="r1" frameDuration="{fdur}" width="1920" height="1080"/>',
         f'<asset id="r2" name={qa(video.name)} start="0s" duration="{rt(fr(vdur, fps), fps)}" hasVideo="1" '
         f'hasAudio="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">'
         f'<media-rep kind="original-media" src={qa(video.resolve().as_uri())}/></asset>']
    if voice:
        L.append(f'<asset id="r3" name={qa(voice.name)} start="0s" duration="{rt(fr(adur, fps), fps)}" '
                 f'hasAudio="1" audioSources="1" audioChannels="1" audioRate="48000">'
                 f'<media-rep kind="original-media" src={qa(voice.resolve().as_uri())}/></asset>')
    L += ["</resources>", "<library>", f"<event name={qa(name)}>", f"<project name={qa(name)}>",
          f'<sequence format="r1" duration="{rt(total, fps)}" tcStart="0s" tcFormat="NDF">', "<spine>"]
    pos = 0
    for k, c in enumerate(cuts):
        n = c["out_f"] - c["in_f"]
        L.append(f'<asset-clip name={qa("%03d %s" % (k + 1, c.get("label", "")))} ref="r2" '
                 f'offset="{rt(pos, fps)}" start="{rt(c["in_f"], fps)}" duration="{rt(n, fps)}" format="r1">')
        if voice:
            L.append('<adjust-volume amount="-96dB"/>')
            a_in = fr(c["in_f"] / fps + off, fps)
            if a_in >= 0:
                L.append(f'<asset-clip name="voice" ref="r3" lane="-1" offset="{rt(c["in_f"], fps)}" '
                         f'start="{rt(a_in, fps)}" duration="{rt(n, fps)}"/>')
        L.append("</asset-clip>")
        pos += n
    L += ["</spine>", "</sequence>", "</project>", "</event>", "</library>", "</fcpxml>"]
    out.write_text("\n".join(L), encoding="utf-8")


def write_preview(cuts: list[dict], video: Path, voice: Path | None, off: float, fps: Fraction, out: Path) -> None:
    def lst(path: Path, shift: float) -> str:
        s = "ffconcat version 1.0\n"
        p = path.resolve().as_posix().replace("'", r"'\''")
        for c in cuts:
            a, b = c["in_f"] / fps + shift, c["out_f"] / fps + shift
            s += f"file '{p}'\ninpoint {float(a):.4f}\noutpoint {float(b):.4f}\n"
        return s
    vl, al = out.with_suffix(".v.txt"), out.with_suffix(".a.txt")
    vl.write_text(lst(video, 0.0), encoding="utf-8")
    al.write_text(lst(voice or video, off if voice else 0.0), encoding="utf-8")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vl), "-f", "concat", "-safe", "0",
         "-i", str(al), "-map", "0:v:0", "-map", "1:a:0", "-vf", f"scale=-2:720,fps={float(fps):.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)])
    vl.unlink(); al.unlink()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("takes", type=Path, help="takes.json written by the montage agent")
    ap.add_argument("--video", type=Path, required=True, help="original camera file (not the proxy)")
    ap.add_argument("--audio", type=Path, help="separate voice recording, if there is one")
    ap.add_argument("--offset", type=float, help="voice_time = video_time + offset (found automatically if omitted)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pre", type=float, default=0.10, help="seconds kept before the first word")
    ap.add_argument("--post", type=float, default=0.18, help="seconds kept after the last word")
    ap.add_argument("--max-pause", type=float, default=0.50, help="pauses longer than this inside a take are cut")
    ap.add_argument("--keep-pause", type=float, default=0.18, help="what a cut pause shrinks to")
    ap.add_argument("--no-tighten", action="store_true", help="never cut pauses inside a take")
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args(argv)

    for p in [a.takes, a.video] + ([a.audio] if a.audio else []):
        if not p.exists():
            die(f"file not found: {p}")
    T = json.loads(a.takes.read_text(encoding="utf-8"))
    segs = T.get("segments") or die("takes.json has no segments")
    a.out.mkdir(parents=True, exist_ok=True)

    fps = probe_fps(a.video)
    vdur = duration(a.video)
    print(f"video {fps} fps, {vdur:.1f} s")
    venv = envelope_db(load_audio(a.video))
    off, score, adur = 0.0, None, vdur
    if a.audio:
        voice = load_audio(a.audio)
        adur = len(voice) / SR
        aenv = envelope_db(voice)
        if a.offset is None:
            off, score = find_offset(venv, aenv)
            print(f"voice offset {off:+.2f} s (match {score:.2f})")
            if score < 0.5:
                die(f"could not line up the voice file with the video (match {score:.2f}); pass --offset")
        else:
            off = a.offset
        # analyse speech on the voice track, mapped back to video time
        shift = int(round(off / HOP))
        env = np.full(len(venv), float(np.min(aenv)))
        src = aenv[max(0, shift): max(0, shift) + len(venv) - max(0, -shift)]
        env[max(0, -shift): max(0, -shift) + len(src)] = src
    else:
        env = venv
    sp, thr = speech_mask(env)

    cuts, notes = [], []
    for k, s in enumerate(segs):
        lab = str(s.get("line", k + 1))
        if not (0 <= s["start"] < s["end"] <= vdur + 0.5):
            die(f"segment {lab}: times {s['start']}-{s['end']} are outside the video")
        st = onset_near(sp, s["start"], 1.2, 0.8)
        en = offset_near(sp, s["end"], 0.8, 1.2)
        flag = []
        if st is None:
            st = s["start"] + a.pre; flag.append("no clear speech start near the agent's time; kept as given")
        if en is None:
            en = s["end"] - a.post; flag.append("no clear speech end near the agent's time; kept as given")
        if en <= st:
            die(f"segment {lab}: after snapping, the end is before the start; check its times in takes.json")
        pieces = [(st - a.pre, en + a.post)]
        if not a.no_tighten and not s.get("keep_pauses"):
            pieces, cur = [], st - a.pre
            for p0, p1 in inner_pauses(sp, st, en, a.max_pause):
                pieces.append((cur, p0 + a.keep_pause / 2))
                cur = p1 - a.keep_pause / 2
            pieces.append((cur, en + a.post))
        for n, (x, y) in enumerate(pieces):
            cuts.append({"line": s.get("line"), "label": lab + ("" if len(pieces) == 1 else chr(97 + n)),
                         "in_f": fr(max(0.0, x), fps), "out_f": fr(min(vdur, y), fps)})
        moved = (st - s["start"], en - s["end"])
        if max(abs(moved[0]), abs(moved[1])) > 0.6:
            flag.append(f"moved {moved[0]:+.2f} s / {moved[1]:+.2f} s from the agent's times: check this cut")
        notes.append((lab, s, st, en, len(pieces) - 1, flag))

    # the takes must not overlap each other in the final order
    for c1, c2 in zip(cuts, cuts[1:]):
        if c1["out_f"] > c2["in_f"] and c2["in_f"] >= c1["in_f"]:
            c1["out_f"] = c2["in_f"]
    cuts = [c for c in cuts if c["out_f"] - c["in_f"] >= 3]

    for c in cuts:
        c["in_s"], c["out_s"] = round(float(c["in_f"] / fps), 3), round(float(c["out_f"] / fps), 3)
    (a.out / "cuts.json").write_text(json.dumps({"fps": str(fps), "voice_offset_s": off, "cuts": cuts},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(c["out_f"] - c["in_f"] for c in cuts) / fps
    R = [f"# Cut report", "", f"{len(segs)} script segments, {len(cuts)} clips, {float(total) / 60:.1f} min. "
         f"Speech threshold {thr:.0f} dB. Voice offset {off:+.2f} s.", "",
         "| line | agent in–out | snapped in–out | pauses cut | check |", "|---|---|---|---|---|"]
    for lab, s, st, en, np_, flag in notes:
        R.append(f"| {lab} | {s['start']:.2f}–{s['end']:.2f} | {st:.2f}–{en:.2f} | {np_} | {'; '.join(flag)} |")
    missing = T.get("missing") or []
    if missing:
        R += ["", "## Script lines with no usable take (re-shoot or decide)", ""] + [f"- {m}" for m in missing]
    (a.out / "cuts_report.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    write_fcpxml(cuts, a.video, a.audio, off, fps, vdur, adur, a.out / "timeline.fcpxml",
                 T.get("name", a.video.stem + " rough cut"))
    print(f"{len(cuts)} clips, {float(total) / 60:.1f} min -> {a.out}")
    if a.preview:
        write_preview(cuts, a.video, a.audio, off, fps, a.out / "preview.mp4")
        print("preview.mp4 written")


if __name__ == "__main__":
    main()
