# Set plates: vintage room backgrounds (Nano Banana Pro, run by hand)

Generate these in the Gemini app or Google AI Studio with **Nano Banana Pro**, then upload the results to
`<studio folder>/00_Brand/sets/` in Drive. Reference them from a job with:

```yaml
background:
  image_h: ../../00_Brand/sets/study_16x9.png   # or copy the files into the job folder
  image_v: ../../00_Brand/sets/study_9x16.png
  light_from: left      # side of the main lamp in the picture; the presenter is relit to match
  blur: 2               # extra softness; the plate already has shallow depth of field
```

## Perspective and scale (v4): match the presenter's camera
Measured from the Uber footage: camera level, eyes 37% down from the top of the 16:9 frame (50% in the
9:16 short), face height 29% of the frame, presenter about 1.2 m from the camera. The frame bottom is at his
mid-chest, so the whole picture covers only ~80 cm of height at his distance.

v3 fixed the angle (eye level) but not the **scale**: the desk and lamp were drawn as if 1.5–2 m away, so
they came out as big as the presenter and the desk top landed at his shoulders. Real geometry for this
framing: furniture 3.5 m+ from the camera, so the **desk top sits at ~78% down the frame (16:9)**, a banker's
lamp is **about 1/5 of the frame height**, and shelves are spaced about **1/10 of the frame height**.

Attach `docs/prompts/guides/guide_scale_16x9.jpg` / `guide_scale_9x16.jpg` (grey presenter silhouette,
horizon, desk-top line, lamp box) to the Gemini prompt. The older `guide_16x9.jpg` / `guide_9x16.jpg` only fix the angle.

### v4 prompt, 16:9 (attach guide_scale_16x9.jpg)
> Use the attached layout guide only for camera height and scale; do not draw the guide, its lines, its labels or any person. Photorealistic cinematic photograph of an empty vintage study at night, 1960s Cairo intellectual's room. Camera at standing eye height, perfectly level, horizon exactly on the yellow line, vertical lines perfectly vertical. The grey shape is a man standing 1.2 m from the camera; everything in the room is 3.5 to 6 meters from the camera, far behind him, at the true scale that distance implies. On the left, far back: a wooden desk whose top edge sits on the green line (never higher), a brass banker's lamp with green glass shade glowing warm no bigger than the green box, a rotary telephone and a small globe; behind it tall walnut bookshelves with plain worn leather spines, shelves spaced like the short white marks. On the right, far back: dark walnut panelling and a carved wooden mashrabiya with soft light through it. The area behind the grey shape is dark, simple panelling. Warm tungsten light from the left, deep shadows on the right, slight dust in the air, Kodak Vision3 500T film look, subtle grain, amber and deep green, high contrast, documentary realism. No people, no faces, no portraits, no logos, no readable text. 16:9, highest resolution.

### v4 prompt, 9:16 (attach guide_scale_9x16.jpg)
> Use the attached layout guide only for camera height and scale; do not draw the guide, its lines, its labels or any person. The same vintage Cairo study at night, vertical frame for a phone video. Camera at standing eye height, perfectly level, horizon exactly on the yellow line (middle of the frame). The grey shape is a man standing 1.2 m from the camera; all furniture is 3.5 to 6 meters away, at the true scale that distance implies. Lower left, far back: the desk top on the green line (never higher) with the brass banker's lamp, green glass shade glowing, no bigger than the green box. Tall walnut bookshelves fill the upper half, shelves spaced like the white marks; the carved mashrabiya with soft light at the upper right. Dark panelling directly behind the grey shape. Warm tungsten light from the left, deep shadows right, Kodak Vision3 500T look, subtle grain, amber and deep green, high contrast. No people, no faces, no portraits, no logos, no readable text. 9:16, highest resolution.

### Check before saving
Place your hand over the frame at the green line: the desk top must not rise above it, and the lamp must look
small and distant, not like an object within arm's reach.

