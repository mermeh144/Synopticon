#!/usr/bin/env python3
"""
Synopticon v1.01
-------------------
Fast HLS thumbnail grid companion for PotPlayer.

Requirements:
    pip install pillow
    pip install tkinterdnd2   (optional — enables drag & drop of .m3u files)

ffmpeg must be in PATH.
PotPlayer must be installed — edit POTPLAYER_PATH if needed.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import json
import re
import time
import math
import subprocess
import tempfile
import urllib.request
from PIL import Image, ImageTk, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────────

POTPLAYER_PATH = r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".synopticon.json")
DEFAULT_INTERVAL = 1    # seconds
DEFAULT_COLS     = 3    # cameras per row
APP_VERSION      = "v1.01"
THUMB_W = 320
THUMB_H = 180
PAD = 8

# ── Skin system ───────────────────────────────────────────────────────────────

# Resolve base directory correctly whether running as script or PyInstaller exe
def _base_dir() -> str:
    """Return the folder containing the exe (or script), not the temp _MEIPASS folder."""
    import sys
    if getattr(sys, "frozen", False):
        # PyInstaller exe: sys.executable is Synopticon.exe
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _bundled_dir() -> str:
    """Return PyInstaller's _MEIPASS (bundled data) or script dir."""
    import sys
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR  = _base_dir()      # Where the exe lives — user-writable
BUNDLE_DIR = _bundled_dir()  # Where bundled data lives (read-only in exe)

# Skins: check user folder next to exe first, then bundled skins
_USER_SKINS  = os.path.join(BASE_DIR,   "skins")
_BUNDLED_SKINS = os.path.join(BUNDLE_DIR, "skins")
SKINS_DIR = _USER_SKINS  # primary (user can add skins here)

# Minimal fallback — used only if no skin files are found at all
DEFAULT_SKIN = {
    "name": "Default",
    "font_family": "Consolas",
    "colors": {
        "BG":           "#080810",
        "TILE_BG":      "#0e0e1a",
        "TILE_BORDER":  "#1a1a2e",
        "TILE_HOVER":   "#2a2a50",
        "ACCENT":       "#4070ff",
        "ACCENT_DIM":   "#1a2a66",
        "OFFLINE_RED":  "#cc2233",
        "ONLINE_GREEN": "#22cc66",
        "TEXT":         "#c0c0e0",
        "TEXT_DIM":     "#404060",
        "SETTINGS_BG":  "#0c0c18",
        "INPUT_BG":     "#12121f",
        "INPUT_BD":     "#252540",
        "BTN_BG":       "#1a1a30",
        "BTN_HOVER":    "#252545",
    },
    "style": {
        "title":        "◉ SYNOPTICON",
        "dot_char":     "●",
        "close_char":   "✕",
        "gear_char":    "⚙",
        "fs_char":      "⛶",
        "drag_char":    "≡",
        "border_width": 1,
    }
}

# Active skin — mutable globals
_SKIN = {}

def _load_skin_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _get_available_skins() -> dict:
    """Return dict of name -> path for all skins in skins/ folder."""
    skins = {}
    if not os.path.isdir(SKINS_DIR):
        return skins
    for fname in sorted(os.listdir(SKINS_DIR)):
        if fname.endswith(".json"):
            try:
                path = os.path.join(SKINS_DIR, fname)
                data = _load_skin_file(path)
                skins[data.get("name", fname)] = path
            except Exception:
                pass
    return skins

def _apply_skin(skin: dict):
    """Apply a skin dict — updates all global color + style variables."""
    global BG, TILE_BG, TILE_BORDER, TILE_HOVER, ACCENT, ACCENT_DIM
    global OFFLINE_RED, ONLINE_GREEN, TEXT, TEXT_DIM
    global SETTINGS_BG, INPUT_BG, INPUT_BD, BTN_BG, BTN_HOVER
    global FONT_FAMILY, S_TITLE, S_DOT, S_CLOSE, S_GEAR, S_FS, S_DRAG, S_BORDER
    _SKIN.clear()
    _SKIN.update(skin)
    c = skin.get("colors", {})
    s = skin.get("style",  {})
    BG           = c.get("BG",           "#080810")
    TILE_BG      = c.get("TILE_BG",      "#0e0e1a")
    TILE_BORDER  = c.get("TILE_BORDER",  "#1a1a2e")
    TILE_HOVER   = c.get("TILE_HOVER",   "#2a2a50")
    ACCENT       = c.get("ACCENT",       "#4070ff")
    ACCENT_DIM   = c.get("ACCENT_DIM",   "#1a2a66")
    OFFLINE_RED  = c.get("OFFLINE_RED",  "#cc2233")
    ONLINE_GREEN = c.get("ONLINE_GREEN", "#22cc66")
    TEXT         = c.get("TEXT",         "#c0c0e0")
    TEXT_DIM     = c.get("TEXT_DIM",     "#404060")
    SETTINGS_BG  = c.get("SETTINGS_BG", "#0c0c18")
    INPUT_BG     = c.get("INPUT_BG",     "#12121f")
    INPUT_BD     = c.get("INPUT_BD",     "#252540")
    BTN_BG       = c.get("BTN_BG",       "#1a1a30")
    BTN_HOVER    = c.get("BTN_HOVER",    "#252545")
    FONT_FAMILY  = skin.get("font_family", "Consolas")
    S_TITLE      = s.get("title",        "◉ SYNOPTICON")
    S_DOT        = s.get("dot_char",     "●")
    S_CLOSE      = s.get("close_char",   "✕")
    S_GEAR       = s.get("gear_char",    "⚙")
    S_FS         = s.get("fs_char",      "⛶")
    S_DRAG       = s.get("drag_char",    "≡")
    S_BORDER     = s.get("border_width", 1)

# Also keep _THEME alias for ColorPickerDialog compat
_THEME = property(lambda: {k: v for k,v in _SKIN.items()})

# Initialise: try to load dark.json from skins folder, else use built-in fallback
def _load_default_skin() -> dict:
    # Try user skins first, then bundled
    dark_path = os.path.join(_USER_SKINS, "dark.json")
    if not os.path.isfile(dark_path):
        dark_path = os.path.join(_BUNDLED_SKINS, "dark.json")
    if os.path.isfile(dark_path):
        try:
            return _load_skin_file(dark_path)
        except Exception:
            pass
    return DEFAULT_SKIN

_apply_skin(_load_default_skin())

# Helper used by ColorPickerDialog
def _theme_color(key: str) -> str:
    return _SKIN.get("colors", {}).get(key, DEFAULT_SKIN["colors"].get(key, "#000000"))

def _contrast_color(hex_bg: str) -> str:
    """Return black or BG color for readable text on a given background."""
    try:
        h = hex_bg.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        # Relative luminance
        luminance = (0.299*r + 0.587*g + 0.114*b) / 255
        return "#000000" if luminance > 0.55 else "#ffffff"
    except Exception:
        return "#ffffff"

# ── Thumbnail capture ─────────────────────────────────────────────────────────

HTTP_TIMEOUT = 8   # seconds

JPEG_Q = 8         # ffmpeg -q:v: 1=best, 31=worst. 8 is plenty for thumbnails.


# Quality levels: "lowest", "medium", "highest"
# Set by the app at runtime via capture_frame(url, quality=...)
QUALITY_LEVELS = ["Lowest", "Medium", "Highest"]

