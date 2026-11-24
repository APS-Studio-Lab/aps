"""Joins: find every cut in the programme and plan how to hide it.

A join is any point where two pieces of the presenter's footage meet: a cut made by this pipeline
(non-consecutive source frames) or a cut already inside a pre-edited export (Filmora), found by a
spike in frame difference.

Each join gets:
- alternating framing (wide / close punch-in, anchored on the face) so the jump reads as a camera change;
- a severity from the pose difference, so large jumps can be covered by an insert;
- a short audio dip-crossfade so no cut clicks.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from .util import FPS, StageError


def frame_scan(mezz: Path, w: int = 192, h: int = 108) -> tuple[np.ndarray, np.ndarray]:
    """Per source frame: luma difference to the previous frame, and the share of the frame that is green screen.

    The green share tells presenter shots (key them) from anything else already inside a pre-edited export
    (logo cards, graphics, B-roll, fades): those pass through untouched.
    """
    import cv2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(mezz), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    size, prev, diff, green = w * h * 3, None, [], []
    while True:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        f = np.frombuffer(b, np.uint8).reshape(h, w, 3)
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        diff.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        green.append(float(((hsv[..., 0] > 35) & (hsv[..., 0] < 90) & (hsv[..., 1] > 60) & (hsv[..., 2] > 40)).mean()))
    p.wait()
    if not diff:
        raise StageError("could not decode the mezzanine for cut detection")
    return np.array(diff, np.float32), np.array(green, np.float32)


def screen_frames(green: np.ndarray, on: float = 0.25, hold: int = 3) -> np.ndarray:
    """True where the frame is a green-screen presenter shot. Short flickers are smoothed out."""
    raw = green > on
    out = raw.copy()
    for i in range(len(raw)):  # a frame counts only if the frames around it agree (no single-frame flips)
        lo, hi = max(0, i - hold), min(len(raw), i + hold + 1)
        out[i] = raw[lo:hi].mean() > 0.5
    return out


def source_cuts(diff: np.ndarray, track: np.ndarray, min_gap: int = 6) -> list[int]:
    """Frames where a hard cut starts inside the source: an isolated diff spike or a face-position jump."""
    n = len(diff)
    cuts = []
    for i in range(1, n - 1):
        lo, hi = max(0, i - 15), min(n, i + 16)
        local = np.median(diff[lo:hi]) + 1e-3
        neigh = max(diff[i - 1], diff[i + 1])
        spike = diff[i] > max(3.5 * local, 2.0) and diff[i] > 1.8 * neigh
        jump = False
        if i < len(track) and track[i, 4] > 0 and track[i - 1, 4] > 0:
            fw = max(track[i, 2], 1.0)
            d = (abs(track[i, 0] - track[i - 1, 0]) + abs(track[i, 1] - track[i - 1, 1])) / fw
            jump = d > 0.12 and diff[i] > 1.5 * local
        if (spike or jump) and (not cuts or i - cuts[-1] >= min_gap):
            cuts.append(i)
    return cuts


def plan(frames: list[int], track: np.ndarray, diff: np.ndarray | None, cfg: dict) -> tuple[np.ndarray, list[dict]]:
    """Return per-output-frame framing [zoom, cx, cy] (source pixels) and the list of joins.

    frames: source frame for each output frame, in order.
    """
    n = len(frames)
    inner = set(source_cuts(diff, track)) if diff is not None else set()
    joins = []
    for k in range(1, n):
        a, b = frames[k - 1], frames[k]
        if b != a + 1 or b in inner:
            joins.append(k)

    # Framing: a straight cut by default. A small punch-in (or back out) only at a cut where the body really
    # jumps, and never sooner than min_gap_s after the previous framing change. Frequent zooms distract.
    z_close = float(cfg.get("punch_in", 1.06))
    min_gap = int(float(cfg.get("min_gap_s", 12)) * FPS)
    big = float(cfg.get("jump_threshold", 0.15))
    min_seg = int(float(cfg.get("min_segment_s", 0.8)) * FPS)
    bounds = [0] + joins + [n]
    framing = np.zeros((n, 3), np.float32)
    zoom, last_change = 1.0, -10 ** 9
    for s, e in zip(bounds, bounds[1:]):
        src = [frames[k] for k in range(s, e)]
        ok = [f for f in src if track[f, 4] > 0]
        cx = float(np.median(track[ok, 0])) if ok else 960.0
        cy = float(np.median(track[ok, 1])) if ok else 400.0
        if s > 0:
            a, b = frames[s - 1], frames[s]
            if track[a, 4] > 0 and track[b, 4] > 0:
                fw = max((track[a, 2] + track[b, 2]) / 2, 1.0)
                d = (abs(track[a, 0] - track[b, 0]) + abs(track[a, 1] - track[b, 1]) + abs(track[a, 2] - track[b, 2])) / fw
                if d >= big and s - last_change >= min_gap and e - s >= min_seg:
                    zoom = z_close if zoom == 1.0 else 1.0
                    last_change = s
        framing[s:e] = (zoom, cx, cy)
    out = []
    for k in joins:
        a, b = frames[k - 1], frames[k]
        sev, d = "unknown", None
        if track[a, 4] > 0 and track[b, 4] > 0:
            fw = max((track[a, 2] + track[b, 2]) / 2, 1.0)
            d = (abs(track[a, 0] - track[b, 0]) + abs(track[a, 1] - track[b, 1]) + abs(track[a, 2] - track[b, 2])) / fw
            sev = "small" if d < 0.06 else "medium" if d < 0.15 else "large"
        i = bounds.index(k)
        seg_before, seg_after = k - bounds[i - 1], bounds[i + 1] - k
        out.append({"t": round(k / FPS, 2), "severity": sev, "pose_delta": None if d is None else round(d, 3),
                    "short_segment": bool(min(seg_before, seg_after) < min_seg),
                    "treatment": ("framing change" if framing[k][0] != framing[k - 1][0] else "straight cut")
                    + (" + overlay cover suggested" if sev == "large" and framing[k][0] == framing[k - 1][0] else "")})
    return framing, out


def soften_audio(wav: Path, join_times: list[float], ms: float = 12.0) -> None:
    """Dip the level for a few ms around every join so a hard audio cut never clicks."""
    import wave
    if not join_times:
        return
    with wave.open(str(wav), "rb") as r:
        params = r.getparams()
        data = np.frombuffer(r.readframes(params.nframes), np.int16).reshape(-1, params.nchannels).astype(np.float32)
    sr, half = params.framerate, int(params.framerate * ms / 1000)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, half))
    env = np.ones(len(data), np.float32)
    for t in join_times:
        c = int(t * sr)
        lo, hi = max(0, c - half), min(len(data), c + half)
        if hi - lo < 2 * half:
            continue
        env[lo:c] = np.minimum(env[lo:c], ramp[::-1] * 0.85 + 0.15)
        env[c:hi] = np.minimum(env[c:hi], ramp * 0.85 + 0.15)
    out = np.clip(data * env[:, None], -32768, 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())


def tighten(program_wav: Path, n_frames: int, cuts: list[int], cfg: dict) -> tuple[list[tuple[int, int]], float]:
    """Shorten the dead pause around each existing cut of a pre-edited export, so sentences run on into a
    paragraph. Only silences that contain a cut are touched: trimming inside a continuous take would add a jump."""
    import wave
    max_pause = float(cfg.get("max_pause_s", 0.35))
    keep = float(cfg.get("keep_pause_s", 0.16))
    with wave.open(str(program_wav), "rb") as r:
        sr, ch = r.getframerate(), r.getnchannels()
        x = np.frombuffer(r.readframes(r.getnframes()), np.int16).reshape(-1, ch).astype(np.float32).mean(1) / 32768
    hop = sr // FPS
    m = min(n_frames, len(x) // hop)
    rms = np.sqrt((x[:m * hop].reshape(m, hop) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 10)
    quiet = db < max(floor + 10, np.percentile(db, 35) - 6)
    drop = np.zeros(n_frames, bool)
    removed = 0
    # flash frames: a sliver of 1-2 frames between two cuts of the export reads as a glitch; drop it
    for c0, c1 in zip(cuts, cuts[1:]):
        if 0 < c1 - c0 <= 2:
            drop[c0:c1] = True
            removed += c1 - c0
    for c in cuts:
        if c >= m or not quiet[min(c, m - 1)] and not quiet[max(c - 1, 0)]:
            continue
        lo = c
        while lo > 0 and quiet[lo - 1]:
            lo -= 1
        hi = c
        while hi < m - 1 and quiet[hi]:
            hi += 1
        span = hi - lo
        if span / FPS <= max_pause:
            continue
        keep_n = int(keep * FPS)
        # keep a little air on both sides of the cut; drop the middle of the silence
        a0, a1 = lo + keep_n // 2, hi - (keep_n - keep_n // 2)
        # the dropped span must swallow the cut itself, or the edit shows two jumps a few frames apart
        a0, a1 = min(a0, c), max(a1, c + 1)
        if a1 > a0:
            drop[a0:a1] = True
            removed += a1 - a0
    takes, start = [], None
    for f in range(n_frames):
        if not drop[f] and start is None:
            start = f
        if drop[f] and start is not None:
            takes.append((start, f - 1)); start = None
    if start is not None:
        takes.append((start, n_frames - 1))
    return takes, removed / FPS


def word_times(program_wav: Path, t0: float, t1: float, model_size: str = "large-v3") -> list[tuple[float, float]]:
    """Word start/end times (source seconds) in [t0, t1], from Whisper's word timestamps. Runs on the
    render machine, no API quota. Only the timing is used here, never the text."""
    import subprocess
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(program_wav),
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(np.frombuffer(pcm, np.float32), language="ar", word_timestamps=True,
                               vad_filter=True, vad_parameters={"min_silence_duration_ms": 250, "speech_pad_ms": 150},
                               condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                out.append((t0 + float(w.start), t0 + float(w.end)))
    return out


def tighten_words(program_wav: Path, n_frames: int, words: list[tuple[float, float]], cfg: dict,
                  t0: float = 0.0, t1: float | None = None) -> tuple[list[tuple[int, int]], float, dict]:
    """Keep every word (with a little air around it) and remove the dead air between words and sentences.
    Anything loud that Whisper did not mark as a word is kept too, so a missed word is never cut."""
    import wave
    pre, post = float(cfg.get("word_pre_s", 0.05)), float(cfg.get("word_post_s", 0.09))
    in_gap = float(cfg.get("word_gap_s", 0.05))        # pause kept between words of one sentence
    sent_gap = float(cfg.get("sentence_gap_s", 0.20))  # pause kept between sentences
    sent_min = float(cfg.get("sentence_break_s", 0.6)) # an original pause this long marks a sentence break
    f0 = int(t0 * FPS)
    f1 = n_frames - 1 if t1 is None else min(n_frames - 1, int(t1 * FPS))
    keep = np.zeros(n_frames, bool)
    for s, e in words:
        keep[max(f0, int((s - pre) * FPS)):min(f1 + 1, int(np.ceil((e + post) * FPS)))] = True
    # safety net: loud frames the word list missed (numbers, names Whisper skipped) stay in
    with wave.open(str(program_wav), "rb") as r:
        sr, ch = r.getframerate(), r.getnchannels()
        x = np.frombuffer(r.readframes(r.getnframes()), np.int16).reshape(-1, ch).astype(np.float32).mean(1) / 32768
    hop = sr // FPS
    m = min(n_frames, len(x) // hop)
    db = 20 * np.log10(np.sqrt((x[:m * hop].reshape(m, hop) ** 2).mean(1) + 1e-12))
    seg = db[f0:min(f1 + 1, m)]
    loud = np.zeros(n_frames, bool)
    if len(seg):
        thr = np.percentile(seg, 15) + 0.55 * (np.percentile(seg, 90) - np.percentile(seg, 15))
        loud[f0:f0 + len(seg)] = seg > thr
        loud = cv2.dilate(loud.astype(np.uint8)[None], np.ones((1, 7), np.uint8))[0].astype(bool)
    keep |= loud & (np.arange(n_frames) >= f0) & (np.arange(n_frames) <= f1)
    # now shrink every gap between kept stretches to the pause it deserves
    takes, k, removed = [], f0, 0
    runs = []
    while k <= f1:
        if keep[k]:
            s = k
            while k <= f1 and keep[k]:
                k += 1
            runs.append([s, k - 1])
        else:
            k += 1
    if not runs:
        return [(f0, f1)], 0.0, {"words": len(words)}
    merged = [runs[0]]
    for s, e in runs[1:]:
        gap = (s - merged[-1][1] - 1) / FPS
        want = sent_gap if gap >= sent_min else in_gap
        if gap <= want + 1 / FPS:
            merged[-1][1] = e          # short enough: keep the pause as it is, no cut
        else:
            extra = int(round(want * FPS))
            merged[-1][1] += extra // 2   # air after the last word ...
            s -= extra - extra // 2       # ... and before the next
            removed += gap - want
            merged.append([s, e])
    takes = [(a, b) for a, b in merged]
    return takes, removed, {"words": len(words), "cuts": len(takes) - 1}


def snap_window(words: list[tuple[float, float]], t0: float, t1: float, min_pause: float = 0.4) -> tuple[float, float]:
    """Move a preview window's ends into pauses, so it never starts or ends in the middle of a word."""
    gaps = [(a_end, b_start) for (_, a_end), (b_start, _) in zip(words, words[1:]) if b_start - a_end >= min_pause]
    s = next(((a + b) / 2 for a, b in gaps if t0 <= (a + b) / 2 <= t0 + 10), t0)
    e = next(((a + b) / 2 for a, b in gaps if t1 <= (a + b) / 2 <= t1 + 10), t1)
    return s, max(e, s + 5)
