from __future__ import annotations

import queue
import json
import sqlite3
import shutil
import sys
import threading
import copy
import math
from contextlib import closing
from datetime import datetime
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import ttkbootstrap
from ttkbootstrap.widgets import Floodgauge
from PIL import Image, ImageDraw, ImageFilter, ImageTk

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


LIKED_VIDEOS_URL = "https://www.youtube.com/playlist?list=LL"

BG = "#090B0E"
PANEL = "#11161C"
FIELD = "#090D11"
FG = "#F2F5F8"
MUTED = "#9AA6B2"
ACCENT = "#8B78FF"
CYAN = "#45D6C8"
BORDER = "#26313A"


class DownloadHistory:
    COLUMNS = (
        "id", "started_at", "completed_at", "status", "source_url", "video_id", "title",
        "media_type", "container", "quality", "ext", "format_id", "format_note",
        "resolution", "width", "height", "fps", "vcodec", "acodec", "abr", "tbr",
        "filesize", "duration", "uploader", "uploader_id", "channel", "channel_id",
        "upload_date", "playlist_title", "playlist_index", "live_status", "output_path",
        "metadata_json",
    )

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT, completed_at TEXT NOT NULL, status TEXT NOT NULL,
                    source_url TEXT, video_id TEXT, title TEXT, media_type TEXT,
                    container TEXT, quality TEXT, ext TEXT, format_id TEXT, format_note TEXT,
                    resolution TEXT, width INTEGER, height INTEGER, fps REAL,
                    vcodec TEXT, acodec TEXT, abr REAL, tbr REAL, filesize INTEGER,
                    duration REAL, uploader TEXT, uploader_id TEXT, channel TEXT,
                    channel_id TEXT, upload_date TEXT, playlist_title TEXT,
                    playlist_index TEXT, live_status TEXT, output_path TEXT, metadata_json TEXT
                )
            """)

    @classmethod
    def _safe_metadata(cls, value):
        sensitive = ("cookie", "authorization", "password", "token", "secret", "http_headers")
        if isinstance(value, dict):
            return {
                str(key): cls._safe_metadata(item)
                for key, item in value.items()
                if str(key).lower() not in {"url", "manifest_url", "fragment_base_url"}
                and not any(word in str(key).lower() for word in sensitive)
            }
        if isinstance(value, (list, tuple)):
            return [cls._safe_metadata(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def add(self, info: dict, settings: dict, *, status="downloaded", output_path=None,
            source_url=None, started_at=None, completed_at=None) -> int:
        info = info or {}
        width, height = info.get("width"), info.get("height")
        resolution = info.get("resolution") or (f"{width}x{height}" if width and height else None)
        actual_size = None
        if output_path and Path(output_path).is_file():
            actual_size = Path(output_path).stat().st_size
        values = {
            "started_at": started_at or datetime.now().astimezone().isoformat(timespec="seconds"),
            "completed_at": completed_at or datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": status,
            "source_url": source_url or info.get("webpage_url") or info.get("original_url"),
            "video_id": info.get("id"),
            "title": info.get("title"),
            "media_type": settings.get("kind"),
            "container": settings.get("container"),
            "quality": settings.get("quality"),
            "ext": Path(output_path).suffix.lstrip(".") if output_path else info.get("ext"),
            "format_id": info.get("format_id"),
            "format_note": info.get("format_note"),
            "resolution": resolution,
            "width": width,
            "height": height,
            "fps": info.get("fps"),
            "vcodec": info.get("vcodec"),
            "acodec": info.get("acodec"),
            "abr": info.get("abr"),
            "tbr": info.get("tbr"),
            "filesize": actual_size or info.get("filesize") or info.get("filesize_approx"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "uploader_id": info.get("uploader_id"),
            "channel": info.get("channel"),
            "channel_id": info.get("channel_id"),
            "upload_date": info.get("upload_date"),
            "playlist_title": info.get("playlist_title"),
            "playlist_index": info.get("playlist_index"),
            "live_status": info.get("live_status"),
            "output_path": str(output_path) if output_path else info.get("filepath"),
            "metadata_json": json.dumps(self._safe_metadata(info), ensure_ascii=False, separators=(",", ":"), default=str),
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with closing(sqlite3.connect(self.database_path)) as db, db:
            cursor = db.execute(
                f"INSERT INTO downloads ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            return cursor.lastrowid

    def list_recent(self, limit=1000) -> list[dict]:
        with closing(sqlite3.connect(self.database_path)) as db, db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def count(self) -> int:
        with closing(sqlite3.connect(self.database_path)) as db, db:
            return int(db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0])

    def get(self, history_id: int) -> dict | None:
        with closing(sqlite3.connect(self.database_path)) as db, db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM downloads WHERE id = ?", (history_id,)).fetchone()
            return dict(row) if row else None


class AnimatedButton(tk.Button):
    COLORS = {
        "primary": ("#705CF2", "#8979FF", "#5947CF"),
        "secondary": ("#202831", "#35424E", "#151B21"),
        "danger": ("#42232A", "#63313B", "#30191F"),
    }

    def __init__(self, master, *, text, command, variant="secondary", **kwargs):
        self.variant = variant
        self.base, self.hover, self.pressed = self.COLORS[variant]
        self.animation_id = None
        self.current_color = self.base
        super().__init__(
            master, text=text, command=command, bg=self.base, fg=FG,
            activebackground=self.pressed, activeforeground=FG,
            disabledforeground="#68727C", relief="flat", borderwidth=0,
            highlightthickness=0, padx=14, pady=8,
            font=("Segoe UI", 10, "bold"), cursor="hand2", **kwargs,
        )
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    @staticmethod
    def _rgb(color):
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))

    @staticmethod
    def _hex(rgb):
        return "#" + "".join(f"{max(0, min(255, n)):02x}" for n in rgb)

    def _on_enter(self, _event=None):
        self._animate(self.hover)

    def _on_leave(self, _event=None):
        self._animate(self.base)

    def _animate(self, target):
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        if str(self["state"]) == "disabled":
            return
        mode = getattr(self.winfo_toplevel(), "motion_mode", None)
        mode = mode.get() if mode else "Smooth"
        steps, delay = {"Quiet": (1, 1), "Smooth": (9, 16), "Peak": (16, 12)}[mode]
        start_rgb, end_rgb = self._rgb(self.current_color), self._rgb(target)

        def step(number=1):
            raw = min(1.0, number / steps)
            fraction = 1 - (1 - raw) ** 3
            rgb = tuple(round(a + (b - a) * fraction) for a, b in zip(start_rgb, end_rgb))
            self.current_color = self._hex(rgb)
            self.configure(bg=self.current_color)
            if number < steps:
                self.animation_id = self.after(delay, lambda: step(number + 1))
            else:
                self.animation_id = None

        step()


class YtDlpDesktop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Downloader")
        self.configure(bg=BG)
        self.geometry("1280x980")
        self.minsize(1000, 740)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self.app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        self.history = DownloadHistory(self.app_dir / "download_history.sqlite3")
        self.history_window = None
        self.events: queue.Queue[tuple] = queue.Queue()
        self.cancel_event = threading.Event()
        self.skip_current_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.liked_entries: list[dict] = []
        self.busy = False
        self.download_active = False
        self.visualizer_after_id = None
        self.progress_animation_id = None
        self.liked_search_after_id = None
        self.liked_search_generation = 0
        self.queue_selection_after_id = None
        self.queue_selection_generation = 0
        self.activity_phase = 0.0
        self._build_ui()
        self.after(400, self._drain_events)

    def _build_ui(self) -> None:
        style = ttkbootstrap.Style(theme="darkly")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Thumbnail.TCheckbutton", background=PANEL, foreground=FG, font=("Segoe UI", 9))
        style.map("Thumbnail.TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", MUTED)])
        style.configure("Card.TLabelframe", background=PANEL, bordercolor=BORDER, relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=PANEL, foreground=CYAN, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=(9, 7))
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG,
                        arrowcolor=CYAN, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=(8, 6))
        style.map("TCombobox", fieldbackground=[("readonly", FIELD), ("focus", FIELD)],
                  foreground=[("readonly", FG)], selectbackground=[("readonly", FIELD)])
        style.configure("Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT,
                        bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT, thickness=9)
        style.configure("Metric.TFrame", background=PANEL, relief="flat")
        style.configure("MetricName.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8, "bold"))
        style.configure("MetricValue.TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 17, "bold"))
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=FIELD,
                        bordercolor=PANEL, arrowcolor=CYAN, lightcolor=PANEL, darkcolor=PANEL)
        style.configure("History.Treeview", background=FIELD, fieldbackground=FIELD,
                        foreground=FG, rowheight=27, bordercolor=BORDER)
        style.configure("History.Treeview.Heading", background=PANEL, foreground=CYAN,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("History.Treeview", background=[("selected", "#39315F")], foreground=[("selected", FG)])
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", FG)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root = ttk.Frame(self, padding=(18, 14, 18, 14))
        root.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(7, weight=3)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="YouTube Downloader", font=("Segoe UI", 21, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="BATCH DOWNLOAD  ·  VIDEO & AUDIO  ·  LIKED VIDEOS", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.motion_mode = tk.StringVar(value="Smooth")
        self.history_button = AnimatedButton(header, text="History · 0", command=self.open_history, variant="secondary")
        self.history_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 8))
        motion = ttk.Frame(header)
        motion.grid(row=0, column=2, rowspan=2, sticky="e")
        ttk.Label(motion, text="MOTION", foreground=CYAN, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Combobox(motion, textvariable=self.motion_mode, state="readonly", values=["Quiet", "Smooth", "Peak"], width=12).pack(anchor="e", pady=(3, 0))

        metrics = ttk.Frame(root)
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 11))
        for col in range(3):
            metrics.columnconfigure(col, weight=1, uniform="metric")
        queue_card = ttk.Frame(metrics, style="Metric.TFrame", padding=(12, 8))
        queue_card.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        downloaded_card = ttk.Frame(metrics, style="Metric.TFrame", padding=(12, 8))
        downloaded_card.grid(row=0, column=1, sticky="ew", padx=3)
        current_card = ttk.Frame(metrics, style="Metric.TFrame", padding=(12, 8))
        current_card.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Label(queue_card, text="BATCH QUEUE", style="MetricName.TLabel").pack(anchor="w")
        self.queue_metric = ttk.Label(queue_card, text="0", style="MetricValue.TLabel")
        self.queue_metric.pack(anchor="w", pady=(1, 0))
        ttk.Label(downloaded_card, text="DOWNLOADED", style="MetricName.TLabel").pack(anchor="w")
        self.downloaded_metric = ttk.Label(downloaded_card, text="0", style="MetricValue.TLabel", foreground=CYAN)
        self.downloaded_metric.pack(anchor="w", pady=(1, 0))
        ttk.Label(current_card, text="CURRENT ITEM", style="MetricName.TLabel").pack(anchor="w")
        self.current_metric = ttk.Label(current_card, text="Idle", style="MetricValue.TLabel")
        self.current_metric.pack(anchor="w", pady=(1, 0))

        links = ttk.LabelFrame(root, text="  01  ·  Download queue  ", style="Card.TLabelframe", padding=12)
        links.grid(row=2, column=0, sticky="ew")
        links.columnconfigure(0, weight=1)
        ttk.Label(links, text="Paste URLs, one per line. You can mix individual videos and playlist links.", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.urls = tk.Text(links, height=4, wrap="word", undo=True, bg=FIELD, fg=FG,
                           insertbackground=CYAN, selectbackground=ACCENT, selectforeground=FG,
                           relief="flat", highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT, padx=10, pady=8, font=("Consolas", 10),
                           spacing1=2, spacing3=2)
        self.urls.grid(row=1, column=0, sticky="ew")

        settings = ttk.LabelFrame(root, text="  02  ·  Download settings  ", style="Card.TLabelframe", padding=12)
        settings.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for col in range(6):
            settings.columnconfigure(col, weight=1 if col in (1, 3, 5) else 0)

        self.kind = tk.StringVar(value="Video")
        self.container = tk.StringVar(value="mp4")
        self.quality = tk.StringVar(value="Best available")
        self.live_mode = tk.StringVar(value="From current position")
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        cookie_candidates = [self.app_dir / "cookies.txt"]
        if getattr(sys, "frozen", False):
            cookie_candidates.extend((self.app_dir.parent / "cookies.txt",
                                      self.app_dir.parent.parent / "cookies.txt"))
        cookie_path = next((path for path in cookie_candidates if path.is_file()), None)
        self.cookies = tk.StringVar(value=str(cookie_path) if cookie_path else "")
        self.ffmpeg = tk.StringVar()
        self.items = tk.StringVar()

        self._combo(settings, 0, 0, "Type", self.kind, ["Video", "Audio"])
        self._combo(settings, 0, 2, "Container", self.container, ["mp4", "mkv", "webm"])
        self._combo(settings, 0, 4, "Quality", self.quality, ["Best available", "360p", "480p", "720p", "1080p", "1440p", "2160p", "64 kbps", "96 kbps", "128 kbps", "160 kbps", "192 kbps", "256 kbps", "320 kbps"])

        self._path_row(settings, 1, "Save to", self.output_dir, self._choose_output)
        self._path_row(settings, 2, "cookies.txt", self.cookies, self._choose_cookies)
        self._path_row(settings, 3, "FFmpeg (optional)", self.ffmpeg, self._choose_ffmpeg)

        ttk.Label(settings, text="Playlist items").grid(row=4, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(settings, textvariable=self.items).grid(row=4, column=1, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Label(settings, text="e.g. 1,3,5-8  ·  blank = all", style="Muted.TLabel").grid(row=4, column=3, columnspan=3, sticky="w", padx=(8, 0), pady=(7, 0))

        ttk.Label(settings, text="Live stream").grid(row=5, column=0, sticky="w", pady=(7, 0))
        ttk.Combobox(settings, textvariable=self.live_mode, state="readonly", values=["From current position", "From beginning (DVR; experimental)" ]).grid(row=5, column=1, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Label(settings, text="Start from beginning needs an available DVR window.", style="Muted.TLabel").grid(row=5, column=3, columnspan=3, sticky="w", padx=(8, 0), pady=(7, 0))
        self.include_thumbnail = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings, text="Include thumbnail", variable=self.include_thumbnail,
                        style="Thumbnail.TCheckbutton").grid(row=6, column=0, columnspan=2,
                                                              sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Save the image; embed cover art when the chosen format supports it.",
                  style="Muted.TLabel").grid(row=6, column=2, columnspan=4, sticky="w",
                                              padx=(8, 0), pady=(8, 0))

        liked = ttk.LabelFrame(root, text="  03  ·  Liked videos  ", style="Card.TLabelframe", padding=12)
        liked.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        liked.columnconfigure(1, weight=1)
        AnimatedButton(liked, text="Load my Liked videos", command=self.load_liked, variant="secondary").grid(row=0, column=0, sticky="w")
        self.liked_status = ttk.Label(liked, text="Uses cookies.txt to read your private Liked videos playlist.", style="Muted.TLabel")
        self.liked_status.grid(row=0, column=1, sticky="w", padx=12)
        ttk.Label(liked, text="Find by title").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.liked_search = tk.StringVar()
        self.liked_search.trace_add("write", self._render_liked_preview)
        self.liked_search_entry = ttk.Entry(liked, textvariable=self.liked_search)
        self.liked_search_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        AnimatedButton(liked, text="Clear", command=lambda: self.liked_search.set(""), variant="secondary").grid(row=1, column=2, sticky="e", padx=(8, 0), pady=(8, 0))
        ttk.Label(liked, text="Liked item numbers").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.liked_numbers = tk.StringVar()
        ttk.Entry(liked, textvariable=self.liked_numbers).grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(liked, text="e.g. 2,7,10-12", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        AnimatedButton(liked, text="Add selection to queue", command=self.add_liked_selection, variant="secondary").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.liked_preview = tk.Text(liked, height=4, wrap="word", state="disabled", bg=FIELD,
                                     fg=FG, relief="flat", highlightthickness=1,
                                     highlightbackground=BORDER, padx=9, pady=7, font=("Segoe UI", 9))
        self.liked_preview.tag_configure("search_match", foreground="#FFFFFF", background="#5747A5")
        liked_scroll = ttk.Scrollbar(liked, orient="vertical", command=self.liked_preview.yview)
        self.liked_preview.configure(yscrollcommand=liked_scroll.set)
        self.liked_preview.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        liked_scroll.grid(row=4, column=2, sticky="ns", pady=(8, 0))

        actions = ttk.Frame(root)
        actions.grid(row=5, column=0, sticky="ew", pady=(12, 5))
        self.start_button = AnimatedButton(actions, text="Start batch", command=self.start_download, variant="primary")
        self.start_button.pack(side="left")
        self.skip_button = AnimatedButton(actions, text="Skip current", command=self.skip_current, variant="secondary", state="disabled")
        self.skip_button.pack(side="left", padx=(8, 0))
        self.stop_button = AnimatedButton(actions, text="Stop after current fragment", command=self.stop_download, variant="danger", state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.batch_progress_label = ttk.Label(actions, text="Done 0 / 0", style="Muted.TLabel")
        self.batch_progress_label.pack(side="right", padx=(10, 0))
        self.activity_dot = tk.Canvas(actions, width=144, height=38, bg=BG, highlightthickness=0)
        self.activity_dot.pack(side="right", padx=(6, 6))
        self._build_visualizer()
        self.status = ttk.Label(actions, text="Ready", style="Muted.TLabel")
        self.status.pack(side="right")

        self.progress = Floodgauge(root, value=0, maximum=100, mode="determinate",
                                   mask="{}%", bootstyle="info", thickness=20,
                                   length=850, font=("Segoe UI", 9, "bold"))
        self.progress.grid(row=6, column=0, sticky="ew", pady=(0, 9))
        activity = ttk.LabelFrame(root, text="  Activity  ", style="Card.TLabelframe", padding=9)
        activity.grid(row=7, column=0, sticky="nsew")
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(0, weight=1)
        self.log = tk.Text(activity, height=14, wrap="word", state="disabled", bg=FIELD, fg=MUTED,
                           relief="flat", highlightthickness=1,
                           highlightbackground=BORDER, padx=9, pady=7, font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(activity, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

        self.kind.trace_add("write", self._update_control_values)
        self._update_control_values()
        self._update_history_count()

    def _combo(self, parent, row, label_col, label, variable, values) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=label_col, sticky="w", padx=(0, 6), pady=(0, 8))
        cb = ttk.Combobox(parent, textvariable=variable, state="readonly", values=values)
        cb.grid(row=row, column=label_col + 1, sticky="ew", padx=(0, 14), pady=(0, 8))
        if label == "Container":
            self.container_combo = cb
        elif label == "Quality":
            self.quality_combo = cb

    def _path_row(self, parent, row, label, variable, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=4, sticky="ew", pady=3)
        AnimatedButton(parent, text="Browse…", command=command, variant="secondary").grid(row=row, column=5, sticky="e", padx=(6, 0), pady=3)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.home()))
        if path:
            self.output_dir.set(path)

    def _choose_cookies(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Cookie files", "cookies*.txt *.txt"), ("All files", "*.*")])
        if path:
            self.cookies.set(path)

    def _choose_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("FFmpeg executable", "ffmpeg.exe"), ("All files", "*.*")])
        if path:
            self.ffmpeg.set(path)

    def _update_control_values(self, *_args) -> None:
        old = self.quality.get()
        if self.kind.get() == "Video":
            values, containers = ["Best available", "360p", "480p", "720p", "1080p", "1440p", "2160p"], ["mp4", "mkv", "webm"]
        else:
            values, containers = ["Best available", "64 kbps", "96 kbps", "128 kbps", "160 kbps", "192 kbps", "256 kbps", "320 kbps"], ["mp3", "flac", "m4a", "opus", "wav"]
        self.container_combo.configure(values=containers)
        if self.container.get() not in containers:
            self.container.set(containers[0])
        self.quality_combo.configure(values=values)
        self.quality.set(old if old in values else "Best available")

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _build_visualizer(self) -> None:
        width, height = 144, 38
        bloom = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bloom)
        draw.ellipse((18, 3, 83, 36), fill=(139, 120, 255, 78))
        draw.ellipse((66, 3, 131, 36), fill=(69, 214, 200, 76))
        self.activity_glow = ImageTk.PhotoImage(bloom.filter(ImageFilter.GaussianBlur(12)), master=self)
        self.activity_dot.create_image(width // 2, height // 2, image=self.activity_glow, tags="glow")
        self.activity_bars = []
        count = 19
        bar_width, stride = 3.2, 6.5
        first_x = (width - (count - 1) * stride - bar_width) / 2
        for index in range(count):
            x = first_x + index * stride
            item = self.activity_dot.create_rectangle(x, 18, x + bar_width, 21,
                                                       fill=MUTED, outline="", tags="bar")
            self.activity_bars.append((item, index, x, x + bar_width))
        self._draw_visualizer(active=False)

    @staticmethod
    def _blend_color(first: str, second: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        values = [round(int(first[i:i + 2], 16) * (1 - amount) + int(second[i:i + 2], 16) * amount)
                  for i in (1, 3, 5)]
        return "#" + "".join(f"{value:02x}" for value in values)

    def _draw_visualizer(self, *, active: bool) -> None:
        canvas_height = 38
        phase = self.activity_phase
        for item, index, left, right in self.activity_bars:
            wave = (math.sin(phase + index * 0.61) + math.sin(phase * 1.43 - index * 0.29)) / 2
            if active:
                bar_height = 6 + abs(wave) * 24
                intensity = 0.58 + abs(wave) * 0.42
            else:
                bar_height = 3 + abs(math.sin(index * 0.57)) * 5
                intensity = 0.34
            bottom = canvas_height - 4
            self.activity_dot.coords(item, left, bottom - bar_height, right, bottom)
            base = ACCENT if index < len(self.activity_bars) // 2 else CYAN
            self.activity_dot.itemconfigure(item, fill=self._blend_color(BG, base, intensity))

    def _animate_progress(self, target: float) -> None:
        if self.progress_animation_id:
            self.after_cancel(self.progress_animation_id)
            self.progress_animation_id = None
        start = float(self.progress.value)
        target = max(0.0, min(100.0, float(target)))
        mode = self.motion_mode.get()
        steps, delay = {"Quiet": (3, 55), "Smooth": (7, 24), "Peak": (10, 16)}[mode]

        def frame(number=1):
            raw = min(1.0, number / steps)
            eased = 1 - (1 - raw) ** 3
            self.progress.configure(value=start + (target - start) * eased)
            if number < steps:
                self.progress_animation_id = self.after(delay, lambda: frame(number + 1))
            else:
                self.progress_animation_id = None

        frame()

    def _begin_action_progress(self, label: str, *, indeterminate: bool = False) -> bool:
        if self.download_active:
            return False
        if self.progress_animation_id:
            self.after_cancel(self.progress_animation_id)
            self.progress_animation_id = None
        self.progress.stop()
        self.status.configure(text=label)
        if indeterminate:
            self.progress.configure(mode="indeterminate", mask=None, text=label)
            self.progress.start(interval={"Quiet": 120, "Smooth": 60, "Peak": 36}[self.motion_mode.get()])
        else:
            self.progress.configure(mode="determinate", mask="{}%", text="", value=0)
        return True

    def _finish_action_progress(self, label: str) -> None:
        if self.download_active:
            return
        self.progress.stop()
        self.progress.configure(mode="determinate", mask="{}%", text="")
        self._animate_progress(100)
        self.status.configure(text=label)

    def _update_history_count(self) -> None:
        self.history_button.configure(text=f"History · {self.history.count()}")

    def open_history(self) -> None:
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift()
            self._refresh_history()
            return
        win = tk.Toplevel(self)
        self.history_window = win
        win.title("Download history")
        win.configure(bg=BG)
        win.geometry("1120x720")
        win.minsize(820, 540)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        header = ttk.Frame(win, padding=(16, 13, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Download history", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Select any row to inspect the saved metadata and file details.", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        AnimatedButton(header, text="Refresh", command=self._refresh_history, variant="secondary").grid(row=0, column=1, rowspan=2, sticky="e")
        body = ttk.Panedwindow(win, orient="vertical")
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        listing = ttk.Frame(body)
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        columns = ("completed_at", "title", "media_type", "format", "resolution", "filesize", "status")
        tree = ttk.Treeview(listing, columns=columns, show="headings", style="History.Treeview", selectmode="browse")
        self.history_tree = tree
        labels = {"completed_at":"Downloaded", "title":"Title", "media_type":"Type", "format":"Format / quality", "resolution":"Resolution", "filesize":"Size", "status":"Status"}
        widths = {"completed_at":150, "title":370, "media_type":75, "format":155, "resolution":105, "filesize":95, "status":90}
        for col in columns:
            tree.heading(col, text=labels[col], anchor="w")
            tree.column(col, width=widths[col], minwidth=65, anchor="w", stretch=col == "title")
        yscroll = ttk.Scrollbar(listing, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(listing, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree.bind("<<TreeviewSelect>>", self._show_history_details)
        detail_frame = ttk.Frame(body)
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        self.history_details = tk.Text(detail_frame, wrap="word", state="disabled", bg=FIELD, fg=FG,
                                       insertbackground=CYAN, selectbackground=ACCENT, relief="flat",
                                       highlightthickness=1, highlightbackground=BORDER, padx=12, pady=10,
                                       font=("Consolas", 9))
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.history_details.yview)
        self.history_details.configure(yscrollcommand=detail_scroll.set)
        self.history_details.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        body.add(listing, weight=3)
        body.add(detail_frame, weight=2)
        win.bind("<Destroy>", lambda event: setattr(self, "history_window", None) if event.widget is win else None)
        self._refresh_history()

    @staticmethod
    def _pretty_size(size):
        if not size:
            return "—"
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return str(size)

    def _refresh_history(self) -> None:
        if not getattr(self, "history_tree", None) or not self.history_tree.winfo_exists():
            self._update_history_count()
            return
        self._begin_action_progress("Refreshing download history…")
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.history_rows = self.history.list_recent()
        for row in self.history_rows:
            fmt = " ".join(str(part) for part in (row.get("container"), row.get("quality")) if part)
            self.history_tree.insert("", "end", iid=str(row["id"]), values=(
                row.get("completed_at") or "", row.get("title") or "(untitled)",
                row.get("media_type") or "", fmt or row.get("ext") or "",
                row.get("resolution") or ("Audio" if row.get("media_type") == "Audio" else "—"),
                self._pretty_size(row.get("filesize")), row.get("status") or "",
            ))
        self._update_history_count()
        if self.history_rows:
            self.history_tree.selection_set(str(self.history_rows[0]["id"]))
            self._show_history_details()
        self._finish_action_progress(f"History refreshed · {len(self.history_rows)} record(s)")

    def _show_history_details(self, _event=None) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        row = self.history.get(int(selected[0]))
        if not row:
            return
        lines = [f"{key.replace('_', ' ').title()}: {self._pretty_size(value) if key == 'filesize' else value if value not in (None, '') else '—'}"
                 for key, value in row.items() if key != "metadata_json"]
        lines.extend(("", "Full yt-dlp metadata:", json.dumps(json.loads(row.get("metadata_json") or "{}"), indent=2, ensure_ascii=False)))
        self.history_details.configure(state="normal")
        self.history_details.delete("1.0", "end")
        self.history_details.insert("1.0", "\n".join(lines))
        self.history_details.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if self.visualizer_after_id:
            self.after_cancel(self.visualizer_after_id)
            self.visualizer_after_id = None
        if busy:
            self._animate_visualizer()
        else:
            self._draw_visualizer(active=False)

    def _animate_visualizer(self) -> None:
        if not self.busy:
            return
        mode = self.motion_mode.get()
        delay, advance = {"Quiet": (120, 0.38), "Smooth": (48, 0.52), "Peak": (28, 0.68)}[mode]
        self.activity_phase += advance
        self._draw_visualizer(active=True)
        self.visualizer_after_id = self.after(delay, self._animate_visualizer)

    def _validate(self) -> str | None:
        if yt_dlp is None:
            return "yt-dlp is not installed. Install the requirements before running this app."
        if not Path(self.output_dir.get()).is_dir():
            return "Choose an existing download folder."
        cookie_path = self.cookies.get().strip()
        if cookie_path and not Path(cookie_path).is_file():
            return "The selected cookies.txt file does not exist."
        return None

    def _yt_options(self, *, extract_flat=False, progress_hook=None, playlist_items=None) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": False,
            "noplaylist": False,
            "outtmpl": str(Path(self.output_dir.get()) / "%(title)s [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "ignoreerrors": False,
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        cookie_path = self.cookies.get().strip()
        if cookie_path:
            opts["cookiefile"] = cookie_path
        ffmpeg_path = self.ffmpeg.get().strip()
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path
        self._add_javascript_runtime(opts)
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        if extract_flat:
            opts["skip_download"] = True
        if playlist_items:
            opts["playlist_items"] = playlist_items
        return opts

    @staticmethod
    def _add_javascript_runtime(options: dict) -> None:
        node_path = shutil.which("node")
        if node_path:
            options["js_runtimes"] = {"node": {"path": node_path}}

    def _formats(self, settings: dict) -> tuple[str, list[dict] | None]:
        container = settings["container"]
        quality = settings["quality"]
        if settings["kind"] == "Video":
            height = quality.removesuffix("p") if quality != "Best available" else None
            if height:
                fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
            else:
                fmt = "bestvideo*+bestaudio/best"
            return fmt, None

        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": container, "preferredquality": "0"}]
        if quality != "Best available":
            postprocessors[0]["preferredquality"] = quality.split()[0]
        return "bestaudio/best", postprocessors

    def _download_opts(self, progress_hook, settings: dict) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": False,
            "noplaylist": False,
            "outtmpl": str(Path(settings["output_dir"]) / "%(title)s [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "ignoreerrors": False,
            "progress_hooks": [progress_hook],
        }
        if settings["cookies"]:
            opts["cookiefile"] = settings["cookies"]
        if settings["ffmpeg"]:
            opts["ffmpeg_location"] = settings["ffmpeg"]
        self._add_javascript_runtime(opts)
        if settings["playlist_items"]:
            opts["playlist_items"] = settings["playlist_items"]
        fmt, postprocessors = self._formats(settings)
        opts["format"] = fmt
        container = settings["container"]
        if settings["kind"] == "Video":
            opts["merge_output_format"] = container
            if container in {"mkv", "webm"}:
                opts["remuxvideo"] = container
        else:
            opts["postprocessors"] = postprocessors
            opts["keepvideo"] = False
        if settings["live_from_start"]:
            opts["live_from_start"] = True
        if settings.get("include_thumbnail"):
            opts["writethumbnail"] = True
            supports_embedded_cover = (
                settings["kind"] == "Video" and settings["container"] in {"mp4", "mkv"}
            ) or (
                settings["kind"] == "Audio" and settings["container"] in {"mp3", "flac", "m4a", "opus"}
            )
            if supports_embedded_cover:
                opts["embedthumbnail"] = True
        return opts

    @staticmethod
    def _parse_indices(text: str) -> list[int]:
        indexes: set[int] = set()
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start < 1 or end < start:
                    raise ValueError
                indexes.update(range(start, end + 1))
            else:
                value = int(part)
                if value < 1:
                    raise ValueError
                indexes.add(value)
        return sorted(indexes)

    def _render_liked_preview(self, *_args) -> None:
        if not hasattr(self, "liked_preview"):
            return
        if self.liked_search_after_id:
            self.after_cancel(self.liked_search_after_id)
            self.liked_search_after_id = None
        self.liked_search_generation += 1
        generation = self.liked_search_generation
        query = self.liked_search.get().strip().casefold()
        entries = self.liked_entries
        self.liked_preview.configure(state="normal")
        self.liked_preview.delete("1.0", "end")
        self.liked_preview.tag_remove("search_match", "1.0", "end")
        if not entries:
            self.liked_preview.insert("end", "Load your Liked videos to search titles.")
            self.liked_preview.configure(state="disabled")
            return

        self._begin_action_progress("Searching Liked titles…")
        matches = 0
        cursor = 0
        total = len(entries)
        chunk_size = {"Quiet": 80, "Smooth": 45, "Peak": 24}[self.motion_mode.get()]
        delay = {"Quiet": 55, "Smooth": 28, "Peak": 16}[self.motion_mode.get()]

        def render_chunk() -> None:
            nonlocal cursor, matches
            self.liked_search_after_id = None
            if generation != self.liked_search_generation or not self.winfo_exists():
                return
            end = min(total, cursor + chunk_size)
            for original_index in range(cursor + 1, end + 1):
                entry = entries[original_index - 1]
                title = str(entry.get("title") or "(unavailable)")
                folded_title = title.casefold()
                if query and query not in folded_title:
                    continue
                matches += 1
                prefix = f"{original_index}. "
                line_start = self.liked_preview.index("end-1c")
                self.liked_preview.insert("end", prefix + title + "\n")
                if query:
                    title_start = f"{line_start}+{len(prefix)}c"
                    title_end = f"{title_start}+{len(title)}c"
                    search_from = title_start
                    while True:
                        found = self.liked_preview.search(query, search_from, stopindex=title_end, nocase=True)
                        if not found:
                            break
                        finish = f"{found}+{len(query)}c"
                        self.liked_preview.tag_add("search_match", found, finish)
                        search_from = finish
            cursor = end
            if not self.download_active:
                self.progress.configure(value=round(cursor * 100 / total))
            self.liked_status.configure(text=f"Searching titles · {cursor} / {total}")
            if cursor < total:
                self.liked_search_after_id = self.after(delay, render_chunk)
                return
            self.liked_preview.configure(state="disabled")
            if query:
                summary = (f"{matches} title match(es) · original item numbers kept." if matches
                           else f"No title matches · {total} items loaded.")
            else:
                summary = f"Loaded {total} items · enter their numbers to queue downloads."
            self.liked_status.configure(text=summary)
            self._finish_action_progress(f"Search complete · {matches} match(es)" if query else "Liked list ready")

        render_chunk()

    def load_liked(self) -> None:
        err = self._validate()
        if err:
            messagebox.showerror("Cannot load Liked videos", err)
            return
        self.liked_status.configure(text="Loading Liked videos…")
        self._log("Reading the Liked videos playlist…")
        if self.liked_search_after_id:
            self.after_cancel(self.liked_search_after_id)
            self.liked_search_after_id = None
            self.liked_search_generation += 1
        self._set_busy(True)
        self._begin_action_progress("Loading Liked videos…", indeterminate=True)
        options = self._yt_options(extract_flat=True)
        threading.Thread(target=self._load_liked_worker, args=(options,), daemon=True).start()

    def _load_liked_worker(self, options: dict) -> None:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(LIKED_VIDEOS_URL, download=False)
            entries = list(info.get("entries") or [])
            entries = [entry for entry in entries if entry]
            self.events.put(("liked", entries))
        except Exception as exc:
            self.events.put(("error", f"Could not read Liked videos: {exc}"))

    def add_liked_selection(self) -> None:
        if not self.liked_entries:
            messagebox.showinfo("Liked videos", "Load your Liked videos first.")
            return
        try:
            indexes = self._parse_indices(self.liked_numbers.get())
        except ValueError:
            messagebox.showerror("Invalid item numbers", "Use numbers or ranges like 2,7,10-12.")
            return
        if not indexes:
            messagebox.showinfo("Item numbers", "Enter the Liked videos item numbers to add.")
            return
        selected = []
        missing = []
        for index in indexes:
            if index > len(self.liked_entries):
                missing.append(index)
                continue
            entry = self.liked_entries[index - 1]
            url = entry.get("url") or entry.get("webpage_url")
            if url and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"
            if url:
                selected.append((index, str(url)))
        if missing:
            messagebox.showwarning("Item not found", f"Liked videos has {len(self.liked_entries)} items; skipped invalid number(s): {', '.join(map(str, missing))}.")
        if not selected:
            messagebox.showinfo("No videos selected", "No selected item had a usable video link.")
            return

        if self.queue_selection_after_id:
            self.after_cancel(self.queue_selection_after_id)
            self.queue_selection_after_id = None
        self.queue_selection_generation += 1
        generation = self.queue_selection_generation
        self._begin_action_progress("Adding selected videos to queue…")
        queued = []
        position = 0
        delay = {"Quiet": 45, "Smooth": 24, "Peak": 16}[self.motion_mode.get()]

        def add_next() -> None:
            nonlocal position
            self.queue_selection_after_id = None
            if generation != self.queue_selection_generation:
                return
            original_index, video_url = selected[position]
            queued.append(video_url)
            position += 1
            if not self.download_active:
                self.progress.configure(value=round(position * 100 / len(selected)))
                self.status.configure(text=f"Queueing selection · {position} / {len(selected)}")
            if position < len(selected):
                self.queue_selection_after_id = self.after(delay, add_next)
                return
            existing = self.urls.get("1.0", "end").strip()
            content = "\n".join(queued)
            self.urls.insert("end", ("\n" if existing else "") + content + "\n")
            self._log(f"Added {len(queued)} selected Liked video(s) to the batch.")
            self._finish_action_progress(f"Queued {len(queued)} selected video(s)")

        add_next()

    def start_download(self) -> None:
        err = self._validate()
        if err:
            messagebox.showerror("Cannot start download", err)
            return
        urls = [line.strip() for line in self.urls.get("1.0", "end").splitlines() if line.strip()]
        if not urls:
            messagebox.showinfo("No URLs", "Paste URLs or add selected Liked videos first.")
            return
        playlist_items = self.items.get().strip()
        if playlist_items:
            try:
                self._parse_indices(playlist_items)
            except ValueError:
                messagebox.showerror("Invalid playlist items", "Use numbers or ranges like 1,3,5-8.")
                return
        self.batch_total = len(urls)
        self.batch_done = 0
        self.downloaded_count = 0
        self.queue_metric.configure(text=str(self.batch_total))
        self.downloaded_metric.configure(text="0")
        self.batch_progress_label.configure(text=f"Done 0 / {self.batch_total}")
        self.current_metric.configure(text="Starting")
        self.run_settings = {
            "kind": self.kind.get(),
            "container": self.container.get().lower(),
            "quality": self.quality.get(),
            "live_from_start": self.live_mode.get().startswith("From beginning"),
            "output_dir": self.output_dir.get(),
            "cookies": self.cookies.get().strip(),
            "ffmpeg": self.ffmpeg.get().strip(),
            "playlist_items": playlist_items,
            "include_thumbnail": self.include_thumbnail.get(),
        }
        self.download_active = True
        self.cancel_event.clear()
        self.skip_current_event.clear()
        self._set_busy(True)
        self.start_button.configure(state="disabled")
        self.skip_button.configure(state="normal")
        self.stop_button.configure(state="normal")
        self.progress.stop()
        self.progress.configure(value=0, maximum=100, mode="determinate", mask="{}%", text="")
        self.worker = threading.Thread(target=self._download_worker, args=(urls,), daemon=True)
        self.worker.start()

    def stop_download(self) -> None:
        self.cancel_event.set()
        self.status.configure(text="Stopping after the current fragment…")
        self._log("Stop requested; the current download will stop at a fragment boundary.")

    def skip_current(self) -> None:
        if self.worker and self.worker.is_alive():
            self.skip_current_event.set()
            self.status.configure(text="Skipping current item after this fragment…")
            self._log("Skip requested for the current item.")

    def _download_worker(self, urls: list[str]) -> None:
        total = len(urls)
        for index, url in enumerate(urls, 1):
            if self.cancel_event.is_set():
                break
            started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            captured: dict[str, dict] = {}
            self.events.put(("status", f"Item {index}/{total}: starting"))
            self.events.put(("item_started", index, total))

            def remember(data: dict) -> None:
                info = data.get("info_dict") or {}
                video_id = info.get("id")
                if video_id:
                    captured[str(video_id)] = copy.deepcopy(info)

            def hook(data: dict) -> None:
                remember(data)
                if self.cancel_event.is_set():
                    raise yt_dlp.utils.DownloadError("Stopped by user")
                if self.skip_current_event.is_set():
                    raise yt_dlp.utils.DownloadError("Skipped by user")
                if data.get("status") == "downloading":
                    downloaded = data.get("downloaded_bytes", 0)
                    size = data.get("total_bytes") or data.get("total_bytes_estimate")
                    pct = downloaded / size * 100 if size else 0
                    speed = data.get("_speed_str") or ""
                    eta = data.get("_eta_str") or ""
                    self.events.put(("progress", pct, f"Item {index}/{total}: {pct:.1f}% {speed} ETA {eta}"))
                elif data.get("status") == "finished":
                    self.events.put(("progress", 100, f"Item {index}/{total}: processing…"))

            try:
                options = self._download_opts(hook, self.run_settings)
                options["postprocessor_hooks"] = [remember]
                with yt_dlp.YoutubeDL(options) as ydl:
                    result = ydl.download([url])
                if result:
                    self.events.put(("log", f"Download reported an issue for {url}"))
                    self.events.put(("job_done", False, "issue"))
                else:
                    completed_at = datetime.now().astimezone().isoformat(timespec="seconds")
                    for info in captured.values():
                        video_id = str(info.get("id") or "")
                        output_path = None
                        possible = info.get("filepath") or info.get("_filename")
                        if possible and Path(possible).is_file():
                            output_path = Path(possible)
                        if not output_path and video_id:
                            candidates = [p for p in Path(self.run_settings["output_dir"]).glob(f"* [{video_id}].*")
                            if p.is_file() and p.suffix.lower() not in {".part", ".ytdl", ".jpg", ".jpeg", ".png", ".webp", ".avif"}]
                            if candidates:
                                output_path = max(candidates, key=lambda p: p.stat().st_mtime)
                        self.history.add(info, self.run_settings, status="downloaded",
                                         output_path=output_path, source_url=info.get("webpage_url") or url,
                                         started_at=started_at, completed_at=completed_at)
                    self.events.put(("history_changed",))
                    self.events.put(("log", f"Finished: {url}"))
                    self.events.put(("job_done", True, "downloaded"))
            except Exception as exc:
                message = str(exc)
                if self.cancel_event.is_set():
                    self.events.put(("log", f"Stopped: {url}"))
                    break
                if self.skip_current_event.is_set():
                    self.skip_current_event.clear()
                    self.events.put(("log", f"Skipped: {url}"))
                    self.events.put(("job_done", False, "skipped"))
                    continue
                self.events.put(("log", f"Failed: {url}\n  {message}"))
                self.events.put(("job_done", False, "failed"))
            self.skip_current_event.clear()
        self.events.put(("done", "Stopped" if self.cancel_event.is_set() else "Batch complete"))

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    if "processing…" in event[2].lower():
                        if self.progress_animation_id:
                            self.after_cancel(self.progress_animation_id)
                            self.progress_animation_id = None
                        self.progress.stop()
                        self.progress.configure(mode="indeterminate", mask=None, text="PROCESSING")
                        interval = {"Quiet": 120, "Smooth": 60, "Peak": 36}[self.motion_mode.get()]
                        self.progress.start(interval=interval)
                    else:
                        if str(self.progress.cget("mode")) == "indeterminate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate", mask="{}%", text="")
                        self._animate_progress(event[1])
                    self.status.configure(text=event[2])
                elif kind == "status":
                    self.status.configure(text=event[1])
                    self.progress.stop()
                    self.progress.configure(mode="determinate", mask="{}%", text="")
                    self._animate_progress(0)
                elif kind == "item_started":
                    self.current_metric.configure(text=f"{event[1]} / {event[2]}")
                elif kind == "job_done":
                    self.batch_done += 1
                    if event[1]:
                        self.downloaded_count += 1
                        self.downloaded_metric.configure(text=str(self.downloaded_count))
                    self.batch_progress_label.configure(text=f"Done {self.batch_done} / {self.batch_total}")
                elif kind == "log":
                    self._log(event[1])
                elif kind == "history_changed":
                    self._update_history_count()
                    if self.history_window and self.history_window.winfo_exists():
                        self._refresh_history()
                elif kind == "liked":
                    self._set_busy(False)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", mask="{}%", text="", value=0)
                    self.liked_entries = event[1]
                    self._render_liked_preview()
                    self._log(f"Loaded {len(self.liked_entries)} visible Liked videos.")
                elif kind == "error":
                    self._set_busy(False)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", mask="{}%", text="", value=0)
                    self.status.configure(text="Action failed")
                    self._log(event[1])
                    self.liked_status.configure(text="Could not load playlist. Check cookies and try again.")
                    messagebox.showerror("yt-dlp error", event[1])
                elif kind == "done":
                    self.download_active = False
                    self._set_busy(False)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", mask="{}%", text="")
                    if event[1] == "Batch complete":
                        self._animate_progress(100)
                    self.status.configure(text=event[1])
                    self.start_button.configure(state="normal")
                    self.skip_button.configure(state="disabled")
                    self.stop_button.configure(state="disabled")
                    self.current_metric.configure(text="Idle" if event[1] == "Batch complete" else "Stopped")
                    self._log(event[1])
        except queue.Empty:
            pass
        self.after(120 if self.busy else 500, self._drain_events)


if __name__ == "__main__":
    app = YtDlpDesktop()
    app.mainloop()