def _resolve_stream_by_quality(m3u8_url: str, quality: str = "Lowest") -> str:
    """
    Fetch a master HLS playlist and pick a variant stream by quality.
      Lowest  → minimum BANDWIDTH (fastest, smallest)
      Medium  → middle variant
      Highest → maximum BANDWIDTH (best quality, slowest)
    Falls back to the original URL if no variants are found.
    """
    try:
        req = urllib.request.Request(m3u8_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            text = r.read().decode("utf-8", errors="ignore")

        if "#EXT-X-STREAM-INF" not in text:
            return m3u8_url  # already a media playlist

        base = m3u8_url.rsplit("/", 1)[0] + "/"
        variants = []  # list of (bandwidth, url)

        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"BANDWIDTH=(\d+)", line)
                bw = int(m.group(1)) if m else 0
                for j in range(i + 1, len(lines)):
                    candidate = lines[j].strip()
                    if candidate and not candidate.startswith("#"):
                        url = candidate if candidate.startswith("http") else base + candidate
                        variants.append((bw, url))
                        break

        if not variants:
            return m3u8_url

        variants.sort(key=lambda x: x[0])  # sort ascending by bandwidth

        q = quality.lower()
        if q == "lowest":
            return variants[0][1]
        elif q == "highest":
            return variants[-1][1]
        else:  # medium
            return variants[len(variants) // 2][1]

    except Exception:
        return m3u8_url


# Quality affects three things: stream variant, capture resolution, JPEG compression
#
#  Lowest  → lowest bitrate stream  | 426x240  | q:v 10  (fast, decent quality)
#  Medium  → middle stream          | 426x240  | q:v 6   (balanced)
#  Highest → highest bitrate stream | 854x480  | q:v 2   (sharpest, slowest)

QUALITY_JPEG = {"Lowest": 10, "Medium": 6, "Highest": 2}
QUALITY_RES  = {"Lowest": (426, 240), "Medium": (426, 240), "Highest": (854, 480)}


# ── Persistent ffmpeg capture engine ─────────────────────────────────────────

import struct as _struct
import io as _io
import sys as _sys

_CREATE_NO_WINDOW = 0x08000000 if _sys.platform == "win32" else 0


class PersistentCapture:
    """
    Manages one long-running ffmpeg process per camera that pipes raw frames
    to stdout. Eliminates cold-start costs (DNS, TLS, probe, init) on every
    refresh cycle.

    The ffmpeg process outputs one raw RGB24 frame per interval (via fps=1/N),
    and we always keep only the *latest* frame — no buffering, no drift.

    When interval or quality changes, the process is killed and respawned
    with the new parameters.
    """

    def __init__(self, url: str, quality: str = "Lowest", interval: int = 1):
        self._url = url
        self._quality = quality
        self._interval = interval
        self._proc = None          # subprocess.Popen
        self._latest_frame = None  # PIL Image or None
        self._online = False
        self._lock = threading.Lock()
        self._reader_thread = None
        self._stopping = False
        self._cap_w, self._cap_h = QUALITY_RES.get(quality, (426, 240))
        self._frame_gen = 0        # increments each time a new frame arrives
        self._new_frame_event = threading.Event()  # signalled on each new frame

    def start(self):
        """Launch the persistent ffmpeg process."""
        self._stopping = False
        stream_url = _resolve_stream_by_quality(self._url, self._quality)

        fps_val = f"1/{self._interval}" if self._interval > 1 else "1"

        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-probesize", "32000",
            "-analyzeduration", "0",
            "-rw_timeout", "8000000",
            "-i", stream_url,
            "-vf", (
                f"fps={fps_val},"
                f"scale={self._cap_w}:{self._cap_h}:"
                f"force_original_aspect_ratio=decrease:flags=fast_bilinear,"
                f"pad={self._cap_w}:{self._cap_h}:(ow-iw)/2:(oh-ih)/2:color=#080810"
            ),
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-vsync", "drop",
            "pipe:1",
        ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception:
            self._online = False
            return

        self._reader_thread = threading.Thread(
            target=self._read_frames, daemon=True
        )
        self._reader_thread.start()

    def _read_frames(self):
        """Continuously read raw frames from ffmpeg stdout.
        Each frame is exactly cap_w * cap_h * 3 bytes (RGB24).
        We always overwrite _latest_frame so it stays fresh."""
        frame_size = self._cap_w * self._cap_h * 3
        buf = bytearray()
        proc = self._proc
        try:
            while not self._stopping and proc.poll() is None:
                chunk = proc.stdout.read(frame_size - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) >= frame_size:
                    # Build PIL Image from raw RGB bytes
                    try:
                        img = Image.frombytes(
                            "RGB", (self._cap_w, self._cap_h), bytes(buf[:frame_size])
                        )
                        with self._lock:
                            self._latest_frame = img
                            self._online = True
                            self._frame_gen += 1
                        # Signal anyone waiting for a new frame
                        self._new_frame_event.set()
                    except Exception:
                        pass
                    buf = buf[frame_size:]
        except Exception:
            pass
        finally:
            with self._lock:
                self._online = False
            self._new_frame_event.set()  # unblock waiters on death

    def get_frame(self) -> tuple:
        """Return (Image or None, online_bool, frame_generation). Non-blocking."""
        with self._lock:
            return self._latest_frame, self._online, self._frame_gen

    def wait_for_new_frame(self, last_gen: int, timeout: float = 5.0) -> bool:
        """Block until a frame newer than last_gen arrives, or timeout.
        Returns True if a new frame is available, False on timeout/death."""
        deadline = time.monotonic() + timeout
        while not self._stopping:
            with self._lock:
                if self._frame_gen > last_gen:
                    return True
                if not self._online and self._frame_gen == 0:
                    # Never connected yet — keep waiting up to timeout
                    pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            # Clear and wait for next signal
            self._new_frame_event.clear()
            self._new_frame_event.wait(timeout=min(remaining, 0.5))
        return False

    def stop(self):
        """Kill the ffmpeg process."""
        self._stopping = True
        proc = self._proc
        self._proc = None
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.stderr.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                pass

    def restart(self, quality: str = None, interval: int = None):
        """Restart with new quality/interval settings."""
        if quality is not None:
            self._quality = quality
            self._cap_w, self._cap_h = QUALITY_RES.get(quality, (426, 240))
        if interval is not None:
            self._interval = interval
        self.stop()
        self.start()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


# Legacy one-shot capture — used as a fallback if persistent fails to start
def capture_frame(url: str, quality: str = "Lowest") -> Image.Image | None:
    """
    One-shot fallback: grab a single thumbnail from an HLS stream.
    Only used if persistent capture hasn't delivered a frame yet.
    """
    tmp_path = None
    try:
        stream_url = _resolve_stream_by_quality(url, quality)
        cap_w, cap_h = QUALITY_RES.get(quality, (320, 180))

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-probesize", "32000",
                "-analyzeduration", "0",
                "-rw_timeout", "8000000",
                "-i", stream_url,
                "-frames:v", "1",
                "-q:v", str(QUALITY_JPEG.get(quality, 8)),
                "-vf", (
                    f"scale={cap_w}:{cap_h}:"
                    f"force_original_aspect_ratio=decrease:flags=fast_bilinear,"
                    f"pad={cap_w}:{cap_h}:(ow-iw)/2:(oh-ih)/2:color=#080810"
                ),
                tmp_path,
            ],
            capture_output=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )

        if result.returncode == 0 and os.path.exists(tmp_path):
            img = Image.open(tmp_path).convert("RGB")
            img.load()
            return img

    except Exception:
        pass
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
    return None


