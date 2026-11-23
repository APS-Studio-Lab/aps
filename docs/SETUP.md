# One-time setup: post-production line

The post-production line runs on GitHub Actions and reads and writes your personal Google Drive. Your PC is only needed once, to authorise Drive access (step 2). After that, everything runs from your phone.

## 1. Google Drive folders

In your personal Google Drive, create:

```
<Your Studio>/          ← any name; put it in the STUDIO_ROOT secret (step 3c)
├── 00_Brand/      ← brand kit: brand.yaml, brand.md, logo, sets/, archive/
├── 01_Inbox/      ← one folder per job: footage + job.yaml
├── 02_Renders/    ← finished master, short, report, transcript
└── 99_Archive/    ← processed inbox folders are moved here
```

## 2. Give GitHub access to Drive (rclone, about 5 minutes, once)

1. Install rclone from https://rclone.org/downloads/ (the Windows zip; no installer needed).
2. In a terminal in that folder run `rclone config`, then answer:
   - `n` (new remote), name: **gdrive**
   - storage: **drive**
   - client_id / client_secret: leave empty
   - scope: **1** (full access)
   - leave the rest as default; "Use web browser to automatically authenticate?" **y**
   - sign in with your **personal** Google account (the one with the 5 TB)
3. Run `rclone config file` to see where the config is saved. Open that file and copy everything in it.
4. Delete the local config afterwards (`rclone config delete gdrive`) so no token stays on the work PC.

## 3. Add the secret to GitHub

GitHub → your copy of this repository → Settings → Secrets and variables → Actions → **New repository secret**

- Name: `RCLONE_CONF`
- Value: the text you copied in step 2.3

## 3b. Gemini key for transcription (free)

1. Open https://aistudio.google.com with your personal account → **Get API key** → **Create API key**.
2. Add it as a second repository secret named `GEMINI_API_KEY` (or `GEMINI_KEY`).

Without it, the pipeline uses Whisper, which is slower and weaker on Egyptian Arabic mixed with English.

## 3c. Tell the workflow your Drive folder

Settings → Secrets and variables → Actions → **Secrets** tab → New repository secret:
`STUDIO_ROOT` = the exact name of your Drive studio folder. Use a secret, not a variable: on a public repository
the Actions logs are public, and only secrets are masked in them.

## 4. Run a job

1. In `01_Inbox`, create a folder, e.g. `2026-11-episode-03`.
2. Upload the green-screen take, the lapel voice file (optional) and a `job.yaml` (copy `jobs/example_job.yaml` and edit the file names, tag and headline).
3. Start it: GitHub app → this repository → Actions → **Post-production** → Run workflow. It also runs by itself twice a day.
4. Results land in `02_Renders/<folder>/`: `*_master_16x9.mp4`, `*_short_9x16.mp4`, `*_report.md`, `*_transcript.json`, `run.log`.
5. If something is wrong with the inputs, the job stops and writes `_failed.txt` into the inbox folder explaining why. Fix it, delete `_failed.txt`, and run again.

## Costs

- GitHub Actions: public repositories run on standard runners for free; private repositories get a monthly allowance of free minutes. A 60–70 second short takes roughly 15–25 runner minutes (HDR tone-mapping, keying and two outputs); a full episode will take a few hours. Check usage under GitHub → Settings → Billing.
- Google Drive: your existing storage. rclone transfers are free.
- Whisper captions run on the GitHub machine; no API key needed.
