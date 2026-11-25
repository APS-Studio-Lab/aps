"""Pen-on-paper sound for hand-drawn graphics, synthesised (no recordings, so nothing to license).

A graphic page publishes window.SFX = [{t, dur, kind}] from the same steps that draw its ink:
  write  - a word being written: short scratchy strokes
  line   - a pen line being drawn: one continuous scratch that follows the stroke
  tap    - a dot set down
This module turns that list into a wav the length of the graphic, and mixes it under the program audio.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

SR = 48000


def _band(noise: np.ndarray, lo: float, hi: float) -> np.ndarray:
    f = np.fft.rfft(noise)
    fr = np.fft.rfftfreq(len(noise), 1 / SR)
    shape = np.exp(-0.5 * ((np.log(fr + 1) - np.log((lo * hi) ** 0.5)) / (0.5 * np.log(hi / lo))) ** 2)
    return np.fft.irfft(f * shape, len(noise)).astype(np.float32)


def _event(kind: str, dur: float, rng: np.random.Generator) -> np.ndarray:
    n = max(int(dur * SR), 64)
    t = np.arange(n) / SR
    if kind == "tap":
        n = int(0.06 * SR)
        x = _band(rng.standard_normal(n), 1500, 5000)
        return x * np.exp(-np.arange(n) / (0.008 * SR)) * 0.9
    x = _band(rng.standard_normal(n), 2200, 7000)          # the paper's grain under the nib
    x += 0.35 * _band(rng.standard_normal(n), 300, 900)    # the hand and the pen body
    if kind == "write":
        # words: quick strokes (~9 a second) with tiny lifts of the pen between them
        rate = rng.uniform(7.5, 10.5)
        ph = rng.uniform(0, 6.28)
        strokes = np.clip(np.sin(2 * np.pi * rate * t + ph + 0.8 * np.sin(2 * np.pi * 2.3 * t)), 0, None) ** 0.6
        j = _band(rng.standard_normal(n), 3, 20)
        env = strokes * (0.75 + 0.25 * j / (np.abs(j).max() or 1.0))
    else:
        # a line: one continuous scratch, pressure wandering a little
        env = 0.75 + 0.25 * np.sin(2 * np.pi * rng.uniform(1.5, 3.0) * t + rng.uniform(0, 6.28))
    a = min(int(0.02 * SR), n // 4)
    edge = np.ones(n, np.float32)
    edge[:a] = np.linspace(0, 1, a)
    edge[-a:] = np.linspace(1, 0, a)
    return (x * env * edge).astype(np.float32)


def render(events: list[dict], seconds: float, out: Path, level_db: float = -26.0, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    buf = np.zeros(int(seconds * SR) + SR, np.float32)
    for e in events:
        t0 = float(e["t"])
        if t0 < 0 or t0 >= seconds:
            continue
        x = _event(e.get("kind", "line"), min(float(e.get("dur", 0.4)), 2.5), rng)
        i = int(t0 * SR)
        buf[i:i + len(x)] += x[:len(buf) - i]
    buf = buf[:int(seconds * SR)]
    peak = np.abs(buf).max() or 1.0
    buf = buf / peak * (10 ** (level_db / 20))
    st = np.repeat((buf * 32767).astype(np.int16)[:, None], 2, 1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(st.tobytes())
    return out


def events_from_page(browser, page_file: Path, w: int = 1920, h: int = 1080) -> list[dict]:
    """Ask the graphic page for its sound events (window.SFX), after its fonts have loaded."""
    pg = browser.browser.new_page(viewport={"width": w, "height": h})
    try:
        pg.goto(page_file.resolve().as_uri())
        pg.wait_for_timeout(600)
        pg.evaluate("window.render && window.render(0.01)")
        return json.loads(pg.evaluate("JSON.stringify(window.SFX || [])"))
    finally:
        pg.close()


def mix_into(master: Path, sfx: Path, at_s: float) -> None:
    """Add a sound under the program at a time (in place). Both are 16-bit wav; channels/rate are matched."""
    with wave.open(str(master), "rb") as r:
        p = r.getparams()
        m = np.frombuffer(r.readframes(p.nframes), np.int16).reshape(-1, p.nchannels).astype(np.float32)
    with wave.open(str(sfx), "rb") as r:
        q = r.getparams()
        s = np.frombuffer(r.readframes(q.nframes), np.int16).reshape(-1, q.nchannels).astype(np.float32)
    if q.framerate != p.framerate:
        idx = np.arange(0, len(s), q.framerate / p.framerate).astype(int)
        s = s[idx[idx < len(s)]]
    s = s.mean(1, keepdims=True).repeat(p.nchannels, 1)
    i = int(at_s * p.framerate)
    if i >= len(m):
        return
    k = min(len(s), len(m) - i)
    m[i:i + k] += s[:k]
    with wave.open(str(master), "wb") as w:
        w.setparams(p)
        w.writeframes(np.clip(m, -32768, 32767).astype(np.int16).tobytes())
