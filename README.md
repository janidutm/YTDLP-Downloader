# YouTube Downloader

A Windows desktop downloader built with Python, Tkinter, and [yt-dlp](https://github.com/yt-dlp/yt-dlp). It provides a dark interface for batch downloads, YouTube Liked videos, quality selection, live streams, download history, and optional thumbnails.

> Download only videos you own or have permission to save. Follow YouTube's terms and the laws that apply to you. This project is independent and is not affiliated with YouTube or Google.

## Features

- Queue multiple video or playlist URLs in one batch.
- Download video or extract audio in supported formats and quality settings.
- Search titles in your Liked videos and queue selected original item numbers or ranges, such as `2,7,10-12`.
- Download a live stream from the current position or, when YouTube exposes a DVR window, from the beginning.
- Track progress, skip the current item, or stop at a fragment boundary.
- Optionally save a thumbnail and embed cover art when the chosen format supports it.
- Review completed downloads and their saved metadata in a local history window.
- Use Quiet, Smooth, or Peak motion settings.

## Get started

### Download the app

For a packaged Windows build, download the `YouTubeDownloader` folder from the project's **Releases** page and run `YouTubeDownloader.exe` inside it. Keep the folder structure intact; this is an onedir build, so the executable uses files in its `_internal` folder.

The app does not include your cookies or FFmpeg. See [Export YouTube cookies](#export-youtube-cookies) and [FFmpeg](#ffmpeg) below.

### Run from source

Requirements:

- Windows 10 or newer.
- Python 3.11 or newer.
- A JavaScript runtime for full YouTube support: [Deno 2.3+](https://deno.com/) is yt-dlp's recommended default; [Node.js 22+](https://nodejs.org/) is also supported and detected by this app.
- FFmpeg for merging separate video/audio streams and converting audio.

In PowerShell, from the project folder:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

### Build the Windows executable

After confirming the source app works, run:

```powershell
.\build_exe.bat
```

The script builds an **onedir** package at `dist\YouTubeDownloader\`. Share the complete folder, not just the `.exe`. `cookies.txt`, download history, and downloaded media are local data and are not bundled. The packaged app looks for `cookies.txt` next to the executable and in the project folder above `dist`.

## Export YouTube cookies

Cookies let yt-dlp access account-specific pages such as your private Liked videos list. Treat `cookies.txt` like a password: anyone who gets a valid copy may be able to use your signed-in session.

1. In Chrome, install **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** from the Chrome Web Store. Check that the publisher/project is [kairi003/Get-cookies.txt-LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY). Avoid similarly named extensions, especially the older extension titled “Get cookies.txt” without “LOCALLY”.
2. Sign in to YouTube in Chrome and open `youtube.com` in a tab. Confirm that the account has access to the Liked videos you want to use.
3. Click the extension's toolbar button. Choose **Netscape** as the export format, then use its export/save action to save the file as `cookies.txt` in the project root, beside `app.py`. If Chrome asks, confirm the `.txt` extension.
4. Start the app. It checks for `cookies.txt` automatically. If the file is elsewhere, select it once with the cookies file control.

Cookie exports can expire and may need to be recreated. yt-dlp requires the Netscape/Mozilla cookie-file format, normally identified by a first line such as `# Netscape HTTP Cookie File`. For other supported ways to provide cookies and current troubleshooting, see the [yt-dlp cookies FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

**Never commit, upload, email, or share `cookies.txt`.** It can contain active account session credentials and may include cookies for more than YouTube. This repository's `.gitignore` excludes cookie files, but still check the files shown by Git before publishing. Delete old exports when they are no longer needed; if one is exposed, sign out/revoke the affected session and create a fresh export.

## Use the app

1. Paste one URL per line into the download queue. URLs can be individual videos or playlists.
2. Choose Video or Audio, a container, and a quality cap. “Best available” lets yt-dlp select the best available format.
3. Optionally set playlist item numbers/ranges, a save folder, FFmpeg location, live-stream behavior, and the thumbnail checkbox.
4. Select **Start batch**. The progress gauge and Activity panel show current work. Use **Skip current** to move on after the current fragment, or **Stop after current fragment** to stop the batch.
5. To use Liked videos, select **Load my Liked videos**, search by title if useful, enter original item numbers or ranges, and choose **Add selection to queue**. Search does not renumber the underlying playlist items.
6. Select **History** to inspect completed downloads and saved metadata. The database is stored locally as `download_history.sqlite3` beside the app.

Liked videos are loaded when you request them. The app does not continuously watch your account for new likes or automatically download new items in the background.

## FFmpeg

Install FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) or a trusted Windows package source, then either add `ffmpeg.exe` to `PATH` or choose its location in the app. yt-dlp needs FFmpeg to merge many high-quality video streams and to convert/extract audio. The app does not bundle FFmpeg.

## Troubleshooting

- **Liked videos will not load:** refresh `cookies.txt` from the YouTube account that owns the list. Ensure the cookie file is Netscape format and begins with the expected cookie-file header.
- **YouTube reports a JavaScript challenge/runtime error or fewer formats than expected:** install a supported JavaScript runtime. Deno 2.3+ is recommended; this app detects Node.js 22+ if it is on `PATH`. Keep yt-dlp and its default dependencies current (`python -m pip install --upgrade "yt-dlp[default]"`).
- **Audio conversion or high-quality merging fails:** install FFmpeg and verify its path in the app.
- **A live stream cannot start from the beginning:** the stream must expose a DVR rewind window; yt-dlp cannot retrieve portions YouTube no longer makes available.
- **A cookie file is rejected:** export it again in Netscape format. Cookie exports are sensitive and can expire.

## Development

Install the app dependencies with the source instructions above. The repository includes a small option/parser test suite that can be run with:

```powershell
python test_app.py
```

Build dependencies are listed separately in `requirements-build.txt` and installed by `build_exe.bat`.

## Privacy, licensing, and third-party software

The app stores download history and metadata locally. It does not intentionally upload the history database or cookie file. yt-dlp connects to the requested media service to read metadata and download media; the browser extension has its own permissions and privacy policy, which you should review before installing it.

This source folder currently has no `LICENSE` file. Choose and add a license before inviting others to reuse or redistribute the app. yt-dlp and other dependencies are separate projects with their own licenses; review their terms before redistributing a packaged build. In particular, yt-dlp notes that PyInstaller-bundled executables include GPLv3+-licensed code; assess the applicable obligations for a packaged release using the [yt-dlp licensing notes](https://github.com/yt-dlp/yt-dlp#licensing).
