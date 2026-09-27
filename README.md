# CinderClip

A lightweight local video-to-short clip MVP with a fiery CinderClip UI.

## Current build
- Black/obsidian background with fiery orange/red/amber accents
- Drag-and-drop video upload
- Local FFmpeg processing
- 9:16, 1:1, or 16:9 output
- Resolution selector from 480p through 2160p where the source supports it
- Custom long-side resolution
- Source maximum option that never upscales beyond the dropped video
- Balanced and High quality export modes
- Browser preview + MP4 download
- Legal pages: privacy, terms, disclaimer

## Run on Windows
1. Install Python 3.10+.
2. Double-click `run.bat`.
3. The launcher automatically installs `imageio-ffmpeg` if needed.
4. Open http://localhost:8787

## Note
This experimental build generates evenly-spaced clip candidates. The AI moment-selection engine will later replace these candidates.

The legal pages are general experimental-product drafts and should be reviewed before a public commercial launch or hosted deployment.