def _apply_cyberpunk_fx(img: Image.Image) -> Image.Image:
    """Apply Cyberpunk 2077 aesthetic to a tile image:
    - Faint circuit-board grid overlay
    - Neon red border with multi-layer glow
    - Corner bracket decorations
    - Scanline darkening
    """
    import random

    # Work on an RGBA copy so alpha blending works, then convert back
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = base.size
    if w < 4 or h < 4:
        return img  # too small to decorate

    # 1. Circuit grid (no scanlines — they obscure the camera feed) — sparse faint lines with node dots
    grid = 40
    line_col = (255, 0, 60, 18)
    node_col = (255, 0, 60, 35)
    for x in range(0, w, grid):
        draw.line([(x, 0), (x, h - 1)], fill=line_col, width=1)
    for y in range(0, h, grid):
        draw.line([(0, y), (w - 1, y)], fill=line_col, width=1)
    rng = random.Random(42)
    for x in range(grid, w, grid):
        for y in range(grid, h, grid):
            if rng.random() < 0.3:
                draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=node_col)

    # 3. Corner brackets — yellow accent, always sorted coords
    bk   = (252, 238, 9, 230)
    blen = min(18, w // 4, h // 4)
    btk  = 2
    # (corner_x, corner_y, x_dir, y_dir)
    corners = [(0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)]
    for cx, cy, dx, dy in corners:
        # horizontal arm — sort so x0 <= x1, y0 <= y1
        hx0 = min(cx, cx + dx * blen)
        hx1 = max(cx, cx + dx * blen)
        hy0 = min(cy, cy + dy * btk)
        hy1 = max(cy, cy + dy * btk)
        draw.rectangle([hx0, hy0, hx1, hy1], fill=bk)
        # vertical arm
        vx0 = min(cx, cx + dx * btk)
        vx1 = max(cx, cx + dx * btk)
        vy0 = min(cy, cy + dy * blen)
        vy1 = max(cy, cy + dy * blen)
        draw.rectangle([vx0, vy0, vx1, vy1], fill=bk)

    # Composite overlay onto base and return as RGB
    result = Image.alpha_composite(base, overlay)
    return result.convert("RGB")


def make_offline_image() -> Image.Image:
    is_cp = _SKIN.get("style", {}).get("tile_fx") == "cyberpunk"
    bg_col   = (5, 3, 8)     if is_cp else (8, 8, 16)
    grid_col = (30, 0, 10)   if is_cp else (18, 18, 30)
    txt_col  = (255, 0, 60)  if is_cp else (160, 30, 40)
    dot_col  = (252, 238, 9) if is_cp else (160, 30, 40)
    txt      = "[ OFFLINE ]" if is_cp else "OFFLINE"

    img  = Image.new("RGB", (THUMB_W, THUMB_H), bg_col)
    draw = ImageDraw.Draw(img)
    step = 20 if is_cp else 32
    for x in range(0, THUMB_W, step):
        draw.line([(x, 0), (x, THUMB_H)], fill=grid_col, width=1)
    for y in range(0, THUMB_H, step):
        draw.line([(0, y), (THUMB_W, y)], fill=grid_col, width=1)
    try:
        fnt = ImageFont.truetype("arialbd.ttf", 20)
    except:
        fnt = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), txt, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((THUMB_W - tw) // 2, (THUMB_H - th) // 2), txt, fill=txt_col, font=fnt)
    if is_cp:
        # Yellow triangle indicator instead of dot
        cx, cy = 12, 10
        draw.polygon([(cx, cy-6), (cx+10, cy), (cx, cy+6)], fill=dot_col)
        # Apply the full cyberpunk FX pipeline
        img = _apply_cyberpunk_fx(img)
    else:
        draw.ellipse([8, 8, 18, 18], fill=dot_col)
    return img


# ── M3U parser ────────────────────────────────────────────────────────────────

def parse_m3u(path: str) -> list[dict]:
    cameras = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        name = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                m = re.search(r',(.+)$', line)
                name = m.group(1).strip() if m else "Camera"
            elif line and not line.startswith("#"):
                cameras.append({"name": name or "Camera", "url": line})
                name = None
    except Exception as e:
        messagebox.showerror("Playlist Error", str(e))
    return cameras


# ── Main App ──────────────────────────────────────────────────────────────────

# ── Color Picker Dialog ───────────────────────────────────────────────────────

class ColorPickerDialog(tk.Toplevel):
    """Excel-style two-tab color picker: Standard presets + Custom RGB/Hex."""

    # Organized like Excel: columns = hue families, rows = dark→light
    # 10 columns: Grey | Red | Orange | Yellow | Lime | Green | Teal | Blue | Indigo | Purple
    # 8 rows: black→very dark→dark→mid→bright→light→very light→white
    PRESETS = [
        # Row 1 — near-black / very dark
        "#000000","#1a0000","#1a0d00","#1a1a00","#0d1a00","#001a00","#001a0d","#000d1a","#00001a","#0d001a",
        # Row 2 — dark
        "#1a1a1a","#4d0000","#4d2600","#4d4d00","#264d00","#004d00","#004d26","#00264d","#00004d","#26004d",
        # Row 3 — medium dark
        "#333333","#800000","#803f00","#808000","#408000","#008000","#00803f","#00408c","#000080","#40008c",
        # Row 4 — medium / standard
        "#666666","#cc0000","#cc6600","#cccc00","#66cc00","#00cc00","#00cc66","#0066cc","#0000cc","#6600cc",
        # Row 5 — standard bright
        "#999999","#ff0000","#ff6600","#ffcc00","#99ff00","#00ff00","#00ff99","#0099ff","#0000ff","#9900ff",
        # Row 6 — bright / vivid
        "#b3b3b3","#ff3333","#ff8533","#ffdd33","#aaff33","#33ff33","#33ffaa","#33aaff","#3333ff","#aa33ff",
        # Row 7 — light
        "#cccccc","#ff8080","#ffb380","#ffee80","#ccff80","#80ff80","#80ffcc","#80ccff","#8080ff","#cc80ff",
        # Row 8 — very light / near-white
        "#ffffff","#ffcccc","#ffddb3","#fffacc","#eeffcc","#ccffcc","#ccffee","#cce8ff","#ccccff","#eeccff",
    ]

    def __init__(self, parent, initial_color: str = "#ffffff", title: str = "Pick Color"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg="#1a1a2e")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._current = initial_color

        # Parse initial color
        self._r, self._g, self._b = self._hex_to_rgb(initial_color)

        # ── Tab bar ──────────────────────────────────────────────────────────
        tab_bar = tk.Frame(self, bg="#1a1a2e")
        tab_bar.pack(fill="x", padx=8, pady=(8,0))
        self._active_tab = "Standard"
        self._std_lbl = tk.Label(tab_bar, text="Standard", bg="#1a1a2e", fg="#4070ff",
                                  font=("Consolas", 9, "bold"), padx=12, pady=4, cursor="hand2")
        self._std_lbl.pack(side="left")
        self._cus_lbl = tk.Label(tab_bar, text="Custom", bg="#1a1a2e", fg="#606080",
                                  font=("Consolas", 9), padx=12, pady=4, cursor="hand2")
        self._cus_lbl.pack(side="left")
        self._std_lbl.bind("<Button-1>", lambda e: self._show_tab("Standard"))
        self._cus_lbl.bind("<Button-1>", lambda e: self._show_tab("Custom"))
        tk.Frame(self, bg="#4070ff", height=1).pack(fill="x", padx=8)

        # ── Content ───────────────────────────────────────────────────────────
        self._content = tk.Frame(self, bg="#1a1a2e")
        self._content.pack(fill="both", padx=8, pady=8)

        # ── Preview + buttons ────────────────────────────────────────────────
        btm = tk.Frame(self, bg="#1a1a2e")
        btm.pack(fill="x", padx=8, pady=(0,8))

        preview_frame = tk.Frame(btm, bg="#1a1a2e")
        preview_frame.pack(side="left")
        tk.Label(preview_frame, text="New", bg="#1a1a2e", fg="#606080",
                 font=("Consolas", 7)).pack()
        self._new_swatch = tk.Frame(preview_frame, bg=initial_color, width=40, height=24)
        self._new_swatch.pack()
        tk.Label(preview_frame, text="Current", bg="#1a1a2e", fg="#606080",
                 font=("Consolas", 7)).pack()
        self._cur_swatch = tk.Frame(preview_frame, bg=initial_color, width=40, height=24)
        self._cur_swatch.pack()

        btn_frame = tk.Frame(btm, bg="#1a1a2e")
        btn_frame.pack(side="right")
        ok = tk.Button(btn_frame, text="OK", bg="#4070ff", fg="white",
                       font=("Consolas", 8), relief="flat", padx=16, pady=4,
                       cursor="hand2", command=self._on_ok)
        ok.pack(side="top", pady=(0,4))
        cancel = tk.Button(btn_frame, text="Cancel", bg="#1a1a30", fg="#c0c0e0",
                           font=("Consolas", 8), relief="flat", padx=16, pady=4,
                           cursor="hand2", command=self.destroy)
        cancel.pack(side="top")

        self._show_tab("Standard")

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - self.winfo_width()  // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - self.winfo_height() // 2
        self.geometry(f"+{px}+{py}")
        self.wait_window()

    def _show_tab(self, name: str):
        self._active_tab = name
        for w in self._content.winfo_children():
            w.destroy()
        if name == "Standard":
            self._std_lbl.config(fg="#4070ff", font=("Consolas", 9, "bold"))
            self._cus_lbl.config(fg="#606080", font=("Consolas", 9))
            self._build_standard()
        else:
            self._std_lbl.config(fg="#606080", font=("Consolas", 9))
            self._cus_lbl.config(fg="#4070ff", font=("Consolas", 9, "bold"))
            self._build_custom()

    def _build_standard(self):
        f = self._content
        tk.Label(f, text="Colors:", bg="#1a1a2e", fg="#808090",
                 font=("Consolas", 8)).pack(anchor="w", pady=(0,4))
        grid = tk.Frame(f, bg="#1a1a2e")
        grid.pack()
        cols = 10
        for i, color in enumerate(self.PRESETS):
            row, col = divmod(i, cols)
            swatch = tk.Frame(grid, bg=color, width=22, height=18, cursor="hand2")
            swatch.grid(row=row, column=col, padx=1, pady=1)
            # Click selects — hover only highlights border, does NOT preview
            swatch.bind("<Button-1>", lambda e, c=color: self._select(c))
            swatch.bind("<Enter>", lambda e, s=swatch: s.config(relief="solid", bd=2))
            swatch.bind("<Leave>", lambda e, s=swatch: s.config(relief="flat", bd=0))

    def _build_custom(self):
        import math
        f = self._content

        # Hue-saturation canvas
        hs_size = 200
        self._hs_canvas = tk.Canvas(f, width=hs_size, height=hs_size,
                                     highlightthickness=1, highlightbackground="#252540")
        self._hs_canvas.pack(pady=(0, 8))
        self._draw_hs_canvas(hs_size)
        self._hs_canvas.bind("<Button-1>",   self._hs_click)
        self._hs_canvas.bind("<B1-Motion>",  self._hs_click)

        # Value (brightness) slider
        val_frame = tk.Frame(f, bg="#1a1a2e")
        val_frame.pack(fill="x", pady=(0,8))
        tk.Label(val_frame, text="Brightness", bg="#1a1a2e", fg="#808090",
                 font=("Consolas", 7), width=10, anchor="w").pack(side="left")
        self._val_var = tk.DoubleVar(value=self._rgb_to_hsv(self._r, self._g, self._b)[2])
        val_slider = tk.Scale(val_frame, from_=0, to=1, resolution=0.01,
                              orient="horizontal", variable=self._val_var,
                              bg="#1a1a2e", fg="#c0c0e0", troughcolor="#252540",
                              highlightthickness=0, sliderlength=12, length=160,
                              command=lambda v: self._on_val_change())
        val_slider.pack(side="left")

        # RGB entries
        rgb_frame = tk.Frame(f, bg="#1a1a2e")
        rgb_frame.pack(fill="x", pady=(0,4))
        self._rgb_vars = []
        for label, val in [("R", self._r), ("G", self._g), ("B", self._b)]:
            col = tk.Frame(rgb_frame, bg="#1a1a2e")
            col.pack(side="left", padx=4)
            tk.Label(col, text=label, bg="#1a1a2e", fg="#808090",
                     font=("Consolas", 8)).pack()
            var = tk.StringVar(value=str(val))
            e = tk.Entry(col, textvariable=var, width=4,
                         bg="#12121f", fg="#c0c0e0", insertbackground="#c0c0e0",
                         relief="flat", font=("Consolas", 9),
                         highlightbackground="#252540", highlightthickness=1)
            e.pack()
            self._rgb_vars.append(var)
            var.trace_add("write", lambda *a: self._on_rgb_entry())

        # Hex entry
        hex_frame = tk.Frame(f, bg="#1a1a2e")
        hex_frame.pack(fill="x", pady=(4,0))
        tk.Label(hex_frame, text="Hex", bg="#1a1a2e", fg="#808090",
                 font=("Consolas", 8), width=10, anchor="w").pack(side="left")
        self._hex_var = tk.StringVar(value=self._rgb_to_hex(self._r, self._g, self._b))
        hex_e = tk.Entry(hex_frame, textvariable=self._hex_var, width=10,
                         bg="#12121f", fg="#c0c0e0", insertbackground="#c0c0e0",
                         relief="flat", font=("Consolas", 9),
                         highlightbackground="#252540", highlightthickness=1)
        hex_e.pack(side="left", padx=4)
        self._hex_var.trace_add("write", lambda *a: self._on_hex_entry())
        self._updating = False

    def _draw_hs_canvas(self, size):
        """Draw hue-saturation gradient."""
        v = self._val_var.get() if hasattr(self, "_val_var") else 1.0
        img = Image.new("RGB", (size, size))
        pixels = img.load()
        for y in range(size):
            for x in range(size):
                h = x / size
                s = 1 - y / size
                r, g, b = self._hsv_to_rgb(h, s, v)
                pixels[x, y] = (r, g, b)
        self._hs_photo = ImageTk.PhotoImage(img)
        self._hs_canvas.create_image(0, 0, anchor="nw", image=self._hs_photo)
        # Draw crosshair at current color position
        h, s, v = self._rgb_to_hsv(self._r, self._g, self._b)
        cx = int(h * size)
        cy = int((1 - s) * size)
        self._hs_canvas.create_oval(cx-5, cy-5, cx+5, cy+5,
                                     outline="white", width=2, tags="cursor")

    def _hs_click(self, event):
        size = 200
        h = max(0, min(1, event.x / size))
        s = max(0, min(1, 1 - event.y / size))
        v = self._val_var.get()
        self._r, self._g, self._b = self._hsv_to_rgb(h, s, v)
        self._update_from_rgb()

    def _on_val_change(self):
        h, s, _ = self._rgb_to_hsv(self._r, self._g, self._b)
        v = self._val_var.get()
        self._r, self._g, self._b = self._hsv_to_rgb(h, s, v)
        self._update_from_rgb()

    def _on_rgb_entry(self):
        if self._updating: return
        try:
            r = max(0, min(255, int(self._rgb_vars[0].get())))
            g = max(0, min(255, int(self._rgb_vars[1].get())))
            b = max(0, min(255, int(self._rgb_vars[2].get())))
            self._r, self._g, self._b = r, g, b
            self._updating = True
            self._hex_var.set(self._rgb_to_hex(r, g, b))
            self._updating = False
            self._preview(self._rgb_to_hex(r, g, b))
        except Exception:
            pass

    def _on_hex_entry(self):
        if self._updating: return
        try:
            val = self._hex_var.get().strip().lstrip("#")
            if len(val) == 6:
                r, g, b = int(val[0:2],16), int(val[2:4],16), int(val[4:6],16)
                self._r, self._g, self._b = r, g, b
                self._updating = True
                self._rgb_vars[0].set(str(r))
                self._rgb_vars[1].set(str(g))
                self._rgb_vars[2].set(str(b))
                self._updating = False
                self._preview(f"#{val}")
                self._draw_hs_canvas(200)
        except Exception:
            pass

    def _update_from_rgb(self):
        if not hasattr(self, "_rgb_vars"): return
        self._updating = True
        self._rgb_vars[0].set(str(self._r))
        self._rgb_vars[1].set(str(self._g))
        self._rgb_vars[2].set(str(self._b))
        self._hex_var.set(self._rgb_to_hex(self._r, self._g, self._b))
        self._updating = False
        self._draw_hs_canvas(200)
        self._preview(self._rgb_to_hex(self._r, self._g, self._b))

    def _preview(self, color: str):
        try:
            self._new_swatch.config(bg=color)
            self._current = color
        except Exception:
            pass

    def _select(self, color: str):
        self._current = color
        r, g, b = self._hex_to_rgb(color)
        self._r, self._g, self._b = r, g, b
        self._preview(color)

    def _on_ok(self):
        self.result = self._current
        self.destroy()

    # ── Color math helpers ────────────────────────────────────────────────────
    @staticmethod
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

    @staticmethod
    def _rgb_to_hex(r, g, b) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _rgb_to_hsv(r, g, b):
        r, g, b = r/255, g/255, b/255
        mx = max(r,g,b); mn = min(r,g,b); d = mx - mn
        if d == 0:   h = 0
        elif mx == r: h = ((g-b)/d) % 6 / 6
        elif mx == g: h = ((b-r)/d + 2) / 6
        else:         h = ((r-g)/d + 4) / 6
        s = 0 if mx == 0 else d/mx
        return h, s, mx

    @staticmethod
    def _hsv_to_rgb(h, s, v):
        import math
        if s == 0:
            c = int(v*255)
            return c, c, c
        i = int(h*6)
        f = h*6 - i
        p,q,t = v*(1-s), v*(1-f*s), v*(1-(1-f)*s)
        segs = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)]
        r,g,b = segs[i%6]
        return int(r*255), int(g*255), int(b*255)



