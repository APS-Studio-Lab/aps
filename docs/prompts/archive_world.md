# World B: the newspaper archive (أرشيف الجرنال): plate prompts for Gemini

Generate each at the highest resolution offered, 16:9 unless noted, download the original file and drop it in
`<studio folder>/00_Brand/archive/` with the file name given. No people, no hands, no logos, no readable text:
every word on screen is set later by the pipeline, so Gemini must not invent headlines.

Shared style line (already inside each prompt): photorealistic, shot on a full-frame cinema camera, 1960s Cairo
newspaper archive, tungsten light, deep shadows, dust in the air, Kodak Vision3 500T film look, subtle grain,
amber and deep green, no text, no logos, no people.

1. `archive_hall.png`: ident opening shot
> Photorealistic cinematic photograph of a basement newspaper archive in 1960s Cairo at night: long aisle of tall grey steel shelves packed with large bound newspaper volumes with cloth spines, a single bare tungsten bulb hanging in the middle of the aisle, dust floating in the light beam, worn tiled floor, deep shadows at the far end. Camera at standing eye height, perfectly level, centred on the aisle, 35 mm lens. Kodak Vision3 500T film look, subtle grain, amber and deep green, high contrast. No people, no text, no logos, no readable writing on spines. 16:9, highest resolution.

2. `press_rollers.png`: ident: the logo gets printed
> Photorealistic macro photograph of an old letterpress printing press in a dim Cairo print shop: heavy steel ink rollers glistening with black ink in the upper half, and a fresh sheet of blank off-white newsprint coming out of the rollers toward the camera in the lower half, the sheet completely blank and evenly lit by a warm work lamp from the left, shallow depth of field. Kodak Vision3 500T film look, subtle grain. No text, no logos, no people. 16:9, highest resolution.

3. `layout_table.png`: base for every insert (clippings, papers, explainers land here)
> Photorealistic top-down photograph of a worn wooden newspaper layout table under a warm lamp: dark walnut surface with ink stains, scratches and a few scattered brass paper clips, a steel ruler and a red grease pencil at the edges, the centre two-thirds of the table completely empty and clear. Soft pool of tungsten light in the middle falling off to dark corners. Camera exactly overhead, no perspective tilt. Kodak Vision3 500T look, subtle grain. No paper in the centre, no text, no logos, no people. 16:9, highest resolution.

4. `newsprint_blank.png`: paper the pipeline prints on (articles, definitions, numbers)
> Photorealistic flat scan of a single large sheet of aged blank newsprint paper: warm off-white with slight yellowing at the edges, fine paper fibres, faint fold line across the middle, a small coffee ring stain near one corner, soft even light. The sheet is completely blank with no printing at all. Fill the whole frame with the paper. No text, no logos. 16:9, highest resolution.

5. `layout_sheet.png`: paper for explainer diagrams (Deliberate vs Emergent, frameworks)
> Photorealistic flat scan of an old newspaper editor's layout sheet: thick cream paper with a faint light-blue printed grid and margin guides, a few graphite smudges and erased pencil marks, slightly curled corners. Completely blank apart from the faint grid. Fill the whole frame. No text, no numbers, no logos. 16:9, highest resolution.

6. `bound_volume.png`: chapter inserts (a heavy volume opens to the next chapter)
> Photorealistic photograph of a heavy bound newspaper volume lying open on a dark wooden archive table under a single tungsten lamp, seen from a 45-degree angle, the two open pages completely blank aged newsprint, cloth-and-leather binding with worn corners, dust in the light. Kodak Vision3 500T look, subtle grain. No text on the pages, no logos, no people. 16:9, highest resolution.

7. `paper_stack.png`: outro (the paper folds and drops on the stack)
> Photorealistic photograph of a tall stack of folded old newspapers on the corner of a wooden archive table at night, printed text on the stacked papers completely out of focus and unreadable, tungsten light from the left, deep shadows, empty dark space on the right half of the frame. Kodak Vision3 500T look, subtle grain. No readable text, no logos, no people. 16:9, highest resolution.

## Check before saving
Zoom in: any readable letters, fake headlines or logos → regenerate. Blank paper must be blank.
