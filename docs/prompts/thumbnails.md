# Thumbnail scenes: prompt recipe

The layout is fixed (`brand/templates/thumbnail.html`): the presenter, cut from a real frame of the episode,
big on the left third; 2–5 words in Ammia on the right, the second line in the accent colour. Only the scene
behind changes per episode. `studio_post/thumbs.py` grades it into the channel's palette and darkens the
presenter and text sides, so scenes can be rich.

Write 3 scene prompts per episode from its script: the story's central image, a metaphor of the conflict, and
a place or object from the case. Give them to the presenter to generate (highest resolution), saved as
`thumbs/scene_1`, `scene_2`, `scene_3` in the episode's inbox folder.

## Every prompt must include
- **Composition:** "Left third of the frame: dark and simple. Right side: calm and darker. The subject in the centre."
- **Look:** cinematic photograph, Kodak Vision3 500T film look, fine grain, high contrast, the channel's tones.
- **Never:** "No people, no faces, no logos, no airline or brand markings, no readable text." Companies appear only
  through generic objects (a plain plane, an unbranded box, a generic storefront). No famous people's likeness.
- **Format:** "16:9, highest resolution."

## job.yaml
```yaml
thumbnail:
  tag: "..."                    # optional small tag
  lines: ["...", "..."]         # 2-5 words in total, Ammia
  scenes: [thumbs/scene_1, thumbs/scene_2, thumbs/scene_3]
  # at_s: [312.5, 95.0, 401.0]  # optional: force presenter moments instead of the automatic pick
```
Run: GitHub → Actions → **Thumbnails** → episode folder name. Results: `02_Renders/<episode>/thumbnails/`
(3 thumbnails + the face shortlist with timestamps, to swap a face via `at_s`).