# ── Skin security validator ───────────────────────────────────────────────────

_VALID_COLOR_KEYS = {
    "BG","TILE_BG","TILE_BORDER","TILE_HOVER","ACCENT","ACCENT_DIM",
    "OFFLINE_RED","ONLINE_GREEN","TEXT","TEXT_DIM",
    "SETTINGS_BG","INPUT_BG","INPUT_BD","BTN_BG","BTN_HOVER"
}
_VALID_STYLE_KEYS = {
    "title","dot_char","close_char","gear_char","fs_char","drag_char",
    "border_width","title_bar_height","settings_relief","tile_fx"
}
_VALID_TILE_FX = {"cyberpunk", None, ""}
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

def _validate_skin_file(path: str) -> dict:
    """Load and strictly validate a skin JSON. Raises ValueError on any violation."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            skin = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    if not isinstance(skin, dict):
        raise ValueError("Skin must be a JSON object")

    # Only allow known top-level keys
    allowed_top = {"name","author","font_family","colors","style"}
    for k in skin:
        if k not in allowed_top:
            raise ValueError(f"Unknown skin key: '{k}'")

    # Validate colors
    colors = skin.get("colors", {})
    if not isinstance(colors, dict):
        raise ValueError("'colors' must be an object")
    for k, v in colors.items():
        if k not in _VALID_COLOR_KEYS:
            raise ValueError(f"Unknown color key: '{k}'")
        if not isinstance(v, str) or not _HEX_RE.match(v):
            raise ValueError(f"Color '{k}' must be a 6-digit hex string like #ff0000, got: {v!r}")

    # Validate style
    style = skin.get("style", {})
    if not isinstance(style, dict):
        raise ValueError("'style' must be an object")
    for k, v in style.items():
        if k not in _VALID_STYLE_KEYS:
            raise ValueError(f"Unknown style key: '{k}'")
    tile_fx = style.get("tile_fx")
    if tile_fx not in _VALID_TILE_FX:
        raise ValueError(f"Unknown tile_fx value: '{tile_fx}'. Allowed: {_VALID_TILE_FX}")

    # Validate font_family — string only, no code
    ff = skin.get("font_family", "Consolas")
    _bad = set(""";'"(){}[]""")
    if not isinstance(ff, str) or len(ff) > 64 or any(c in _bad for c in ff):
        raise ValueError(f"Invalid font_family: {ff!r}")

    return skin



try:
    from tkinterdnd2 import TkinterDnD as _TkinterDnD
    _AppBase = _TkinterDnD.Tk
except ImportError:
    _AppBase = tk.Tk

