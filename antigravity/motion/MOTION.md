# Motion agent (Antigravity): text printed ON moving archive footage

Goal: short live-action-looking clips (intro, chapter cards) where the show's type is PRINTED on a real object
in the scene (the page of an old book, paper coming out of a printing press, a sheet on the editor's desk),
and the object moves: light flickers, dust drifts, the camera glides, paper runs, pages breathe.
No cards floating over the footage. The text must look like ink on that paper and move with it.

You make each clip in two steps: first a still where the type is already printed on the object (image
editing), then you animate that still (image-to-video). Animating a still that already carries the print
keeps the print glued to the object, which is exactly what we want.

## Inputs (studio Google Drive)
- Plates (the scenes): `00_Brand/archive/` — `bound_volume.jpeg` (open book), `press_rollers.jpeg`
  (press with paper), `layout_table.jpeg`, `paper_stack.jpeg`, `newsprint_blank.jpeg`, `archive_hall.jpeg`.
- Type artwork, exact and final: `00_Brand/agents/motion/<episode>/art/*.png` (black ink on transparent).
  The words, letters and logo in these files are the ONLY text allowed in the clip.
- The shot list for the episode: `00_Brand/agents/motion/<episode>/shots.md`.

## Way A (try first) — edit an EXISTING clip from `00_Brand/archive/motion/`
If you have a video-editing (video-to-video) model, give it the existing clip and the artwork PNG:

> Add the supplied artwork to [the left-hand page of the open book / the paper coming out of the press] as if
> it had been printed there with letterpress: dark brown-black ink pressed into the paper, following its
> curve, perspective, light and every movement of the paper for the whole clip. Keep the artwork's letters
> EXACTLY as supplied; add no other text. Keep everything else in the clip unchanged.

Same checks as Step 2 below: every Arabic letter identical to the artwork in EVERY part of the clip, the print
moves with the paper (including when a page lifts or the paper runs), nothing else changes, no visible
watermark. If the text is garbled or slides, do not keep trying for long: switch to Way B.

## Way B — print on a still, then animate it

## Step 1 — print the artwork onto the object (image edit, one still per shot)
Give the image model the plate AND the artwork PNG, with this prompt (fill the brackets from the shot list):

> Print the supplied artwork onto [the right-hand page of the open book / the sheet of paper coming out of
> the press rollers / the sheet on the desk] as if it had been printed there decades ago with letterpress:
> dark brown-black ink pressed into the paper, slightly uneven density, ink following the paper's fibres,
> curve and perspective of the surface, lit by the same warm lamp as the scene, in the same shadows.
> Keep the artwork's letters, spacing and proportions EXACTLY as supplied: do not redraw, translate,
> re-letter or add any text. Keep everything else in the photo unchanged. Photorealistic, 16:9, high detail.

Check before going on (zoom in to 100%):
- Every Arabic letter and dot is identical to the artwork. One wrong, missing or extra letter = redo.
- The print sits on the surface (perspective, curve, lighting) and does not float.
- No other text, logo or watermark anywhere in the image.

Make a 9:16 version too (same prompt, 9:16; or extend the 16:9 still to 9:16 first, then print).

## Step 2 — animate the still (image-to-video, 8 s, 1080p or higher)
Prompt (adapt the motion to the shot list):

> Slow cinematic push-in on [the open book / the printing press]. The warm desk lamp flickers gently, dust
> particles drift through the light beam, [the page lifts and settles slightly in a soft draught / the
> paper keeps feeding slowly out of the turning inked rollers, carrying the printed text downwards].
> The printed text stays perfectly legible and fixed to the paper, moving only with it. No new text, no
> letters changing, no page turning over the print, no people, no hands. Moody, warm tungsten light,
> shallow depth of field, film grain, 24 fps.

Check the whole clip frame by frame at the start, middle and end:
- The printed text never melts, morphs, swaps letters or slides across the paper. If it does: regenerate,
  or ask for less motion of the printed surface.
- Motion is real (light, dust, paper, camera), not just a zoom.
- **Watermarks:** if the video has a visible watermark (e.g. "Veo"), do not crop, blur, cover or otherwise
  remove it. Stop and report it; the presenter decides. The invisible SynthID mark is fine.

## Output
Save to `00_Brand/agents/motion/<episode>/out/`:
- `<shot>_16x9.mp4` and `<shot>_9x16.mp4` (the animated clips, highest quality available)
- `<shot>_still_16x9.png` / `_9x16.png` (the printed stills)
- `notes.md`: per shot, how many tries, anything you were unsure about, and which model made it
  (the presenter discloses AI footage on YouTube).

Never invent a shot, a text or a logo that is not in the shot list and the art folder. If something is
missing, stop and say what.
