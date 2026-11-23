# APS — Automated Production Studio

A cloud post-production studio for presenter-led documentary channels (built for Egyptian Arabic business content). Footage lives in Google Drive, renders run on GitHub Actions, and the agents run as Claude sessions on this repository. No local PC is needed after the one-time setup.

## What works today: the post-production line

Green-screen take (+ optional lapel voice) in Drive → GitHub Actions →

1. **Mezzanine:** HDR (HLG/PQ) tone-mapped to Rec.709, variable frame rate converted to a constant 30 fps.
2. **Voice sync:** the lapel recording is aligned to the camera by audio cross-correlation; it stops if the match is weak.
3. **Edit:** keeps speech and drops pauses and moments of looking down at the script (face pitch tracking).
4. **Transcript and retakes:** Gemini (Whisper as backup) transcribes Egyptian Arabic with English terms; repeated attempts of a line are removed, keeping the last one.
5. **Captions:** word-by-word Arabic captions rendered by Chromium.
6. **Key, relight and grade:** models the uneven green screen, removes spill, evens out exposure and colour between takes from the face, relights the presenter to match the set's lamp, and gives the whole frame a film finish (curve, halation, grain, vignette). Sets can be real-looking room plates (see `docs/prompts/sets.md`).
7. **Archive inserts:** realistic paper-and-ink inserts anchored to spoken phrases: definitions, quotes, evidence (real page captures), name cards, chapters, hand-drawn explainers, ident and outro (`graphics/inserts/`).
8. **Outputs:** a 4K (2160p) 16:9 master with the channel logo, and a 9:16 short with face-tracked framing, headline and captions. Motion-graphic cutaways are placed at a spoken phrase.
9. **QC:** A/V sync, loudness (-14 LUFS) and true peak, plus a report with every decision.

Results go to `<studio folder>/02_Renders/<job>/` in Drive. Setup: [docs/SETUP.md](docs/SETUP.md). Recording: [docs/SHOOTING_GUIDE.md](docs/SHOOTING_GUIDE.md).

Run locally: `pip install -r requirements.txt && python -m studio_post.run path/to/job.yaml`

## Known limits

- The source is 1080p, so the 9:16 short is a 1.42x enlargement and looks soft. Recording in 4K fixes this.
- The 4K master is upscaled from 1080p footage: cleaner on YouTube, but real detail needs 4K recording.
- Archive-style graphics (`graphics/archive/`) are a first prototype; the other graphics still use the older card style.
- Full 25–30 minute episodes take longer than one GitHub job allows (6 hours on 2 cores). They need splitting across parallel jobs, which is the next pipeline task.

## Roadmap

1. Post-production line (this) → 2. Thumbnail and graphics kit → 3. Pre-production agents (research, script room, Guardian) → 4. Publishing and analytics.

## Brand kit (kept out of this repository)

Everything channel-specific lives in Drive, in `<studio folder>/00_Brand/`, and is downloaded before each job:
`brand.yaml` (name, logo file, glossary), `brand.md` (editorial and language rules for the agents), the logo, the set plates (`sets/`) and the archive plates (`archive/`). Without a brand kit the output is neutral.
