# Synopticon

**A lightweight, fast HLS camera grid viewer for Windows.**

Synopticon lets you monitor multiple live streams simultaneously in a clean, resizable grid. Load an `.m3u` playlist or add stream URLs manually, and Synopticon will continuously capture and display thumbnails from each stream — all in one window, with no browser required.

---

![Synopticon](synopticon.ico)

---

## Features

- **Multi-stream grid** — view as many cameras as you want, with configurable columns (default 3 per row, adjustable up to any number)
- **Live thumbnail refresh** — streams are captured in parallel using ffmpeg and updated on a configurable interval (default: 1 second)
- **Three quality modes** — Lowest (fastest), Medium, and Highest — balancing speed vs. image clarity
- **Drag to reorder** — rearrange tiles by dragging
- **Click to open** — click any tile to open the stream in your preferred video player
- **Skin system** — ships with 5 built-in themes: Dark, Light, Navy, Red, Cyberpunk. Drop custom `.json` skin files into the `skins/` folder to add your own
- **Fullscreen mode** — press `F11` or click the fullscreen button. Stays in your taskbar and alt-tab
- **Auto-load playlists** — configure `.m3u` files to load automatically on startup
- **Persistent config** — settings saved to `~/.synopticon.json`
- **Portable** — single `.exe`, no installation required

---

## Requirements

| Component | Details |
|-----------|---------|
| **OS** | Windows 10 / 11 |
| **ffmpeg** | Must be present — either bundled next to `Synopticon.exe`, or available in your system PATH |
| **Python** | Not required for end users (exe is self-contained) |

> **ffmpeg** is the only external dependency. You can download a static build from [ffmpeg.org](https://ffmpeg.org/download.html). Place `ffmpeg.exe` in the same folder as `Synopticon.exe`.

---

## Getting Started

### Using the exe

1. Download `Synopticon.exe`
2. Place `ffmpeg.exe` in the same folder
3. Double-click `Synopticon.exe`
4. Click the **gear icon** (⚙) to open Settings
5. Go to **Streams → Load .m3u** to load a playlist, or **+ Add URL** to add a stream manually
6. Thumbnails will begin appearing automatically

### Adding streams manually

- Click ⚙ → **Streams** → **+ Add URL**
- Enter a stream name and an HLS URL (`.m3u8`)
- Click **Add**

### Loading an .m3u playlist

- Click ⚙ → **Streams** → **Load .m3u**
- Select your playlist file
- All streams in the file will be added to the grid

### Auto-loading playlists on startup

- Click ⚙ → **General** → **Auto-Load → + Add File**
- Any `.m3u` files added here will be loaded automatically every time Synopticon starts

---

## Settings Reference

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| Refresh interval | Playback | 1 second | How often thumbnails are recaptured |
| Columns | Playback | 3 | Number of camera tiles per row |
| Quality | Playback | Lowest | Thumbnail capture quality (Lowest / Medium / Highest) |
| Hotkey | Playback | `r` | Keyboard shortcut to manually refresh all streams |
| Video player | Playback | System default | External player used when clicking a tile |
| Skin | Appearance | Dark | Visual theme |
| Auto-load | General | — | `.m3u` files to load on startup |

---

## Skins

Synopticon ships with 5 built-in skins:

| Skin | Description |
|------|-------------|
| **Dark** | Default — dark background, blue accents |
| **Light** | Light background for bright environments |
| **Navy** | Deep ocean blue |
| **Red** | Crimson and dark |
| **Cyberpunk** | High-contrast black, red, and yellow with circuit overlay effects |

### Creating a custom skin

Create a `.json` file and place it in the `skins/` folder next to `Synopticon.exe`:

```json
{
  "name": "My Skin",
  "author": "Your Name",
  "font_family": "Consolas",
  "colors": {
    "BG":          "#0d0d0d",
    "TILE_BG":     "#111111",
    "TILE_BORDER": "#222222",
    "TILE_HOVER":  "#2a2a2a",
    "ACCENT":      "#00aaff",
    "ACCENT_DIM":  "#005580",
    "OFFLINE_RED": "#ff3333",
    "ONLINE_GREEN":"#33ff66",
    "TEXT":        "#ffffff",
    "TEXT_DIM":    "#666666",
    "SETTINGS_BG": "#161616",
    "INPUT_BG":    "#1a1a1a",
    "INPUT_BD":    "#333333",
    "BTN_BG":      "#1e1e1e",
    "BTN_HOVER":   "#2a2a2a"
  },
  "style": {
    "title":       "◉ MY SKIN",
    "dot_char":    "◉",
    "close_char":  "✕",
    "gear_char":   "⚙",
    "fs_char":     "⛶",
    "drag_char":   "≡",
    "border_width": 2
  }
}
```

All color values must be 6-digit hex (`#rrggbb`). Synopticon validates skin files on load and will reject any file with unknown keys or invalid values.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F11` | Toggle fullscreen |
| `Escape` | Exit fullscreen |
| `r` *(default)* | Refresh all streams now |

The refresh hotkey can be changed in **Settings → Playback → Hotkey**.

---

## Building from Source

If you want to build the exe yourself:

**Prerequisites:**
- Python 3.10+
- `pip install pillow pyinstaller`
- `ffmpeg.exe` in the project folder (will be bundled into the exe)

**Build:**
```bash
pyinstaller synopticon.spec
```

Output: `dist/Synopticon.exe`

The spec file handles bundling the skins folder, icon, and ffmpeg automatically.

**Running from source directly:**
```bash
pip install pillow
pip install tkinterdnd2   # optional, enables drag & drop of .m3u files
python synopticon.py
```

> ffmpeg must be in your PATH when running from source.

---

## File Structure

```
Synopticon.exe          ← main application
ffmpeg.exe              ← required for thumbnail capture
skins/                  ← custom skin folder (optional)
    my_skin.json
```

Config is saved automatically to `~/.synopticon.json` (your user home folder).

---

## Troubleshooting

**Tiles show "OFFLINE" but streams are working**
- Check that `ffmpeg.exe` is in the same folder as `Synopticon.exe` or in your system PATH
- Try increasing the refresh interval in Settings → Playback
- Try a lower quality setting — Lowest is the most reliable for slow connections

**App feels slow with many cameras**
- Reduce quality to Lowest
- Increase the refresh interval
- Reduce the number of columns so fewer tiles are active at once

**Skin not appearing in the dropdown**
- Ensure the `.json` file is in the `skins/` folder next to `Synopticon.exe`
- Validate your JSON — a syntax error will cause the skin to be silently skipped

---

## Disclaimer

> Synopticon is a media player tool. It does not provide, host, or curate any content. Users are responsible for ensuring they have the legal right to view the streams they add to the application.

---

## License

MIT License — free to use, modify, and distribute.

---

*Synopticon v1.01*
