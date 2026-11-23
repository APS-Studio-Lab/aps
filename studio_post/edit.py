"""Stage 3: the cut. Keep speech, drop pauses and moments the presenter looks down at the script."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .ingest import _pcm
from .util import FPS, StageError


def speech_frames(audio: Path, cfg: dict, n_frames: int, track: np.ndarray, report: dict) -> list[tuple[int, int]]:
    a = _pcm(audio, 16000)
    win = 1600  # 0.1 s
    n = len(a) // win
    db = 20 * np.log10(np.sqrt((a[: n * win].reshape(n, win) ** 2).mean(1)) + 1e-9)
    speech = db > cfg.get("speech_threshold_db", -45)

    runs, i = [], 0
    while i < n:
        if speech[i]:
            j = i
            while j < n and speech[j]:
                j += 1
            runs.append([i / 10, j / 10])
            i = j
        else:
            i += 1
    merged: list[list[float]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < cfg.get("merge_gap_s", 0.45):
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    pre, post = cfg.get("pad_before_s", 0.12), cfg.get("pad_after_s", 0.22)
    pitch_max = cfg.get("look_down_pitch", 0.66)
    bad = (track[:, 4] == 0) | (track[:, 5] > pitch_max)
    keep, dropped = [], 0
    for s, e in merged:
        f0 = math.ceil(max(0.0, s - pre) * FPS)
        f1 = min(n_frames - 1, math.floor((e + post) * FPS))
        if f1 - f0 + 1 < cfg.get("min_take_s", 0.7) * FPS:
            continue
        if bad[f0 : f1 + 1].mean() > cfg.get("max_look_down_share", 0.35):
            dropped += 1
            continue
        keep.append((f0, f1))

    limit = cfg.get("max_seconds")
    if limit:
        total, cut = 0, []
        for f0, f1 in keep:
            if total + (f1 - f0 + 1) > limit * FPS:
                break
            cut.append((f0, f1))
            total += f1 - f0 + 1
        keep = cut
    if not keep:
        raise StageError("no usable speech found; check the audio track and threshold")
    kept = sum(f1 - f0 + 1 for f0, f1 in keep)
    report["edit"] = {
        "takes_kept": len(keep),
        "takes_dropped_looking_down": dropped,
        "source_seconds": round(n_frames / FPS, 1),
        "edited_seconds": round(kept / FPS, 2),
        "note": "Repeated lines cannot be detected without a transcript; listen once before approving.",
    }
    return keep
