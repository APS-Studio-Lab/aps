# APS — Automated Production Studio

This repository is the studio: its agents, its render pipeline and its workflows. It is brand-neutral and public.
Media never lives here. Raw footage, renders, archives and the channel's brand kit live in Google Drive, in the
studio folder named by the `STUDIO_ROOT` repository variable.

## Before any editorial, script, design or publishing work
Read the channel's rules in the private brand kit: Drive `<STUDIO_ROOT>/00_Brand/brand.md` (Google Drive connector).
It names the host, the editorial scope, the publishing schedule and the brand. Those rules apply on top of the ones here.
Never copy brand names, the host's name, logos or channel-specific rules into this repository.

## Non-negotiable rules for every agent and script
1. **Fail loudly, never fabricate.** If real data, a source or an input file is missing, stop and report what is missing. Never fill a gap with a template, a placeholder number or an "offline" fallback.
2. **Every figure is sourced.** Any number, date or quote that reaches a script, graphic or thumbnail must carry a source in the artifact that introduced it. Evidence inserts show the real page, never a recreation.
3. **Real people only from real footage.** No AI-generated or AI-altered faces of the presenter. Still photos are allowed; synthetic animation of a face is not.
4. **No third-party IP in brand assets.** No logos, characters or posters of other companies or franchises in sets, intros or templates. Company names in editorial context are fine.
5. **Human gates.** Nothing is published without the presenter's approval in the Claude app: pitch, script, final cut and thumbnail.

## Language: Egyptian business Ammia, never Fus-ha
Every word the audience sees or hears (scripts, captions, titles, thumbnails, cards, descriptions, community posts)
is Egyptian Ammia the way Egyptian business people talk, not Modern Standard Arabic. Guide: `docs/LANGUAGE.md`.
Captions transcribe what the presenter said, never "corrected" to Fus-ha.

## Brand kit (Drive `00_Brand/`, downloaded before every job)
- `brand.yaml`: name, logo file, transcription glossary (read by `studio_post/brandkit.py`).
- `brand.md`: the channel's rules for agents.
- `logo.png`, `sets/` (study plates), `archive/` (archive-world plates).
- Arabic text is always rendered by a browser (Chromium shaping) from HTML templates. Never draw Arabic with PIL.

## Repository map
- `studio_post/` — post-production pipeline (`python -m studio_post.run jobs/<job>.yaml`).
- `brand/` — open fonts (SIL OFL / Apache) and neutral HTML templates for backgrounds, overlays and captions.
- `graphics/inserts/` — archive inserts (definition, quote, evidence, namecard, chapter, explainer + `diagrams.js`, ident, outro); each is HTML with a deterministic `window.render(t)` reading its content from `window.D`.
- `graphics/` — other motion graphics, same `window.render(t)` contract.
- `jobs/` — example job YAML documenting every option.
- `.github/workflows/` — the render farm (GitHub Actions), probe and key checks.
- `docs/SETUP.md` — one-time setup of Drive, secrets, the `STUDIO_ROOT` variable and the workflow.

## Working conventions
- Keep stages small and composable; each stage writes its artifact into the job's work folder and the QC report.
- Prefer ffmpeg for decode/encode, OpenCV/NumPy for per-frame image work, Chromium for anything with text.
- Phone footage may be HDR (HLG). Always tone-map to Rec.709 before any processing.
- Pre-edited exports (`edit.mode: keep`): frames that are not green screen pass through untouched.
