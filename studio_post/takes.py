"""Raw phone clips -> chosen takes -> one assembled video.

    python -m studio_post.takes plan     <clips_dir> <script> <out_dir> [--max-minutes N]
    python -m studio_post.takes assemble <clips_dir> <plan.json> <out.mp4>

plan: transcribes every clip with word timings (Whisper, on this machine), matches each utterance to the
script loosely, and decides per utterance: keep, retake (an earlier attempt of a line said again later),
fragment (false start), meta ("again", "wait") or unscripted (kept, flagged). Writes plan.json and plan.md for
the presenter to approve. Nothing is cut until he does.

assemble: cuts the kept utterances out of the clips (with a little air) and joins them into one file at full
quality, which then goes through the normal pipeline (edit.mode: keep).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from .util import StageError

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}
META = {"تاني", "تانى", "استنى", "استني", "معلش", "ثانية", "ثانيه", "كت", "cut", "اعيد", "هعيد", "نعيد", "اعيدها",
        "مرة", "غلط", "لا لا"}


# ---------- text ----------

def norm(w: str) -> str:
    w = re.sub(r"[ً-ْـ]", "", w)
    w = w.translate(str.maketrans("أإآىةؤئ", "اااىهوي")).replace("ى", "ي")
    w = re.sub(r"[^\w]", "", w.lower())
    for p in ("وال", "بال", "فال", "لل", "ال"):
        if w.startswith(p) and len(w) > len(p) + 2:
            w = w[len(p):]
            break
    if len(w) > 3 and w[0] in "وفب":
        w = w[1:]
    return w[:5]


def script_tokens(path: Path) -> tuple[list[str], list[str], list[int]]:
    """Spoken Arabic lines of the script (stage directions dropped). Returns normalized tokens, raw tokens and
    the line number of each token."""
    if path.suffix.lower() == ".docx":
        import docx  # python-docx
        text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    else:
        text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # the spoken part starts at the script heading when the document also holds research notes
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(Script|السكريبت|سكريبت)\b", ln.strip(), re.I):
            lines = lines[i + 1:]
            break
    nt, rt, li = [], [], []
    for k, ln in enumerate(lines):
        s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", ln)  # (Visual: ...) and [notes]
        if not re.search(r"[؀-ۿ]", s):
            continue
        for tok in s.split():
            n = norm(tok)
            if n:
                nt.append(n); rt.append(tok); li.append(k)
    if len(nt) < 50:
        raise StageError(f"script looks empty or unreadable: {path.name}")
    return nt, rt, li


# ---------- audio / transcription ----------

def clip_list(d: Path) -> list[Path]:
    clips = [p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT]
    if not clips:
        raise StageError(f"no video clips in {d}")

    def when(p: Path):
        try:
            tags = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time",
                                              "-of", "json", str(p)], capture_output=True, text=True).stdout)
            return (tags.get("format", {}).get("tags", {}).get("creation_time") or "", p.name)
        except Exception:
            return ("", p.name)
    return sorted(clips, key=when)


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True, check=True).stdout.strip())


def transcribe_clips(clips: list[Path], work: Path) -> list[dict]:
    """One audio file for all clips (faster than one model pass each), then words mapped back to clips."""
    from faster_whisper import WhisperModel
    work.mkdir(parents=True, exist_ok=True)
    offs, t = [], 0.0
    pcm = []
    for c in clips:
        a = subprocess.run(["ffmpeg", "-v", "error", "-i", str(c), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le",
                            "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(a, np.float32)
        offs.append((t, c))
        pcm.append(x); pcm.append(np.zeros(16000, np.float32))  # 1 s of silence between clips
        t += len(x) / 16000 + 1.0
    audio = np.concatenate(pcm)
    try:
        model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    except Exception:
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language="ar", word_timestamps=True, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 120},
                               condition_on_previous_text=False, beam_size=5)
    words = []
    for s in segs:
        for w in s.words or []:
            if not w.word.strip():
                continue
            ci = max(i for i, (o, _) in enumerate(offs) if o <= w.start)
            o, c = offs[ci]
            words.append({"w": w.word.strip(), "clip": c.name, "ci": ci, "s": round(w.start - o, 3),
                          "e": round(w.end - o, 3), "p": round(w.probability, 3)})
    return words


def utterances(words: list[dict], gap: float = 0.55) -> list[dict]:
    out, cur = [], []
    for w in words:
        if cur and (w["ci"] != cur[-1]["ci"] or w["s"] - cur[-1]["e"] >= gap):
            out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"clip": u[0]["clip"], "ci": u[0]["ci"], "s": u[0]["s"], "e": u[-1]["e"],
             "text": " ".join(w["w"] for w in u), "words": u} for u in out]


# ---------- matching and choosing ----------

def match(utts: list[dict], snt: list[str]) -> None:
    """For each utterance: where in the script it starts (token index), how much of it matches, and the script
    span it covers. Voting on offsets makes this fast and tolerant of skipped or changed words."""
    pos = defaultdict(list)
    for i, t in enumerate(snt):
        pos[t].append(i)
    for u in utts:
        toks = [norm(w["w"]) for w in u["words"]]
        toks = [t for t in toks if t]
        u["n"] = len(toks)
        votes = defaultdict(int)
        for j, t in enumerate(toks):
            for p in pos.get(t, ()):
                votes[p - j] += 1
        if not votes:
            u.update(score=0.0, at=-1, span=(-1, -1)); continue
        # smooth: a skipped or added word shifts the offset by one or two
        best_off, best = max(((o, sum(votes.get(o + d, 0) for d in (-2, -1, 0, 1, 2))) for o in votes),
                             key=lambda x: x[1])
        hit = sorted(p for j, t in enumerate(toks) for p in pos.get(t, ()) if abs(p - j - best_off) <= 2)
        u["score"] = round(min(1.0, best / max(1, len(toks))), 2)
        u["at"] = best_off
        u["span"] = (hit[0], hit[-1]) if hit else (-1, -1)


def decide(utts: list[dict], min_score: float = 0.4) -> None:
    kept = []  # indices of scripted utterances currently kept
    for i, u in enumerate(utts):
        norm_words = {norm(w["w"]) for w in u["words"]}
        is_meta = u["n"] <= 4 and any(norm(m) in norm_words for m in META)
        if is_meta:
            u["decision"], u["why"] = "drop", "meta (instruction to self)"; continue
        if u["score"] < min_score:
            if u["n"] <= 3:
                u["decision"], u["why"] = "drop", "fragment, not in script"
            else:
                u["decision"], u["why"] = "keep", "UNSCRIPTED: kept, please check"
            continue
        a, b = u["span"]
        u["decision"], u["why"] = "keep", f"script line ~{a}"
        # a later attempt of the same script stretch replaces the earlier one(s) it overlaps
        for k in list(kept):
            pa, pb = utts[k]["span"]
            ov = max(0, min(b, pb) - max(a, pa) + 1)
            if ov >= 0.5 * min(b - a + 1, pb - pa + 1):
                if u["n"] >= 0.6 * utts[k]["n"]:
                    utts[k]["decision"], utts[k]["why"] = "drop", f"retake: said again at #{i + 1}"
                    kept.remove(k)
                else:
                    u["decision"], u["why"] = "drop", f"fragment of #{k + 1} (shorter later attempt)"
                    break
        if u["decision"] == "keep":
            kept.append(i)


def plan(clips_dir: Path, script: Path, out: Path, max_minutes: float | None = None) -> dict:
    clips = clip_list(clips_dir)
    if max_minutes:
        sel, tot = [], 0.0
        for c in clips:
            if tot >= max_minutes * 60:
                break
            sel.append(c); tot += duration(c)
        clips = sel
    snt, srt, sli = script_tokens(script)
    words = transcribe_clips(clips, out / "_work")
    utts = utterances(words)
    match(utts, snt)
    decide(utts)
    out.mkdir(parents=True, exist_ok=True)
    plan = {"clips": [c.name for c in clips], "utterances": [
        {k: v for k, v in u.items() if k != "words"} | {"num": i + 1} for i, u in enumerate(utts)]}
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    kept = [u for u in utts if u["decision"] == "keep"]
    lines = ["# Takes plan", "",
             f"{len(clips)} clips, {len(utts)} utterances: {len(kept)} kept "
             f"({sum(u['e'] - u['s'] for u in kept):.0f} s), {len(utts) - len(kept)} dropped.",
             "Reply with changes like: keep 12, drop 30, use 41 instead of 44.", "",
             "| # | clip | time | decision | why | what was said |", "|---|---|---|---|---|---|"]
    for i, u in enumerate(utts):
        lines.append(f"| {i + 1} | {u['clip']} | {u['s']:.1f}–{u['e']:.1f} | {u['decision']} | {u['why']} | "
                     f"{u['text']} |")
    (out / "plan.md").write_text("\n".join(lines), encoding="utf-8")
    return plan


# ---------- assembly ----------

def assemble(clips_dir: Path, plan_file: Path, out: Path, pre: float = 0.15, post: float = 0.25) -> Path:
    p = json.loads(plan_file.read_text(encoding="utf-8"))
    keep = [u for u in p["utterances"] if u["decision"] == "keep"]
    if not keep:
        raise StageError("the plan keeps nothing")
    # merge kept utterances that follow each other in the same clip into one piece (no cut between them)
    pieces = []
    for u in keep:
        s, e = max(0.0, u["s"] - pre), u["e"] + post
        if pieces and pieces[-1][0] == u["clip"] and s <= pieces[-1][2] + 0.6:
            pieces[-1][2] = e
        else:
            pieces.append([u["clip"], s, e])
    first = clips_dir / pieces[0][0]
    hdr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                     "stream=color_transfer,color_primaries,color_space,pix_fmt", "-of", "json",
                                     str(first)], capture_output=True, text=True).stdout)["streams"][0]
    hdr10 = hdr.get("color_transfer") in ("arib-std-b67", "smpte2084")
    tmp = out.parent / "_pieces"
    tmp.mkdir(parents=True, exist_ok=True)
    lst = []
    for k, (clip, s, e) in enumerate(pieces):
        f = tmp / f"p{k:04d}.mov"
        venc = ["-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt",
                "yuv420p10le" if hdr10 else "yuv420p"]
        if hdr10:
            venc += ["-color_primaries", hdr.get("color_primaries", "bt2020"), "-color_trc", hdr["color_transfer"],
                     "-colorspace", hdr.get("color_space", "bt2020nc")]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-to", f"{e:.3f}", "-i",
                        str(clips_dir / clip), "-map", "0:v:0", "-map", "0:a:0", "-r", "30", *venc,
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(f)], check=True)
        lst.append(f"file '{f.resolve()}'")
    (tmp / "list.txt").write_text("\n".join(lst))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(out)], check=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("plan"); a1.add_argument("clips"); a1.add_argument("script"); a1.add_argument("out")
    a1.add_argument("--max-minutes", type=float, default=None)
    a2 = sub.add_parser("assemble"); a2.add_argument("clips"); a2.add_argument("plan"); a2.add_argument("out")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        p = plan(Path(a.clips), Path(a.script), Path(a.out), a.max_minutes)
        k = sum(u["decision"] == "keep" for u in p["utterances"])
        print(f"plan: {len(p['clips'])} clips, {len(p['utterances'])} utterances, {k} kept", flush=True)
    else:
        assemble(Path(a.clips), Path(a.plan), Path(a.out))
        print("assembled", flush=True)


if __name__ == "__main__":
    main()
