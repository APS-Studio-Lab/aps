"""Full breaks: intro, chapter cards and outro that STOP the episode, play with their own sound, then cut back.

The presenter's voice never plays under a break. Each break is placed at the end of a spoken phrase (or a time),
rendered as an insert over its moving clip, given its own audio (a music cue, the clip's own sound, or silence),
and spliced into the finished program, video and audio together.

Job YAML:
  breaks:
    - insert: intro            # any graphics/inserts type (intro, chapter_card, outro)
      after_phrase: "ودي حواديت بيزنس"   # or at_s: 12.3, or at: end
      seconds: 7
      bg_video: ../00_Brand/archive/motion/book.mp4
      audio: ../00_Brand/audio/track.mp3   # or "clip" for the bg clip's own sound; omit for silence
      audio_start: 0                       # seconds into the audio file
      audio_gain_db: -2
      fade_in_s: 0.4
      fade_out_s: 1.2
      before_phrase: "..."     # or: cut in just before these words (the line the presenter comes back on)
      skip_to_phrase: "..."    # optional: the break replaces the program up to these words (a line it says instead)
      pad_s: 0.25              # air after the last word / before the next word
      ...insert data (logo, episode, title, number, line, stamp, place, bg_shift, bg_soft)
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .util import FPS, StageError

KEYS = ("insert", "cut", "snap", "after_phrase", "before_phrase", "skip_to_phrase", "at_s", "at", "seconds", "audio", "audio_start",
        "audio_gain_db", "fade_in_s", "fade_out_s", "pad_s", "near_s")


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        raise StageError("break audio/splice failed: " + p.stderr.decode(errors="replace")[-500:])


def _with_audio(video: Path, b: dict, bg: Path | None, out: Path) -> Path:
    """Give a rendered break its own sound track (48 kHz stereo), exactly as long as the picture."""
    secs = float(b["seconds"])
    fi, fo = float(b.get("fade_in_s", 0.3)), float(b.get("fade_out_s", 0.8))
    gain = float(b.get("audio_gain_db", 0))
    src = b.get("audio")
    if src == "clip":
        if not bg:
            raise StageError("break audio 'clip' needs a bg_video")
        src = bg
        b = dict(b, audio_start=b.get("audio_start", b.get("bg_start", 0)))
    if src:
        src = Path(src)
        if not src.exists():
            raise StageError(f"break audio not found: {src.name}")
        a_in = ["-ss", f"{float(b.get('audio_start', 0)):.3f}", "-i", str(src)]
    else:
        a_in = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    af = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{secs:.3f},asetpts=PTS-STARTPTS,"
          f"volume={gain}dB,afade=t=in:d={fi:.2f},afade=t=out:st={max(0.0, secs - fo):.3f}:d={fo:.2f},apad[a]")
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video)] + a_in +
         ["-filter_complex", af, "-map", "0:v", "-map", "[a]", "-t", f"{secs:.3f}",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


def _quiet_curve(audio: Path):
    """Loudness of the program in 10 ms steps (dBFS), for placing cuts in the pauses between sentences."""
    with wave.open(str(audio), "rb") as r:
        p = r.getparams()
        x = np.frombuffer(r.readframes(p.nframes), np.int16).reshape(-1, p.nchannels).astype(np.float32).mean(1) / 32768
    hop = p.framerate // 100
    n = len(x) // hop
    rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-10)
    return 20 * np.log10(rms)


def _snap(db, t: float, before: float = 0.9, after: float = 0.5) -> tuple[float, bool]:
    """Move a cut point into the nearest pause (never inside a word). Returns (time, moved)."""
    if t < 0:
        return t, False
    a, b = max(0, int((t - before) * 100)), min(len(db), int((t + after) * 100))
    if b - a < 5:
        return t, False
    w = db[a:b]
    quiet = w < min(-38.0, float(np.percentile(w, 20)) + 6)
    best, best_d = None, 1e9
    i = 0
    while i < len(w):
        if quiet[i]:
            j = i
            while j < len(w) and quiet[j]:
                j += 1
            if j - i >= 8:  # a pause of 80 ms or more
                mid = (a + (i + j) / 2) / 100
                d = abs(mid - t)
                if d < best_d:
                    best, best_d = mid, d
            i = j
        else:
            i += 1
    return (best, True) if best is not None else (t, False)


def _place(b: dict, words, find_phrase) -> tuple[float, float]:
    """(cut-in time, time the program resumes); -1 = after the end."""
    if b.get("at") == "end":
        return -1.0, -1.0
    if "after_phrase" in b or "before_phrase" in b:
        if not words:
            raise StageError("a break placed at a phrase needs the transcript")
        win = {} if b.get("near_s") is None else {"after": float(b["near_s"]) - 25, "before": float(b["near_s"]) + 25}
        if "after_phrase" in b:
            t = find_phrase(words, b["after_phrase"], end=True, **win) + float(b.get("pad_s", 0.25))
        else:
            t = find_phrase(words, b["before_phrase"], **win) - float(b.get("pad_s", 0.25))
    else:
        t = float(b["at_s"])
    t_back = t
    if b.get("skip_to_phrase"):
        t_back = find_phrase(words, b["skip_to_phrase"], after=t, before=t + 60) - float(b.get("pad_s", 0.25))
    return t, max(t, t_back)


def prepare(br, items: list[dict], words: list[dict] | None, find_phrase, base_path, inserts, work: Path,
            report: dict, audio: Path | None = None) -> list[dict]:
    """Render every break (both orientations, with sound). Returns [{t, h, v}] sorted by time; t = -1 means 'end'."""
    out = []
    db = _quiet_curve(audio) if audio and Path(audio).exists() else None
    for i, b in enumerate(items):
        name = b.get("insert") or ("cut" if b.get("cut") else "break")
        try:
            t, t_back = _place(b, words, find_phrase)
        except StageError as e:  # skip only this break, loudly; never guess a position
            report.setdefault("inserts_skipped", []).append(f"break {name}: {e}")
            continue
        if db is not None and b.get("snap", True):  # land in the pause after the sentence, never inside a word
            t0, back0 = t, t_back
            t, moved = _snap(db, t)
            if t_back > t0:
                t_back, _ = _snap(db, back0)
            elif t_back >= 0:
                t_back = t
            if not moved and t >= 0:
                report.setdefault("warnings", []).append(f"break {name} at {t:.2f}s: no pause found nearby, cut as placed")
        if b.get("cut"):  # a repeated take to drop: no card, the program just skips ahead
            out.append({"t": t, "back": max(t, t_back), "h": None, "v": None, "kind": "cut", "seconds": 0.0})
            report.setdefault("cuts", {})[f"{t:7.2f}s"] = f"removed {max(0.0, t_back - t):.2f}s"
            continue
        data = {k: v for k, v in b.items() if k not in KEYS}
        bg = None
        for key in ("logo", "bg_video", "image", "photo"):
            if data.get(key) and not str(data[key]).startswith(("http", "data:", "file:")):
                f = base_path(data[key])
                if not f.exists():
                    raise StageError(f"break {i} ({b['insert']}): file not found: {f.name}")
                if key == "bg_video":
                    bg = f
                data[key] = f.resolve().as_uri()
        if b.get("bg_start") is not None:
            data["bg_start"] = b["bg_start"]
        if b.get("audio") and b["audio"] != "clip":
            b = dict(b, audio=str(base_path(b["audio"])))
        h, v = inserts.render(br, b["insert"], data, float(b["seconds"]), work, f"brk{i}")
        h = _with_audio(h, b, bg, work / f"break{i}_h.mp4")
        v = _with_audio(v, b, bg, work / f"break{i}_v.mp4") if v is not None else None
        out.append({"t": t, "back": max(t, t_back), "h": h, "v": v, "kind": b["insert"], "seconds": float(b["seconds"])})
        report.setdefault("breaks", {})["end" if t < 0 else f"{t:7.2f}s"] = f"{b['insert']} ({float(b['seconds']):.1f}s)"
    return sorted(out, key=lambda x: (x["t"] < 0, x["t"]))


def splice(src: Path, audio: Path, breaks: list[dict], tag: str, w: int, h: int, out: Path, vcodec: list[str],
           post_vf: str = ""):
    """program video + its master audio, with each break cut in at its time (video and audio together)."""
    ins = ["-i", str(src), "-i", str(audio)]
    inp = {}
    for j, b in enumerate(breaks):
        if b[tag] is not None:
            inp[j] = 2 + len(inp)
            ins += ["-i", str(b[tag])]
    norm_v = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p"
    norm_a = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True).stdout.strip())
    fc, segs, prev = [], [], 0.0
    cuts = [b["t"] for b in breaks if b["t"] >= 0]
    n_src = len(cuts) + 1
    fc.append(f"[0:v]{norm_v},split={n_src}" + "".join(f"[sv{k}]" for k in range(n_src)))
    fc.append(f"[1:a]{norm_a},apad,asplit={n_src}" + "".join(f"[sa{k}]" for k in range(n_src)))
    k = 0
    for j, b in enumerate(breaks):
        if b["t"] < 0:
            continue
        fc.append(f"[sv{k}]trim={prev:.3f}:{b['t']:.3f},setpts=PTS-STARTPTS[v{k}]")
        fc.append(f"[sa{k}]atrim={prev:.3f}:{b['t']:.3f},asetpts=PTS-STARTPTS[a{k}]")
        segs.append(f"[v{k}][a{k}]")
        if b[tag] is not None:
            fc.append(f"[{inp[j]}:v]{norm_v}[bv{j}]")
            fc.append(f"[{inp[j]}:a]{norm_a}[ba{j}]")
            segs.append(f"[bv{j}][ba{j}]")
        prev, k = b.get("back", b["t"]), k + 1
    fc.append(f"[sv{k}]trim={prev:.3f}:{dur:.3f},setpts=PTS-STARTPTS[v{k}]")
    # the program's own audio is padded with silence: cut it to the picture's length
    fc.append(f"[sa{k}]atrim={prev:.3f}:{dur:.3f},asetpts=PTS-STARTPTS[a{k}x]")
    segs.append(f"[v{k}][a{k}x]")
    for j, b in enumerate(breaks):
        if b["t"] < 0 and b[tag] is not None:
            fc.append(f"[{inp[j]}:v]{norm_v}[bv{j}]")
            fc.append(f"[{inp[j]}:a]{norm_a}[ba{j}]")
            segs.append(f"[bv{j}][ba{j}]")
    fc.append("".join(segs) + f"concat=n={len(segs)}:v=1:a=1[vc][ao]")
    fc.append(f"[vc]{post_vf or 'null'}[vo]")
    # the breaks' music and the program were levelled apart: a final limiter keeps true peaks under -1 dBTP
    fc[-2] = fc[-2].replace("[vc][ao]", "[vc][am]")
    fc.append("[am]alimiter=limit=0.79:level=false:attack=2:release=60,aresample=48000[ao]")
    _run(["ffmpeg", "-v", "error", "-y"] + ins + ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]"]
         + vcodec + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    return out
