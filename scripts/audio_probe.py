"""Picture and numbers for a stretch of speech: loudness curve with the voice detector's speech spans and the
pauses, so pacing problems can be seen without listening.

python scripts/audio_probe.py a.wav <start_s> <out_dir>
"""
import sys
import wave
from pathlib import Path

import cv2
import numpy as np

wav, t0, out = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3])
with wave.open(str(wav)) as r:
    sr = r.getframerate()
    x = np.frombuffer(r.readframes(r.getnframes()), np.int16).astype(np.float32) / 32768
hop = sr // 20  # 50 ms
m = len(x) // hop
db = 20 * np.log10(np.sqrt((x[:m * hop].reshape(m, hop) ** 2).mean(1) + 1e-12))

from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
y = x[:len(x) // 3 * 3].reshape(-1, 3).mean(1)
sp = get_speech_timestamps(y, VadOptions(threshold=0.45, min_silence_duration_ms=80, speech_pad_ms=0,
                                         min_speech_duration_ms=40))
spans = [(d["start"] / 16000, d["end"] / 16000) for d in sp]
gaps = [(e0, s1) for (_, e0), (s1, _) in zip(spans, spans[1:])]

W, H = 3000, 600
img = np.full((H, W, 3), 255, np.uint8)
dur = len(x) / sr
X = lambda t: int(t / dur * (W - 1))  # noqa: E731
Y = lambda d: int(np.interp(d, [-70, 0], [H - 40, 20]))  # noqa: E731
for s, e in spans:
    cv2.rectangle(img, (X(s), H - 30), (X(e), H - 10), (80, 170, 60), -1)
for s, e in gaps:
    col = (40, 40, 220) if e - s >= 0.3 else (0, 160, 240) if e - s >= 0.15 else (200, 200, 200)
    cv2.rectangle(img, (X(s), 0), (X(e), H - 35), col if e - s >= 0.15 else (235, 235, 235), -1 if e - s >= 0.15 else 1)
pts = np.array([[X(i * 0.05), Y(v)] for i, v in enumerate(db)], np.int32)
cv2.polylines(img, [pts], False, (30, 30, 30), 1)
for s in range(int(dur) + 1):
    cv2.line(img, (X(s), H - 35), (X(s), H - 30), (0, 0, 0), 1)
    if s % 5 == 0:
        cv2.putText(img, f"{t0 + s:.0f}", (X(s) + 2, H - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
cv2.imwrite(str(out / "audio.png"), img)
hist = np.histogram([e - s for s, e in gaps], bins=[0, .08, .15, .25, .4, .7, 2, 99])[0]
lines = [f"duration {dur:.1f}s, speech spans {len(spans)}, loudness p5 {np.percentile(db, 5):.1f} dB, "
         f"p50 {np.percentile(db, 50):.1f}, p95 {np.percentile(db, 95):.1f}",
         "gaps between speech (s): <0.08 %d | 0.08-0.15 %d | 0.15-0.25 %d | 0.25-0.4 %d | 0.4-0.7 %d | 0.7-2 %d | >2 %d"
         % tuple(hist)]
lines += [f"{t0 + s:7.2f} - {t0 + e:7.2f}  gap {e - s:.2f}s  (min dB {db[int(s * 20):max(int(s * 20) + 1, int(e * 20))].min():.1f})"
          for s, e in gaps if e - s >= 0.12]
(out / "audio.txt").write_text("\n".join(lines))
print("\n".join(lines[:2]))
