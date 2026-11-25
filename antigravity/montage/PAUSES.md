# Pause-tightening agent (Antigravity)

The video is ALREADY EDITED (takes chosen, retakes removed). Your only job: remove the dead moments inside
the speech so every sentence flows as one phrase. Nothing else changes: same takes, same order, same words.

Example: "صاحبه وصديقه …… هيرب كيليهر" becomes "صاحبه وصديقه هيرب كيليهر".

In this footage a "pause" is usually NOT silence. It is filled with sound, so you must listen for it:
- a stretched last syllable ("وصديقهههه"), "اااه", "ممم", "يعني…" used as filler
- a breath, a sigh, a lip smack, a swallow
- dead air while he looks down at the script or back up to the camera

Tools: `pauses.py` (in the same folder as this file). Python + numpy + ffmpeg.

## Steps

1. **Prepare review chunks**
   ```
   python pauses.py prep "<edited>.mp4" --out "_pauses"
   ```
   This writes 20-second chunks in `_pauses/chunks/` with the source time burned in (yellow clock, top right).
   ALWAYS read times from that clock, never from your own sense of time.

2. **Listen to every chunk at normal speed.** For each dead moment write one entry in `_pauses/remove.json`:
   ```json
   {"remove": [
     {"start": 4.26, "end": 4.95, "what": "stretched 'ه' + breath", "before": "وصديقه", "after": "هيرب"},
     {"start": 61.40, "end": 62.10, "what": "looks down at script, silent", "before": "السوق", "after": "وده"}
   ]}
   ```
   - `start` = the moment the last real word of the phrase ends; `end` = the moment the next real word starts.
   - Include the whole dead moment: the stretched sound, the breath and the silence, not only the silence.
   - Never include any part of a real word. If unsure where a word ends, leave 0.1 s more of it.
   - Write `before` / `after`: the words on each side, so the presenter can check the list.

3. **Which pauses to remove**
   - Inside a sentence: remove the whole dead moment (the script leaves only a hair between the words).
   - Between two sentences of the same paragraph: remove it, but end your span about 0.2 s before the next
     sentence starts, so a short breath stays.
   - Keep (do NOT list): the pause at the end of a paragraph or before a new section; a deliberate dramatic
     beat (he holds a look, smiles, reacts); a laugh; anything over a graphic or an insert.
   - Fillers that are words ("يعني", "بقى") stay unless they are clearly dead filler stretched over a pause.

4. **Cut**
   ```
   python pauses.py cut "<edited>.mp4" --out "_pauses" --preview
   ```
   It moves each edge to the gap between two words (up to 0.12 s) and writes `<edited>_tight.mp4` (full quality),
   `<edited>_tight_preview.mp4` and `report.md`. If it prints `STOP:`, fix what it says.

5. **Check your own work.** Watch the preview from start to end. At each removed span: is a word clipped?
   Does it sound rushed or robotic? Is any dead moment left? Fix `remove.json` and run step 4 again.
   Note in `_pauses/notes.md` anything you were unsure about.

## When you are asked for a TEST first
Do steps 1–5 only for the first 2 minutes (the first 6 chunks), and add `--until 120` to the cut command. Stop and report, so the presenter can approve
the style before the whole episode.
