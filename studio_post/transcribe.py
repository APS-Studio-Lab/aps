"""Transcription: Gemini (best for Egyptian Arabic mixed with English) with Whisper as the backup engine.

Both return utterances [{text, start, end}] on the timeline of the audio file they were given, and
word timings derived from them. Nothing is ever invented: if every engine fails, the stage stops.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

from .ingest import _pcm
from .util import StageError

GLOSSARY = ["مينتزبرج", "Mintzberg", "مدرسة القوة", "Power School",
            "Strategy Safari", "process of negotiation", "Micro Power", "Macro Power"]

PROMPT = """You are transcribing one presenter of an Egyptian Arabic business documentary.
Transcribe EXACTLY what is spoken, word for word:
- Egyptian Arabic in Arabic script, as spoken (do not convert to Modern Standard Arabic, do not fix grammar).
- English words and terms in Latin script, exactly as said.
- Keep false starts and REPEATED sentences: the speaker often re-records a line several times; every attempt must appear.
- Do not translate, summarise, or add anything that is not audible. Skip silence and breaths.
Split into short utterances of at most 8 words, each with start and end time in seconds from the start of the audio
(decimals allowed). Times must increase.
Names and terms that may occur: {glossary}."""

SCHEMA = {
    "type": "object",
    "properties": {"utterances": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"}},
        "required": ["text", "start", "end"]}}},
    "required": ["utterances"],
}


def _wav_bytes(samples: np.ndarray, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def _chunks(samples: np.ndarray, rate: int, max_s: float = 60.0) -> list[tuple[int, int]]:
    """Split at the quietest point near each max_s boundary so no word is cut."""
    n, step, out, s = len(samples), int(max_s * rate), [], 0
    win = rate // 10
    while s < n:
        e = min(n, s + step)
        if e < n:
            lo = max(s + step // 2, e - 10 * rate)
            seg = samples[lo:e]
            m = len(seg) // win
            if m:
                rms = np.sqrt((seg[: m * win].reshape(m, win) ** 2).mean(1))
                e = lo + int(np.argmin(rms)) * win
        out.append((s, e))
        s = e
    return out


def _gemini_call(api_key: str, model: str, audio: bytes, glossary: list[str]) -> list[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [
            {"text": PROMPT.format(glossary=", ".join(glossary))},
            {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(audio).decode()}},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    data = json.dumps(body).encode()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
            text = out["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)["utterances"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300]!r}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # network or malformed response
            last = repr(e)
        time.sleep(15 * (attempt + 1))
    raise StageError(f"Gemini transcription failed: {last}")


def _snap(utts: list[dict], samples: np.ndarray, rate: int) -> list[dict]:
    """Move utterance edges to the nearest real speech onset/offset (Gemini times can drift ~0.5 s)."""
    win = rate // 20  # 50 ms
    m = len(samples) // win
    db = 20 * np.log10(np.sqrt((samples[: m * win].reshape(m, win) ** 2).mean(1)) + 1e-9)
    sp = db > -45
    on = [i for i in range(1, m) if sp[i] and not sp[i - 1]] or [0]
    off = [i for i in range(1, m) if sp[i - 1] and not sp[i]] or [m - 1]
    on_t, off_t = np.array(on) * 0.05, np.array(off) * 0.05
    res = []
    for u in utts:
        s, e = float(u["start"]), float(u["end"])
        i = np.argmin(np.abs(on_t - s))
        if abs(on_t[i] - s) <= 0.6:
            s = float(on_t[i])
        j = np.argmin(np.abs(off_t - e))
        if abs(off_t[j] - e) <= 0.6:
            e = float(off_t[j])
        if e > s:
            res.append({"text": u["text"].strip(), "start": round(s, 3), "end": round(e, 3)})
    return res


def gemini(audio: Path, model: str, glossary: list[str]) -> list[dict]:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise StageError("GEMINI_API_KEY is not set")
    rate = 16000
    samples = _pcm(audio, rate)
    utts = []
    # Short chunks: Gemini's timestamps drift over long audio. Keep Gemini's own order (never re-sort by time,
    # which interleaves sentences when stamps overlap), keep every stamp inside its chunk and monotonic.
    for s, e in _chunks(samples, rate):
        part = [u for u in _gemini_call(key, model, _wav_bytes(samples[s:e], rate), glossary) if u.get("text")]
        if not part:
            continue
        dur, off = (e - s) / rate, s / rate
        last = max(float(u["end"]) for u in part)
        k = dur / last if last > dur else 1.0  # stamps ran past the chunk: squeeze them back in proportionally
        t = 0.0
        for u in part:
            st = min(max(float(u["start"]) * k, t), dur)
            en = min(max(float(u["end"]) * k, st + 0.2), dur)
            utts.append({"text": u["text"], "start": st + off, "end": en + off})
            t = en
    if not utts:
        raise StageError("Gemini returned an empty transcript")
    return _snap(utts, samples, rate)


def whisper(audio: Path, model_size: str, glossary: list[str]) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise StageError("faster-whisper is not installed") from e
    samples = _pcm(audio, 16000)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(samples, language="ar", word_timestamps=True, vad_filter=True,
                               condition_on_previous_text=False, initial_prompt="، ".join(glossary))
    gloss = {g.strip().lower() for g in glossary}
    utts = []
    for seg in segs:
        # Whisper sometimes "hears" its own prompt in silence: drop segments that are mostly glossary terms
        toks = [t.strip(" ،,.").lower() for t in seg.text.replace("،", " ").split() if t.strip(" ،,.")]
        if toks and sum(any(t in g.split() for g in gloss) for t in toks) / len(toks) > 0.6:
            continue
        ws = [w for w in (seg.words or []) if w.word.strip()]
        for k in range(0, len(ws), 8):
            grp = ws[k:k + 8]
            utts.append({"text": " ".join(w.word.strip() for w in grp), "start": grp[0].start, "end": grp[-1].end})
    if not utts:
        raise StageError("Whisper returned an empty transcript")
    return utts


def transcribe(audio: Path, cfg: dict, report: dict) -> list[dict]:
    """Gemini by default. No silent fallback: Whisper is weaker on Egyptian Ammia, so it is used only when the
    job asks for it (engine: whisper, or fallback: whisper). Otherwise a Gemini failure stops the render."""
    engine = cfg.get("engine", "gemini")
    from . import brandkit
    glossary = GLOSSARY + brandkit.glossary() + list(cfg.get("glossary", []))
    errors = []
    order = [engine] + [e for e in [cfg.get("fallback")] if e and e != engine]
    for eng in order:
        try:
            utts = gemini(audio, cfg.get("gemini_model", "gemini-3.5-flash"), glossary) if eng == "gemini" \
                else whisper(audio, cfg.get("whisper_model", "large-v3"), glossary)
            report["transcript"] = {"engine": eng, "utterances": len(utts)}
            if errors:
                report.setdefault("warnings", []).append(f"Transcription fell back to {eng}: {errors}")
            return utts
        except StageError as e:
            errors.append(f"{eng}: {e}")
    msg = " | ".join(errors)
    if "429" in msg or "quota" in msg.lower():
        raise StageError("Gemini free quota is used up for today. Re-run after it resets (about 10:00 Cairo), or put "
                         "a transcript_cache.json in the episode folder (e.g. made in Antigravity). " + msg[:300])
    raise StageError("transcription failed: " + msg)


def to_words(utts: list[dict]) -> list[dict]:
    """Spread each utterance's duration over its words in proportion to their length."""
    words = []
    for u in utts:
        toks = u["text"].split()
        if not toks:
            continue
        total = sum(len(t) for t in toks)
        t, span = u["start"], u["end"] - u["start"]
        for tok in toks:
            d = span * len(tok) / total
            words.append({"w": tok, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
    return words