## Why the framing matters
The presenter is filmed about 1.5 m from the camera, at eye level. A plate only looks real if it was
"shot" from the same place: **nothing in the foreground**, furniture **3 m or more behind** the presenter, and a
**straight, eye-level** view (not looking down at a desk). The pipeline then pushes into the room and adds lens blur
(`zoom`, `anchor_x`, `lens_blur` in the job), so the room falls softly out of focus behind you.

## Rules for every set (they keep the composite believable and the brand clean)
- **Empty room, no people, no faces, no portraits** in frames or photos on the walls.
- **No readable text, logos, brands, posters, film or game characters.** Book spines plain or with illegible gilt.
- Camera at **standing eye level, level and straight-on** (not looking down); furniture at the scale of 3.5 m+ away (see v4).
- **Nothing within 3 m of the camera.** The desk and shelves sit in the background, 3–5 m away.
- Leave a **clear, slightly darker zone** where the presenter will stand (right of centre for 16:9, centre for 9:16).
- The main light is a **warm practical lamp on the left** of frame, with deep shadows on the right. Night interior.
- Photographic realism: real materials, film grain, no CGI gloss, no fantasy elements.

---

## Set A: The Investigator's Study (main set)

**16:9 prompt**

> Photorealistic cinematic photograph of an empty vintage study at night, 1960s Cairo intellectual's room, seen straight-on at standing eye level (1.6 m) with a 50mm lens, camera perfectly level, not looking down. The nearest furniture is at least 3 meters from the camera: in the background left, a wooden desk with a brass banker's lamp with green glass shade glowing warm, an old rotary telephone, a typewriter and a vintage globe, in front of tall walnut bookshelves with old leather-bound books with plain worn spines. In the background right, dark walnut panelling and a carved wooden mashrabiya screen with soft light through it. The foreground and the right-centre of the frame are empty open floor and dark space, where a person will later stand close to the camera. Warm tungsten practical light from the left, deep moody shadows on the right, faint dust in the air. Kodak Vision3 500T film look, subtle grain, rich amber and deep green tones, high contrast, documentary realism. No people, no faces, no portraits, no posters, no logos, no readable text. 16:9, 4K.

**9:16 prompt**

> Same room as above, vertical composition for a phone video: the same walnut bookshelves and brass banker's lamp, the lamp now at the left edge in the lower third, bookshelves rising behind, mashrabiya light at the top right. The centre of the frame from the middle down is an open, slightly darker area in soft focus where a person will stand. Camera at seated eye level, 35mm, f/1.8, shallow depth of field, Kodak Vision3 500T look, subtle grain, warm amber and deep green, high contrast. No people, no faces, no portraits, no posters, no logos, no readable text. 9:16, 4K.

## Set B: The Archive Room (for investigations and "the file is opened" moments)

> Photorealistic cinematic photograph of an empty old newspaper archive room at night, rows of metal filing cabinets and wooden pigeonhole shelves stuffed with bundled yellowed documents tied with string, a single hanging industrial lamp with a warm bulb at the upper left casting a cone of light, dust floating in the beam, an old wooden table with an open ledger and a magnifying glass on the left. The right-centre of the frame is an open, darker area in soft focus where a person will stand. Seated eye level, 35mm, f/2, shallow depth of field, 1970s documentary film look, Kodak 500T grain, amber light and teal shadows, high contrast. No people, no faces, no posters, no logos, no readable text. 16:9, 4K.

## Set C: The Boardroom After Hours (for corporate-power episodes)

> Photorealistic cinematic photograph of an empty 1980s corporate boardroom at night, long dark mahogany table with leather chairs pushed back, scattered papers and an ashtray-free crystal water carafe, tall windows on the right showing a blurred city at night in cool blue, a warm brass table lamp at the left end of the table providing the main light, venetian blind shadows across the far wall. The right-centre of the frame is an open area in soft focus where a person will stand. Seated eye level, 35mm, f/1.8, shallow depth of field, film look with grain, warm amber key against cool blue night, high contrast, documentary realism. No people, no faces, no logos, no readable text. 16:9, 4K.

## Checking a plate before using it
- Zoom in on shelves and papers: regenerate if any text is readable or any face appears.
- The lamp must be on the left (or set `light_from: right` in the job).
- Prefer the version with the emptiest, softest area where you will stand.
