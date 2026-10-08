# VidMind browser extension

A thin bridge between a YouTube tab and the VidMind backend. The extension
does no downloading, transcription, or analysis itself — it just detects the
video you're watching, asks the VidMind backend to analyze it, and opens the
full result in the VidMind web app.

## What it is (and isn't)

- **Popup-only.** No content script is injected into YouTube's page. The
  popup reads the active tab's URL and title via the `activeTab` permission
  when you open it — nothing runs on youtube.com in the background. This was
  a deliberate choice: page injection into YouTube's UI is fragile (frequent
  layout changes) and the popup gives the same functionality more reliably.
- **A bridge, not a workspace.** Once a video is analyzed, "Open Full
  Analysis" opens the real VidMind app at `/videos/{id}` — the extension
  never duplicates the transcript/summary/search UI.

## Install (unpacked, Chrome/Edge/Chromium)

1. Start the VidMind backend (`http://localhost:8000` by default) and
   frontend (`http://localhost:5173` by default) — see the main
   [README](../README.md).
2. Open `chrome://extensions` (or `edge://extensions`).
3. Enable **Developer mode** (top right).
4. Click **Load unpacked** and select this `extension/` folder.
5. Pin the VidMind icon to the toolbar if you'd like.

## Using it

1. Open any public YouTube video (`youtube.com/watch?v=…`, `youtu.be/…`, or
   `youtube.com/shorts/…`).
2. Click the VidMind icon.
3. Click **Analyze with VidMind**.
4. The popup polls real backend progress (`Fetching transcript…` →
   `Building semantic index…` → `Generating summary…` → `Finalizing…`) until
   it's done.
5. Click **Open Full Analysis** to see the full transcript, summary,
   chapters, semantic search, and Ask the Video in a new tab.

If captions are available on the video, VidMind uses them directly — no
video or audio is downloaded. If they aren't, VidMind downloads audio only
(never the full video) and transcribes it locally with Whisper; that
temporary audio file is deleted once processing finishes.

## Settings

Click the gear icon in the popup to set a different backend or app URL (for
example, if you're running VidMind on a different port or host). Defaults:

- Backend: `http://localhost:8000`
- App: `http://localhost:5173`

The extension only has network permission for `localhost:8000` /
`127.0.0.1:8000` (the default backend) — pointing it at a different host
requires reloading the extension with updated `host_permissions` in
`manifest.json`.

## Permissions

- `activeTab` — read the URL/title of the tab you have open when you click
  the icon. Nothing is read without you clicking.
- `storage` — remember your backend/app URL settings.
- Host access to the local backend only, so the popup can call its API.

No YouTube page access, no browsing history, no other tabs.

## Limitations

- Only works with the videos you can already watch — no private, deleted,
  age-restricted (sign-in-gated), or region-blocked video is accessed.
- Non-English captions fall back to Whisper if no English track is
  available (the summarization/QA models are English-tuned).
- The popup doesn't seek an already-open YouTube tab to a timestamp; source
  links inside the VidMind web app open `youtube.com/watch?v=…&t=…` in a new
  tab instead, which is simpler and more reliable than trying to control a
  separate tab's player.

## Your responsibility

This extension analyzes video content you already have access to and are
authorized to view. You're responsible for complying with YouTube's Terms of
Service, applicable copyright law, and any other content-access rules that
apply to the videos you analyze. VidMind does not bypass private-video
access, age-restriction sign-in, or any other access control, and is not a
general-purpose video downloader.