class Synopticon(_AppBase):
    def __init__(self):
        super().__init__()
        self.title("Synopticon")
        try:
            _ico = os.path.join(BUNDLE_DIR, "synopticon.ico")
            if os.path.isfile(_ico):
                self.iconbitmap(_ico)
        except Exception:
            pass
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(400, 300)

        self._cameras: list[dict] = []
        self._tiles:   list[dict] = []
        self._cam_order: list[int] = []
        self._refresh_job = None
        self._refreshing = False
        self._interval = DEFAULT_INTERVAL
        self._cols     = DEFAULT_COLS
        self._settings_open = False
        self._hotkey = "r"
        self._drag_tile = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_moved = False
        self._click_consumed = False
        self._resize_job = None
        self._countdown_tag = None
        self._quality = "Lowest"  # Lowest / Medium / Highest
        self._player_path = ""       # empty = system default
        self._fullscreen = False
        self._autoload_files: list[str] = []  # paths to auto-load on start
        self._active_skin_path: str = ""     # path to active skin .json
        self._captures: dict[str, PersistentCapture] = {}  # url -> PersistentCapture

        self._build_ui()
        self._bind_hotkey()
        self._load_config()
        # Clean up persistent captures on window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Show grid if autoload populated cameras, otherwise show empty prompt
        if self._cameras:
            self._rebuild_grid()
            self._schedule_refresh(delay=0.2)
        else:
            self._show_empty()
        self._setup_dnd()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=PAD, pady=(PAD, 0))
        self._top_bar = bar

        self._title_lbl = tk.Label(bar, text=S_TITLE, bg=BG, fg=ACCENT,
                 font=(FONT_FAMILY, 11, "bold"))
        self._title_lbl.pack(side="left")

        self._gear_btn = tk.Label(bar, text=S_GEAR, bg=BG, fg=TEXT_DIM,
                                  font=("Segoe UI", 14), cursor="hand2")
        self._gear_btn.pack(side="right", padx=(4, 4))
        self._gear_btn.bind("<Button-1>", lambda e: self._toggle_settings())
        self._gear_btn.bind("<Enter>",    lambda e: self._gear_btn.config(fg=TEXT))
        self._gear_btn.bind("<Leave>",    lambda e: self._gear_btn.config(
            fg=ACCENT if self._settings_open else TEXT_DIM))

        self._fs_btn = tk.Label(bar, text=S_FS, bg=BG, fg=TEXT_DIM,
                                font=("Segoe UI", 12), cursor="hand2")
        self._fs_btn.pack(side="right", padx=(0, 4))
        self._fs_btn.bind("<Button-1>", lambda e: self._toggle_fullscreen())
        self._fs_btn.bind("<Enter>",    lambda e: self._fs_btn.config(fg=TEXT))
        self._fs_btn.bind("<Leave>",    lambda e: self._fs_btn.config(fg=TEXT_DIM))

        self._status_lbl = tk.Label(bar, text="", bg=BG, fg=TEXT_DIM,
                                    font=("Consolas", 8))
        # status_lbl kept for internal use but not packed/visible

        # Settings panel placeholder (inserted between prog and grid when open)
        self._settings_frame = tk.Frame(self, bg=SETTINGS_BG,
                                        highlightbackground=INPUT_BD,
                                        highlightthickness=1)

        # Grid area
        self._grid_outer = tk.Frame(self, bg=BG)
        self._grid_outer.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        self._grid_frame = tk.Frame(self._grid_outer, bg=BG)
        self._grid_frame.pack(fill="both", expand=True)

        # Fullscreen keybinds
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.bind("<Escape>", lambda e: self._exit_fullscreen())

        # Drag and drop via tkinterdnd2 (registered in __init__ after build)

    def _build_settings_panel(self):
        f = self._settings_frame
        for w in f.winfo_children():
            w.destroy()

        TABS = ["Streams", "Playback", "General", "Appearance"]
        if not hasattr(self, "_active_tab"):
            self._active_tab = "Streams"

        # ── Tab bar ──────────────────────────────────────────────────────────
        tab_bar = tk.Frame(f, bg=SETTINGS_BG)
        tab_bar.pack(fill="x")

        # Bottom border line under whole tab bar
        tk.Frame(f, bg=ACCENT, height=1).pack(fill="x")

        self._tab_labels = {}
        for name in TABS:
            is_active = (name == self._active_tab)
            lbl = tk.Label(tab_bar, text=name,
                           bg=SETTINGS_BG,
                           fg=TEXT if is_active else TEXT_DIM,
                           font=("Consolas", 8, "bold" if is_active else "normal"),
                           padx=16, pady=6, cursor="hand2")
            lbl.pack(side="left")
            self._tab_labels[name] = lbl
            lbl.bind("<Button-1>", lambda e, n=name: self._switch_tab(n))
            # Active tab: accent underline drawn as a child frame overlay
            if is_active:
                lbl.config(fg=ACCENT)
                bar = tk.Frame(lbl, bg=ACCENT, height=2)
                bar.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")

        # ── Content area ─────────────────────────────────────────────────────
        content = tk.Frame(f, bg=SETTINGS_BG)
        content.pack(fill="x")
        self._tab_content = content

        ro = dict(bg=SETTINGS_BG, pady=6, padx=16)

        if self._active_tab == "Streams":
            # Playlist actions
            r0 = tk.Frame(content, **ro); r0.pack(fill="x")
            tk.Label(r0, text="PLAYLIST", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._btn(r0, "Load .m3u", self._load_playlist).pack(side="left", padx=(0, 4))
            self._btn(r0, "+ Add URL", self._show_add_url).pack(side="left", padx=4)

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            # Camera list
            r3 = tk.Frame(content, **ro); r3.pack(fill="x")
            tk.Label(r3, text="CAMERAS", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._btn(r3, "Clear all", self._clear_cameras).pack(side="left")

            self._cam_list_frame = tk.Frame(content, bg=SETTINGS_BG)
            self._cam_list_frame.pack(fill="x", padx=16, pady=(0, 4))
            self._refresh_cam_list()


        elif self._active_tab == "Playback":
            # Interval
            r1 = tk.Frame(content, **ro); r1.pack(fill="x")
            tk.Label(r1, text="REFRESH (sec)", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._interval_var = tk.StringVar(value=str(self._interval))
            tk.Entry(r1, textvariable=self._interval_var, width=6,
                     bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=("Consolas", 10),
                     highlightbackground=INPUT_BD, highlightthickness=1).pack(side="left", padx=(0, 8))
            self._btn(r1, "Apply", self._apply_interval).pack(side="left")
            self._btn(r1, "⟳ Refresh Now", self._manual_refresh, accent=True).pack(side="left", padx=(8, 0))

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            # Columns per row
            r_cols = tk.Frame(content, **ro); r_cols.pack(fill="x")
            tk.Label(r_cols, text="COLUMNS", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=(FONT_FAMILY, 7, "bold"), width=16, anchor="w").pack(side="left")
            self._cols_var = tk.StringVar(value=str(self._cols))
            tk.Entry(r_cols, textvariable=self._cols_var, width=4,
                     bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=(FONT_FAMILY, 10),
                     highlightbackground=INPUT_BD, highlightthickness=1).pack(side="left", padx=(0, 8))
            def apply_cols():
                try:
                    val = int(self._cols_var.get())
                    if val < 1: raise ValueError
                    self._cols = val
                    self._rebuild_grid()
                    self._schedule_refresh(delay=0.2)
                except ValueError:
                    messagebox.showwarning("Invalid", "Enter a whole number ≥ 1.")
            self._btn(r_cols, "Apply", apply_cols).pack(side="left")
            tk.Label(r_cols, text="cameras per row  (default: 3)",
                     bg=SETTINGS_BG, fg=TEXT_DIM, font=(FONT_FAMILY, 7)).pack(side="left", padx=8)

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            # Quality
            r_q = tk.Frame(content, **ro); r_q.pack(fill="x")
            tk.Label(r_q, text="QUALITY", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._quality_var = tk.StringVar(value=self._quality)
            quality_menu = tk.OptionMenu(r_q, self._quality_var, *QUALITY_LEVELS,
                                         command=lambda v: self._apply_quality(v))
            quality_menu.config(bg=INPUT_BG, fg=TEXT, activebackground=ACCENT,
                                activeforeground="white", relief="flat",
                                highlightthickness=0, font=("Consolas", 8), bd=0)
            quality_menu["menu"].config(bg=INPUT_BG, fg=TEXT, activebackground=ACCENT,
                                        activeforeground="white", font=("Consolas", 8))
            quality_menu.pack(side="left")

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            # Hotkey
            r2 = tk.Frame(content, **ro); r2.pack(fill="x")
            tk.Label(r2, text="HOTKEY", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._hotkey_var = tk.StringVar(value=self._hotkey)
            tk.Entry(r2, textvariable=self._hotkey_var, width=4,
                     bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=("Consolas", 10),
                     highlightbackground=INPUT_BD, highlightthickness=1).pack(side="left", padx=(0, 8))
            self._btn(r2, "Set", self._apply_hotkey).pack(side="left")

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            # Video player (for tile click open)
            r_p = tk.Frame(content, **ro); r_p.pack(fill="x")
            tk.Label(r_p, text="VIDEO PLAYER", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            player_name = os.path.basename(self._player_path) if self._player_path else "System default"
            self._player_lbl = tk.Label(r_p, text=player_name, bg=SETTINGS_BG, fg=TEXT,
                                        font=("Consolas", 8))
            self._player_lbl.pack(side="left", padx=(0, 8))
            self._btn(r_p, "Browse…", self._browse_player).pack(side="left")
            self._btn(r_p, "Reset", self._reset_player).pack(side="left", padx=4)

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            tk.Label(r_lq,
                     text="  Low Latency = fastest, may buffer  |  High Quality = smoothest, more delay",
                     bg=SETTINGS_BG, fg=TEXT_DIM, font=(FONT_FAMILY, 7)).pack(side="left", padx=8)

        elif self._active_tab == "General":
            # Auto-load files
            r_al = tk.Frame(content, **ro); r_al.pack(fill="x")
            tk.Label(r_al, text="AUTO-LOAD", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._btn(r_al, "+ Add File", self._add_autoload_file).pack(side="left", padx=(0, 4))
            self._btn(r_al, "Clear all", self._clear_autoload_files).pack(side="left", padx=4)

            self._autoload_list_frame = tk.Frame(content, bg=SETTINGS_BG)
            self._autoload_list_frame.pack(fill="x", padx=16, pady=(0, 4))
            self._refresh_autoload_list()

            tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

            r_save = tk.Frame(content, **ro); r_save.pack(fill="x")
            tk.Label(r_save, text="CONFIG", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 7, "bold"), width=16, anchor="w").pack(side="left")
            self._btn(r_save, "💾  Save as Default", self._save_config, accent=True).pack(side="left")
            self._btn(r_save, "↺  Reset to Default", self._reset_config).pack(side="left", padx=8)
            tk.Label(r_save, text=APP_VERSION, bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=(FONT_FAMILY, 6)).pack(side="right", padx=8)

        elif self._active_tab == "Appearance":
            self._build_appearance_tab(content, ro)


    def _build_appearance_tab(self, content, ro):
        """Appearance tab — skin dropdown + color overrides."""
        available = _get_available_skins()

        r_skin = tk.Frame(content, **ro); r_skin.pack(fill="x")
        tk.Label(r_skin, text="SKIN", bg=SETTINGS_BG, fg=TEXT_DIM,
                 font=(FONT_FAMILY, 7, "bold"), width=14, anchor="w").pack(side="left")

        if not available:
            tk.Label(r_skin, text="No .json skins found in skins/ folder",
                     bg=SETTINGS_BG, fg=TEXT_DIM, font=(FONT_FAMILY, 8)).pack(side="left")
        else:
            skin_names  = list(available.keys())
            current     = _SKIN.get("name", skin_names[0])
            if current not in skin_names:
                current = skin_names[0]
            skin_var = tk.StringVar(value=current)

            om = tk.OptionMenu(r_skin, skin_var, *skin_names)
            om.config(bg=INPUT_BG, fg=TEXT, activebackground=ACCENT,
                      activeforeground=_contrast_color(ACCENT),
                      relief="flat", highlightthickness=0,
                      font=(FONT_FAMILY, 8), bd=0)
            om["menu"].config(bg=INPUT_BG, fg=TEXT,
                              activebackground=ACCENT,
                              activeforeground=_contrast_color(ACCENT),
                              font=(FONT_FAMILY, 8))
            om.pack(side="left", padx=(0, 8))

            def apply_skin_dropdown(*_):
                name = skin_var.get()
                path = available.get(name)
                if not path:
                    return
                try:
                    skin = _validate_skin_file(path)
                    _apply_skin(skin)
                    self._active_skin_path = path
                    self._apply_appearance()
                except ValueError as e:
                    messagebox.showerror("Skin Error", f"Invalid skin file:\n{e}")
                except Exception as e:
                    messagebox.showerror("Skin Error", str(e))

            skin_var.trace_add("write", apply_skin_dropdown)

        tk.Frame(content, bg=INPUT_BD, height=1).pack(fill="x", padx=16)

        # Color overrides
        r_ov = tk.Frame(content, **ro); r_ov.pack(fill="x")
        tk.Label(r_ov, text="OVERRIDE", bg=SETTINGS_BG, fg=TEXT_DIM,
                 font=(FONT_FAMILY, 7, "bold"), width=14, anchor="w").pack(side="left")
        tk.Label(r_ov, text="Fine-tune individual colors on top of the active skin:",
                 bg=SETTINGS_BG, fg=TEXT_DIM, font=(FONT_FAMILY, 7)).pack(side="left")

        COLOR_TARGETS = [
            ("Background",  "BG"),
            ("Text",        "TEXT"),
            ("Accent",      "ACCENT"),
            ("Settings BG", "SETTINGS_BG"),
            ("Dim Text",    "TEXT_DIM"),
            ("Tile Border", "TILE_BORDER"),
        ]
        c = _SKIN.get("colors", {})
        for label, key in COLOR_TARGETS:
            row = tk.Frame(content, bg=SETTINGS_BG, padx=16, pady=2)
            row.pack(fill="x")
            tk.Label(row, text=label, bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=(FONT_FAMILY, 7), width=13, anchor="w").pack(side="left")
            cur_col = c.get(key, "#000000")
            swatch  = tk.Frame(row, bg=cur_col, width=20, height=14)
            swatch.pack(side="left", padx=(0, 4))
            hex_lbl = tk.Label(row, text=cur_col, bg=SETTINGS_BG, fg=TEXT,
                               font=(FONT_FAMILY, 7), width=8)
            hex_lbl.pack(side="left")
            def make_picker(k=key, sw=swatch, lbl=hex_lbl):
                def pick():
                    result = ColorPickerDialog(self,
                        _SKIN.get("colors", {}).get(k, "#000000"),
                        title=f"Pick — {k}").result
                    if result:
                        colors = dict(_SKIN.get("colors", {}))
                        colors[k] = result
                        merged = dict(_SKIN); merged["colors"] = colors
                        _apply_skin(merged)
                        sw.config(bg=result); lbl.config(text=result)
                        self._apply_appearance()
                return pick
            self._btn(row, "Pick…", make_picker()).pack(side="left", padx=4)
    def _apply_appearance(self):
        """Rebuild the entire UI to apply the current skin."""
        # Guard against re-entrant calls (rapid skin switching)
        if getattr(self, "_rebuilding", False):
            return
        self._rebuilding = True
        self._click_consumed = True  # prevent tile clicks during rebuild

        # Step 1: kill the refresh loop completely and wait for any running
        # thread to finish before touching widgets
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = None
        self._refreshing  = False
        self._stop_all_captures()

        for widget in self.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass

        self._tiles.clear()
        self._settings_open = False

        # Step 3: rebuild
        self._build_ui()
        self._bind_hotkey()
        self._setup_dnd()
        if self._cameras:
            self._rebuild_grid()
            self._schedule_refresh(delay=0.5)
        else:
            self._show_empty()

        # Step 4: reopen settings on appearance tab
        self._settings_open = True
        self._settings_frame.pack(fill="x", padx=PAD, pady=(4, 0),
                                  before=self._grid_outer)
        self._gear_btn.config(fg=ACCENT)
        self._active_tab = "Appearance"
        self._build_settings_panel()

        self._click_consumed = False
        self._rebuilding = False

    def _switch_tab(self, name: str):
        self._active_tab = name
        self._build_settings_panel()

    # ── Auto-load files ──────────────────────────────────────────────────────

    def _add_autoload_file(self):
        path = filedialog.askopenfilename(
            title="Select Playlist File",
            filetypes=[("Playlist files", "*.m3u *.m3u8"), ("All files", "*.*")]
        )
        if path:
            path = os.path.abspath(path)
            if path not in self._autoload_files:
                self._autoload_files.append(path)
                self._refresh_autoload_list()

    def _remove_autoload_file(self, path: str):
        if path in self._autoload_files:
            self._autoload_files.remove(path)
        self._refresh_autoload_list()

    def _clear_autoload_files(self):
        self._autoload_files.clear()
        self._refresh_autoload_list()

    def _refresh_autoload_list(self):
        if not hasattr(self, "_autoload_list_frame"):
            return
        for w in self._autoload_list_frame.winfo_children():
            w.destroy()
        if not self._autoload_files:
            tk.Label(self._autoload_list_frame, text="  (none)",
                     bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 8)).pack(anchor="w")
            return
        for path in list(self._autoload_files):
            row = tk.Frame(self._autoload_list_frame, bg=SETTINGS_BG)
            row.pack(fill="x", pady=1)
            name = os.path.basename(path)
            tk.Label(row, text=f"  {name}", bg=SETTINGS_BG, fg=TEXT,
                     font=("Consolas", 8), anchor="w").pack(side="left")
            x = tk.Label(row, text="✕", bg=SETTINGS_BG, fg=OFFLINE_RED,
                         font=("Consolas", 8), cursor="hand2")
            x.pack(side="right")
            x.bind("<Button-1>", lambda e, p=path: self._remove_autoload_file(p))

    # ── Config persistence ───────────────────────────────────────────────────

    def _load_config(self):
        """Load saved settings from disk if they exist."""
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            self._interval       = cfg.get("interval",    DEFAULT_INTERVAL)
            self._cols           = cfg.get("cols",        DEFAULT_COLS)
            self._quality        = cfg.get("quality",     "Lowest")
            self._hotkey         = cfg.get("hotkey",      "r")
            self._player_path    = cfg.get("player_path", "")
            self._autoload_files = cfg.get("autoload_files", [])
            self._active_skin_path    = cfg.get("active_skin_path", "")
            if self._active_skin_path and os.path.isfile(self._active_skin_path):
                try:
                    _apply_skin(_load_skin_file(self._active_skin_path))
                except Exception:
                    _apply_skin(DEFAULT_SKIN)
            overrides = cfg.get("skin_overrides", {})
            if overrides and "colors" in overrides:
                _apply_skin(overrides)
            self._active_skin_path    = cfg.get("active_skin_path", "")
            if self._active_skin_path and os.path.isfile(self._active_skin_path):
                try:
                    _apply_skin(_load_skin_file(self._active_skin_path))
                except Exception:
                    _apply_skin(DEFAULT_SKIN)
            overrides = cfg.get("skin_overrides", {})
            if overrides and "colors" in overrides:
                _apply_skin(overrides)
            self._bind_hotkey()
            # Auto-load any saved playlist files
            for path in self._autoload_files:
                if os.path.isfile(path):
                    cams = parse_m3u(path)
                    if cams:
                        self._cameras.extend(cams)
            if self._cameras:
                saved_order = cfg.get("cam_order", [])
                n = len(self._cameras)
                # Validate: must be a permutation of 0..n-1
                if sorted(saved_order) == list(range(n)):
                    self._cam_order = saved_order
                else:
                    self._cam_order = list(range(n))
        except FileNotFoundError:
            pass  # no config yet — use defaults
        except Exception as e:
            print(f"[synopticon] config load error: {e}")

    def _save_config(self):
        """Save current settings to disk — auto-applies any unapplied field values."""
        # Flush interval entry if open
        if hasattr(self, "_interval_var"):
            try:
                val = int(self._interval_var.get())
                if val >= 1:
                    self._interval = val
            except Exception:
                pass
        # Flush hotkey entry if open
        if hasattr(self, "_hotkey_var"):
            key = self._hotkey_var.get().strip().lower()
            if key:
                self._hotkey = key
                self._bind_hotkey()
        cfg = {
            "interval":         self._interval,
            "cols":             self._cols,
            "quality":          self._quality,
            "hotkey":           self._hotkey,
            "player_path":      self._player_path,
            "autoload_files":   self._autoload_files,
            "cam_order":        self._cam_order,
            "active_skin_path":    getattr(self, "_active_skin_path", ""),
            "skin_overrides":   dict(_SKIN),
        }
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            # Flash confirmation in gear button briefly
            self._gear_btn.config(fg=ONLINE_GREEN)
            self.after(1000, lambda: self._gear_btn.config(
                fg=ACCENT if self._settings_open else TEXT_DIM))
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

    def _reset_config(self):
        """Delete saved config and restore defaults."""
        try:
            if os.path.exists(CONFIG_PATH):
                os.remove(CONFIG_PATH)
        except Exception:
            pass
        self._interval       = DEFAULT_INTERVAL
        self._cols           = DEFAULT_COLS
        self._quality        = "Lowest"
        self._hotkey         = "r"
        self._player_path    = ""
        self._autoload_files = []
        self._cam_order      = list(range(len(self._cameras)))
        self._active_skin_path = ""
        _apply_skin(DEFAULT_SKIN)
        self._bind_hotkey()
        # Rebuild settings panel to reflect reset values
        self._build_settings_panel()
        messagebox.showinfo("Reset", "Settings reset to defaults.")

    def _btn(self, parent, text, cmd, accent=False):
        bg = ACCENT if accent else BTN_BG
        fg = _contrast_color(ACCENT) if accent else TEXT
        b = tk.Label(parent, text=text, bg=bg, fg=fg,
                     font=(FONT_FAMILY, 8), padx=8, pady=3,
                     cursor="hand2", relief="flat")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=ACCENT if accent else BTN_HOVER))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _refresh_cam_list(self):
        if not hasattr(self, "_cam_list_frame"):
            return
        for w in self._cam_list_frame.winfo_children():
            w.destroy()
        if not self._cameras:
            tk.Label(self._cam_list_frame, text="  (none)", bg=SETTINGS_BG, fg=TEXT_DIM,
                     font=("Consolas", 8)).pack(anchor="w")
            return

        # Use _cam_order for display so reorder is reflected immediately
        ordered = [self._cameras[i] for i in self._cam_order if i < len(self._cameras)]

        for display_idx, cam in enumerate(ordered):
            row = tk.Frame(self._cam_list_frame, bg=SETTINGS_BG)
            row.pack(fill="x", pady=1)

            # Drag handle
            handle = tk.Label(row, text=S_DRAG, bg=SETTINGS_BG, fg=TEXT_DIM,
                               font=(FONT_FAMILY, 10), cursor="fleur", padx=4)
            handle.pack(side="left")

            # Number + name
            tk.Label(row, text=f"{display_idx + 1}. {cam['name'][:30]}",
                     bg=SETTINGS_BG, fg=TEXT,
                     font=("Consolas", 8), anchor="w").pack(side="left")

            # Remove button
            x_lbl = tk.Label(row, text="✕", bg=SETTINGS_BG, fg=OFFLINE_RED,
                              font=("Consolas", 8), cursor="hand2")
            x_lbl.pack(side="right")
            x_lbl.bind("<Button-1>", lambda e, c=cam: self._remove_camera_by_obj(c))

            # Drag-to-reorder bindings on handle and row
            for widget in (handle, row):
                widget.bind("<ButtonPress-1>",   lambda e, r=row, d=display_idx: self._cl_drag_start(e, r, d))
                widget.bind("<B1-Motion>",        lambda e, d=display_idx: self._cl_drag_motion(e, d))
                widget.bind("<ButtonRelease-1>",  lambda e, d=display_idx: self._cl_drag_end(e, d))

    def _cl_drag_start(self, event, row, display_idx):
        self._cl_drag_idx   = display_idx
        self._cl_drag_y0    = event.y_root
        self._cl_drag_row   = row
        row.config(bg="#1a1a2e")
        for child in row.winfo_children():
            child.config(bg="#1a1a2e")

    def _cl_drag_motion(self, event, display_idx):
        if not hasattr(self, "_cl_drag_idx"):
            return
        frame = self._cam_list_frame
        rows  = [w for w in frame.winfo_children() if isinstance(w, tk.Frame)]
        # Find which row the mouse is over
        for i, row in enumerate(rows):
            y1 = row.winfo_rooty()
            y2 = y1 + row.winfo_height()
            if y1 <= event.y_root <= y2:
                # Highlight target
                for j, r in enumerate(rows):
                    tgt_color = ACCENT + "44" if j == i else SETTINGS_BG
                    r.config(bg=SETTINGS_BG if j != i else "#0d2040")
                break

    def _cl_drag_end(self, event, display_idx):
        if not hasattr(self, "_cl_drag_idx"):
            return
        src_disp = self._cl_drag_idx
        frame    = self._cam_list_frame
        rows     = [w for w in frame.winfo_children() if isinstance(w, tk.Frame)]

        # Find destination row
        dst_disp = src_disp
        for i, row in enumerate(rows):
            y1 = row.winfo_rooty()
            y2 = y1 + row.winfo_height()
            if y1 <= event.y_root <= y2:
                dst_disp = i
                break

        del self._cl_drag_idx

        if src_disp == dst_disp:
            self._refresh_cam_list()
            return

        # Reorder _cam_order using display positions
        ordered = [self._cam_order[i] for i in range(len(self._cam_order))]
        item = ordered.pop(src_disp)
        ordered.insert(dst_disp, item)
        self._cam_order = ordered
        self._rebuild_grid()
        self._refresh_cam_list()

    # ── Settings toggle ───────────────────────────────────────────────────────

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self._settings_frame.pack(fill="x", padx=PAD, pady=(4, 0),
                                      before=self._grid_outer)
            self._gear_btn.config(fg=ACCENT)
            self._build_settings_panel()
        else:
            self._settings_frame.pack_forget()
            self._gear_btn.config(fg=TEXT_DIM)

    # ── Camera management ─────────────────────────────────────────────────────

    def _load_playlist(self):
        path = filedialog.askopenfilename(
            title="Open Playlist",
            filetypes=[("M3U Playlist", "*.m3u *.m3u8"), ("All files", "*.*")]
        )
        if not path:
            return
        cams = parse_m3u(path)
        if cams:
            self._cameras.extend(cams)
            self._cam_order = list(range(len(self._cameras)))
            self._rebuild_grid()
            self._refresh_cam_list()
            # Wait for tkinter to finish rendering canvases before refreshing
            self._schedule_refresh(delay=0.2)

    def _show_add_url(self):
        win = tk.Toplevel(self)
        win.title("Add Camera")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        def lbl(t):
            tk.Label(win, text=t, bg=BG, fg=TEXT_DIM,
                     font=("Consolas", 8, "bold")).pack(anchor="w", padx=16, pady=(10, 2))

        def inp():
            e = tk.Entry(win, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("Consolas", 10), width=44,
                         highlightbackground=INPUT_BD, highlightthickness=1)
            e.pack(padx=16, fill="x")
            return e

        lbl("CAMERA NAME")
        name_e = inp()
        lbl("STREAM URL  (.m3u8)")
        url_e = inp()

        def add():
            name = name_e.get().strip() or "Camera"
            url  = url_e.get().strip()
            if not url:
                messagebox.showwarning("Missing URL", "Please enter a stream URL.", parent=win)
                return
            self._cameras.append({"name": name, "url": url})
            self._cam_order = list(range(len(self._cameras)))
            self._rebuild_grid()
            self._refresh_cam_list()
            win.destroy()
            self._schedule_refresh(delay=0.2)

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=12, padx=16, fill="x")
        self._btn(btn_row, "Add Camera", add, accent=True).pack(side="right")
        self._btn(btn_row, "Cancel", win.destroy).pack(side="right", padx=6)

    def _remove_camera(self, idx: int):
        if 0 <= idx < len(self._cameras):
            self._cameras.pop(idx)
            self._cam_order = list(range(len(self._cameras)))
            self._rebuild_grid()
            self._refresh_cam_list()

    def _clear_cameras(self):
        self._stop_all_captures()
        self._cameras.clear()
        self._tiles.clear()
        self._cam_order = []
        self._rebuild_grid()
        self._refresh_cam_list()

    # ── Grid ──────────────────────────────────────────────────────────────────

    def _show_empty(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()

        wrap = tk.Frame(self._grid_frame, bg=BG)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(wrap, text=S_TITLE, bg=BG, fg=ACCENT,
                 font=("Consolas", 13, "bold")).pack(pady=(0, 6))
        tk.Label(wrap, text="Load a playlist or add a stream to get started.",
                 bg=BG, fg=TEXT_DIM, font=("Consolas", 9)).pack(pady=(0, 20))

        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack()
        self._big_btn(btn_row, "📂  Load Playlist", self._load_playlist).pack(side="left", padx=8)
        self._big_btn(btn_row, "＋  Add URL", self._show_add_url).pack(side="left", padx=8)

        tk.Label(wrap, text="or drag & drop an .m3u / .m3u8 file onto this window",
                 bg=BG, fg=TEXT_DIM, font=("Consolas", 8)).pack(pady=(16, 0))

    def _big_btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=ACCENT, fg=_contrast_color(ACCENT),
                     font=(FONT_FAMILY, 10, "bold"),
                     padx=18, pady=10, cursor="hand2", relief="flat")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=ACCENT))
        b.bind("<Leave>", lambda e: b.config(bg=ACCENT))
        return b

    def _rebuild_grid(self):
        try:
            self.unbind("<Configure>")
        except Exception:
            pass

        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._tiles.clear()

        if not self._cameras:
            self._show_empty()
            return

        # Apply custom order
        cameras = [self._cameras[i] for i in self._cam_order if i < len(self._cameras)]
        for i, cam in enumerate(self._cameras):
            if i not in self._cam_order:
                cameras.append(cam)

        n = len(cameras)

        cols = max(1, getattr(self, '_cols', DEFAULT_COLS))
        rows_of_cams = []
        i = 0
        while i < n:
            rows_of_cams.append(cameras[i:i+cols])
            i += cols

        num_rows = len(rows_of_cams)
        offline = make_offline_image()
        grid_idx = 0

        for row_idx, row_cams in enumerate(rows_of_cams):
            count = len(row_cams)  # 1, 2, or 3

            # Each row is its own Frame that fills horizontally
            row_frame = tk.Frame(self._grid_frame, bg=BG)
            row_frame.grid(row=row_idx, column=0, sticky="nsew", padx=0, pady=1)
            self._grid_frame.rowconfigure(row_idx, weight=1)

            for col_idx, cam in enumerate(row_cams):
                if count < cols:
                    row_frame.columnconfigure(0, weight=1)
                    for ci in range(count):
                        row_frame.columnconfigure(ci + 1, weight=3)
                    row_frame.columnconfigure(count + 1, weight=1)
                    grid_col = col_idx + 1
                else:
                    row_frame.columnconfigure(col_idx, weight=1)
                    grid_col = col_idx

                outer = tk.Frame(row_frame, bg=TILE_BORDER)
                outer.grid(row=0, column=grid_col, sticky="nsew", padx=1, pady=0)
                row_frame.rowconfigure(0, weight=1)

                canvas = tk.Canvas(outer, bg=TILE_BG, highlightthickness=0,
                                   cursor="hand2")
                canvas.pack(fill="both", expand=True)

                dot_id = canvas.create_text(10, 10, text=S_DOT, fill=OFFLINE_RED,
                                            font=(FONT_FAMILY, 8), anchor="nw")

                # Camera name — centered top, hidden until hover
                name_id = canvas.create_text(0, 8, text=cam["name"],
                                             fill="white", anchor="n",
                                             font=("Consolas", 8, "bold"),
                                             state="hidden")

                # Close button — top right, hidden until hover
                close_id = canvas.create_text(0, 8, text=S_CLOSE, fill=OFFLINE_RED,
                                              anchor="ne", font=(FONT_FAMILY, 10, "bold"),
                                              state="hidden")


                tile = {"cam": cam, "outer": outer, "canvas": canvas,
                        "dot_id": dot_id, "name_id": name_id, "close_id": close_id,
                        "online": False, "raw_img": offline,
                        "_photo": None, "grid_idx": grid_idx}
                self._tiles.append(tile)
                grid_idx += 1

                url = cam["url"]
                canvas.bind("<Button-1>",        lambda e, t=tile: self._on_tile_click(e, t))
                canvas.bind("<B1-Motion>",       lambda e, t=tile: self._on_tile_drag(e, t))
                canvas.bind("<ButtonRelease-1>", lambda e, t=tile: self._on_tile_drop(e, t))
                canvas.bind("<Enter>",  lambda e, t=tile, o=outer: self._on_tile_enter(t, o))
                canvas.bind("<Leave>",  lambda e, t=tile, o=outer: self._on_tile_leave(t, o))
                canvas.bind("<Motion>", lambda e, t=tile: self._on_tile_motion(e, t))
                canvas.bind("<Configure>", lambda e, t=tile: self._redraw_tile(t))

        # Single column for the grid_frame itself
        self._grid_frame.columnconfigure(0, weight=1)

        self.bind("<Configure>", self._on_resize)
        self.update_idletasks()
        self._redraw_tiles()

    # ── Drag-to-reorder ───────────────────────────────────────────────────────

    def _on_tile_click(self, event, tile):
        c = tile["canvas"]
        w = c.winfo_width()
        h = c.winfo_height()

        # Close button: top-right 24x24
        if event.x >= w - 24 and event.y <= 24:
            self._click_consumed = True
            self._remove_camera_by_tile(tile)
            return

        self._click_consumed = False
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_tile    = tile
        self._drag_moved   = False

    def _remove_camera_by_obj(self, cam: dict):
        """Remove a camera by its dict object (used from settings list)."""
        url = cam.get("url")
        if url and url in self._captures:
            self._captures[url].stop()
            del self._captures[url]
        if cam in self._cameras:
            self._cameras.remove(cam)
        self._cam_order = list(range(len(self._cameras)))
        self._rebuild_grid()
        self._refresh_cam_list()

    def _remove_camera_by_tile(self, tile):
        """Remove the camera associated with this tile."""
        cam = tile["cam"]
        url = cam.get("url")
        if url and url in self._captures:
            self._captures[url].stop()
            del self._captures[url]
        if cam in self._cameras:
            self._cameras.remove(cam)
        self._cam_order = list(range(len(self._cameras)))
        self._rebuild_grid()
        self._refresh_cam_list()

    def _on_tile_drag(self, event, tile):
        dx = abs(event.x_root - self._drag_start_x)
        dy = abs(event.y_root - self._drag_start_y)
        if dx > 8 or dy > 8:
            self._drag_moved = True
            tile["canvas"].config(cursor="fleur")
            # Highlight potential drop targets
            for t in self._tiles:
                if t is not tile:
                    # Check if mouse is over this tile
                    x1 = t["outer"].winfo_rootx()
                    y1 = t["outer"].winfo_rooty()
                    x2 = x1 + t["outer"].winfo_width()
                    y2 = y1 + t["outer"].winfo_height()
                    if x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2:
                        t["outer"].config(bg=ACCENT)
                    else:
                        t["outer"].config(bg=TILE_BORDER)

    def _on_tile_drop(self, event, tile):
        # Only process if the press actually started on THIS tile
        # (guards against ButtonRelease firing on newly-created tiles after a UI rebuild)
        if self._drag_tile is not tile:
            self._drag_tile = None
            return
        # If click was consumed by X button, do nothing
        if getattr(self, "_click_consumed", False):
            self._click_consumed = False
            return
        try:
            tile["canvas"].config(cursor="hand2")
        except Exception:
            return  # tile was destroyed (e.g. after remove)
        # Reset highlights
        for t in self._tiles:
            try:
                t["outer"].config(bg=TILE_BORDER)
            except Exception:
                pass

        if not self._drag_moved:
            # It was a click, not a drag — open player
            self._open_in_potplayer(tile["cam"]["url"])
            return

        self._drag_moved = False
        self._click_consumed = False

        # Find which tile we dropped onto
        target = None
        for t in self._tiles:
            if t is tile:
                continue
            x1 = t["outer"].winfo_rootx()
            y1 = t["outer"].winfo_rooty()
            x2 = x1 + t["outer"].winfo_width()
            y2 = y1 + t["outer"].winfo_height()
            if x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2:
                target = t
                break

        if target is None:
            return

        # Swap positions in _cam_order
        ai = tile["grid_idx"]
        bi = target["grid_idx"]
        order = list(self._cam_order)
        order[ai], order[bi] = order[bi], order[ai]
        self._cam_order = order
        self._rebuild_grid()
        self._schedule_refresh(delay=0)

    def _on_tile_enter(self, tile, outer):
        outer.config(bg=TILE_HOVER)
        c = tile["canvas"]
        c.itemconfig(tile["name_id"],     state="normal")
        c.itemconfig(tile["close_id"],    state="normal")

    def _on_tile_leave(self, tile, outer):
        outer.config(bg=TILE_BORDER)
        c = tile["canvas"]
        c.itemconfig(tile["name_id"],     state="hidden")
        c.itemconfig(tile["close_id"],    state="hidden")

    def _on_tile_motion(self, event, tile):
        """Handle hover regions — close, live, pause, mute buttons."""
        c = tile["canvas"]
        w = c.winfo_width()
        h = c.winfo_height()

        # Close button: top-right 24x24
        if event.x >= w - 24 and event.y <= 24:
            c.itemconfig(tile["close_id"], fill="#ff4455")
        else:
            c.itemconfig(tile["close_id"], fill=OFFLINE_RED)


    def _on_resize(self, event):
        if event.widget is not self:
            return
        if hasattr(self, "_resize_job") and self._resize_job:
            self.after_cancel(self._resize_job)
        # Redraw thumbnails fast; restart live mpv with a longer delay so the
        # canvas has fully settled before we embed the new process
        self._resize_job = self.after(60, self._redraw_tiles)

    def _redraw_tile(self, tile):
        """Draw tile's raw_img scaled to fill its canvas, preserving aspect ratio."""
        c = tile["canvas"]
        try:
            if not c.winfo_exists():
                return
        except Exception:
            return
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2 or h < 2:
            return
        raw = tile.get("raw_img")
        if raw is None:
            return

        # Scale to fit within cell, preserving aspect ratio (letterbox with black)
        src_w, src_h = raw.size
        scale = min(w / src_w, h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = raw.resize((new_w, new_h), Image.BILINEAR)

        # Center on black canvas
        canvas_img = Image.new("RGB", (w, h), (8, 8, 16))
        x = (w - new_w) // 2
        y = (h - new_h) // 2
        canvas_img.paste(img, (x, y))

        # Skin post-process (e.g. cyberpunk neon overlay)
        skin_fx = _SKIN.get("style", {}).get("tile_fx")
        if skin_fx == "cyberpunk":
            canvas_img = _apply_cyberpunk_fx(canvas_img)

        photo = ImageTk.PhotoImage(canvas_img)
        c.delete("img")
        c.create_image(0, 0, anchor="nw", image=photo, tags="img")
        # Keep overlays on top, update positions for current canvas size
        c.coords(tile["dot_id"],      10,       10)
        c.coords(tile["name_id"],     w // 2,   8)
        c.coords(tile["close_id"],    w - 8,    8)
        # Keep all overlays on top
        for key in ("dot_id","name_id","close_id"):
            c.tag_raise(tile[key])
        tile["_photo"] = photo

    def _redraw_tiles(self):
        for tile in self._tiles:
            self._redraw_tile(tile)

    def _set_tile_image(self, tile: dict, img: Image.Image, online: bool):
        # Tile may have been removed while refresh thread was running — skip it
        try:
            if not tile["canvas"].winfo_exists():
                return
        except Exception:
            return
        tile["raw_img"] = img
        tile["online"]  = online
        color = ONLINE_GREEN if online else OFFLINE_RED
        tile["canvas"].itemconfig(tile["dot_id"], fill=color)
        self._redraw_tile(tile)

    # ── Persistent capture management ────────────────────────────────────────

    def _ensure_captures(self):
        """Start/restart persistent captures for all cameras.
        Called when cameras are added/removed or settings change."""
        active_urls = set()
        for tile in self._tiles:
            if tile.get("live"):
                continue
            url = tile["cam"]["url"]
            active_urls.add(url)
            if url not in self._captures:
                cap = PersistentCapture(url, self._quality, self._interval)
                cap.start()
                self._captures[url] = cap
            else:
                # Ensure existing capture matches current settings
                cap = self._captures[url]
                if cap._quality != self._quality or cap._interval != self._interval:
                    cap.restart(quality=self._quality, interval=self._interval)
                elif not cap.alive:
                    cap.restart()

        # Stop captures for cameras that were removed
        stale = set(self._captures.keys()) - active_urls
        for url in stale:
            self._captures[url].stop()
            del self._captures[url]

    def _stop_all_captures(self):
        """Kill all persistent ffmpeg processes."""
        for cap in self._captures.values():
            cap.stop()
        self._captures.clear()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _schedule_refresh(self, delay: int = None):
        """Schedule next refresh after `delay` seconds (default: _interval)."""
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        secs = delay if delay is not None else self._interval
        self._refresh_job = self.after(int(secs * 1000), self._start_refresh)

    def _start_refresh(self):
        """Start a refresh if not already in progress."""
        if self._refreshing or not self._cameras:
            self._schedule_refresh()
            return
        self._refreshing = True
        # Ensure all persistent captures are running
        self._ensure_captures()
        threading.Thread(target=self._refresh_all_parallel, daemon=True).start()

    def _refresh_all_parallel(self):
        """Wait for all captures to deliver a fresh frame, then update all tiles
        at once so the grid stays in sync."""
        tiles = [t for t in self._tiles if not t.get("live")]

        if getattr(self, "_rebuilding", False):
            self._refreshing = False
            return

        # Step 1: Record current generation for each capture
        snap = {}  # url -> last_gen
        for tile in tiles:
            url = tile["cam"]["url"]
            cap = self._captures.get(url)
            if cap:
                _, _, gen = cap.get_frame()
                snap[url] = gen

        # Step 2: Wait for ALL captures to produce a frame newer than snap,
        # with a timeout so one dead camera doesn't stall the whole grid.
        # Use threads so we wait on all cameras concurrently.
        wait_timeout = min(self._interval + 3, 10)

        def _wait_one(url):
            cap = self._captures.get(url)
            if cap:
                cap.wait_for_new_frame(snap.get(url, 0), timeout=wait_timeout)

        wait_threads = []
        for url in snap:
            t = threading.Thread(target=_wait_one, args=(url,), daemon=True)
            t.start()
            wait_threads.append(t)

        # Wait for all wait threads to finish (each has its own timeout)
        for t in wait_threads:
            t.join(timeout=wait_timeout + 1)

        if getattr(self, "_rebuilding", False):
            self._refreshing = False
            return

        # Step 3: Collect frames and batch-update all tiles at once
        results = []  # list of (tile, img, online)
        for tile in tiles:
            url = tile["cam"]["url"]
            cap = self._captures.get(url)
            if cap:
                img, online, _ = cap.get_frame()
            else:
                img, online = None, False

            if img is None:
                online = False
                img = make_offline_image()

            results.append((tile, img, online))

        # Single batched UI update — all tiles refresh together
        def _batch_update():
            for tile, img, online in results:
                self._set_tile_image(tile, img, online)

        self.after(0, _batch_update)

        self._refreshing = False
        if not getattr(self, "_rebuilding", False):
            self.after(0, self._schedule_refresh)

    def _animate_countdown(self, total: int):
        pass  # countdown display removed — only gear icon shown

    # ── Settings actions ──────────────────────────────────────────────────────

    def _apply_interval(self):
        try:
            val = int(self._interval_var.get())
            if val < 1:
                raise ValueError
            self._interval = val
            # Restart all persistent captures with new fps=1/val
            for cap in self._captures.values():
                cap.restart(interval=val)
            self._schedule_refresh()
            self._status_lbl.config(text=f"interval → {val}s")
        except ValueError:
            messagebox.showwarning("Invalid", "Enter a whole number ≥ 1 second.")

    def _apply_quality(self, value: str):
        self._quality = value
        # Restart all persistent captures with new stream variant + resolution
        for cap in self._captures.values():
            cap.restart(quality=value)

    def _browse_player(self):
        path = filedialog.askopenfilename(
            title="Select Video Player",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self._player_path = path
            if hasattr(self, "_player_lbl"):
                self._player_lbl.config(text=os.path.basename(path))

    def _reset_player(self):
        self._player_path = ""
        if hasattr(self, "_player_lbl"):
            self._player_lbl.config(text="System default")

    def _apply_hotkey(self):
        key = self._hotkey_var.get().strip().lower()
        if not key:
            return
        self._hotkey = key
        self._bind_hotkey()
        self._status_lbl.config(text=f"hotkey → '{key}'")

    def _bind_hotkey(self):
        self.bind(f"<Key-{self._hotkey}>", lambda e: self._manual_refresh())

    def _manual_refresh(self):
        """Immediately fire a refresh, interrupting any scheduled one."""
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        self._refreshing = False
        self._start_refresh()

    # ── Clean shutdown ──────────────────────────────────────────────────────

    def _on_close(self):
        """Kill all persistent ffmpeg processes and close the window."""
        self._stop_all_captures()
        self.destroy()

    # ── File drop (via tkinterdnd2) ──────────────────────────────────────────────

    def _setup_dnd(self):
        """Register tkinterdnd2 drop target. Safe no-op if not installed."""
        try:
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", self._on_tkdnd_drop)
        except Exception:
            pass  # tkinterdnd2 not installed — Load button still works

    def _on_tkdnd_drop(self, event):
        """Called by tkinterdnd2 when files are dropped."""
        raw = event.data.strip()
        # tkinterdnd2 wraps paths with spaces in braces: {C:/my folder/file.m3u}
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.find("}", i)
                if end != -1:
                    paths.append(raw[i+1:end])
                    i = end + 2
                else:
                    break
            else:
                # no braces — space-separated
                parts = raw.split()
                paths.extend(parts)
                break
        self._handle_dropped_files(paths)

    def _handle_dropped_files(self, paths):
        """Load any .m3u / .m3u8 files from a drop."""
        loaded = 0
        for path in paths:
            if path.lower().endswith((".m3u", ".m3u8")):
                cams = parse_m3u(path)
                if cams:
                    self._cameras.extend(cams)
                    loaded += len(cams)
        if loaded:
            self._cam_order = list(range(len(self._cameras)))
            self._rebuild_grid()
            self._refresh_cam_list()
            # Wait for tkinter to finish rendering canvases before refreshing
            self._schedule_refresh(delay=0.2)  # instant after grid renders

    # ── PotPlayer ─────────────────────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self._apply_fullscreen()

    def _exit_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self._apply_fullscreen()

    def _apply_fullscreen(self):
        if self._fullscreen:
            self.attributes("-fullscreen", True)
            self._fs_btn.config(text=S_CLOSE, fg=ACCENT)
        else:
            self.attributes("-fullscreen", False)
            self._fs_btn.config(text=S_FS, fg=TEXT_DIM)

    def _open_in_potplayer(self, url: str):
        """Open stream URL in the configured player, or system default."""
        import subprocess, sys
        try:
            if self._player_path and os.path.isfile(self._player_path):
                subprocess.Popen([self._player_path, url])
            elif sys.platform == "win32":
                os.startfile(url)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception as e:
            self._status_lbl.config(text=f"⚠ Could not open: {e}")


if __name__ == "__main__":
    app = Synopticon()
    app.mainloop()
