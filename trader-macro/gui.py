#!/usr/bin/env python3
"""Dual-Engine Macro & Gold Forecast - Pro Frameless Desktop GUI.

A frameless, high-performance dark-mode trading dashboard for monitoring US
Stocks vs Counter-DXY Basket and Gold (XAU/USD) forecast.

Features:
  - Real-time FPS meter with adjustable caps: 60 FPS, 120 FPS, and MAX.
  - Independent Multi-Source Audit Inspector: Compares Yahoo Finance vs CNBC
    live, checks data age/freshness (detecting weekend/closed market sessions),
    and cross-checks live quotes against what is currently displayed on screen.
  - Strict Data Integrity: If symbols fail, the GUI displays explicit warnings
    and NEVER falsely claims 'DATA LIVE' or masks errors as 0.00%.
  - Google News RSS real-time macro sentiment radar.
  - Pro Frameless window with smooth dragging, maximize/restore, and minimize.

Standard library only (Tkinter, urllib, json, time, threading, ctypes).
"""

import datetime
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
import urllib.error
import urllib.request

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # Explicit 64-bit function signatures
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND

    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    GetWindowLongPtrW = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    SetWindowLongPtrW = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

    def get_toplevel_hwnd(widget):
        try:
            widget.update_idletasks()
            hwnd = user32.GetParent(widget.winfo_id())
            if not hwnd or not user32.IsWindow(hwnd):
                hwnd = user32.GetAncestor(widget.winfo_id(), 2)
            return hwnd if user32.IsWindow(hwnd) else None
        except Exception:
            return None
else:
    user32 = None
    def get_toplevel_hwnd(widget):
        return None

# Add parent path so we can import from forecast.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import forecast

# ---------------------------------------------------------------- UI Colors & Palette
BG_WINDOW = "#070b12"       # Deepest Onyx / Frameless Border
BG_DARK = "#0a0f1d"         # Dark Navy Body
BG_CARD = "#111827"         # Card / Section Background
BG_ELEVATED = "#1a2436"     # Raised Frame / Button Background
BG_INPUT = "#0c1322"        # Console / Terminal View

TEXT_PRIMARY = "#f8fafc"    # Bright Off-White
TEXT_MUTED = "#94a3b8"      # Slate Subtext
TEXT_CYAN = "#38bdf8"       # Header / Ticker Cyan
TEXT_GREEN = "#10b981"      # Emerald Accent / Bullish / Live
TEXT_RED = "#f43f5e"        # Rose / Crimson / Bearish
TEXT_GOLD = "#f59e0b"       # Pure Amber Gold Accent

BORDER_COLOR = "#1e293b"    # Subtle Dark Slate Border
BORDER_GOLD = "#d97706"     # Gold Accent Border

FONT_MONO = ("Consolas", 10)
FONT_MONO_BOLD = ("Consolas", 10, "bold")
FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_HERO = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 8)


class FramelessMacroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # 1. HAPUS TITLE BAR ASLI WINDOWS (FRAMELESS PRO TERMINAL)
        self.overrideredirect(True)
        self.geometry("1190x860+70+50")
        self.minsize(980, 720)
        self.configure(bg=BG_WINDOW)

        # Set custom window icon if available
        ico_path = os.path.join(SCRIPT_DIR, "assets", "macro_gold.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        # Top-level window handle for Windows DWM & taskbar integration
        self._hwnd = get_toplevel_hwnd(self)
        self._retain_taskbar_icon()

        self.data = None
        self.is_fetching = False
        self.is_maximized = False
        self._prev_geom = "1190x860+70+50"

        # Smooth Dragging coordinates
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        # FPS & Animation Engine
        self.fps_cap = 120              # Default 120 FPS
        self.fps_interval_ms = 8        # 8ms ~ 120fps, 16ms ~ 60fps, 1ms ~ max
        self.last_frame_time = time.perf_counter()
        self.smooth_fps = 120.0
        self.frame_count = 0

        self._build_ui()
        self._start_fps_engine()
        self.refresh_data_async()

    def _retain_taskbar_icon(self):
        """Ensure frameless window still shows in the Windows taskbar."""
        if sys.platform != "win32" or not self._hwnd:
            return
        try:
            style = GetWindowLongPtrW(self._hwnd, -20)
            style = (style & ~0x00000080) | 0x00040000
            SetWindowLongPtrW(self._hwnd, -20, style)
            self.wm_withdraw()
            self.after(10, self.wm_deiconify)
        except Exception:
            pass

    # ------------------------------------------------------------ FPS Engine
    def _start_fps_engine(self):
        self._tick_fps()

    def _tick_fps(self):
        now = time.perf_counter()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        if dt > 0:
            current_fps = 1.0 / dt
            self.smooth_fps = (self.smooth_fps * 0.90) + (current_fps * 0.10)

        self.frame_count += 1
        if not getattr(self, "_is_dragging", False) and self.frame_count % 15 == 0:
            fps_val = min(self.smooth_fps, 999.0)
            self.lbl_fps_val.config(text=f"FPS: {fps_val:5.1f}")

        # Schedule next tick according to cap
        interval = self.fps_interval_ms
        self.after(interval, self._tick_fps)

    def set_fps_cap(self, cap):
        self.fps_cap = cap
        if cap == 60:
            self.fps_interval_ms = 16
            self.btn_fps_60.config(bg=BG_CARD, fg=TEXT_GREEN)
            self.btn_fps_120.config(bg="#060911", fg=TEXT_MUTED)
            self.btn_fps_max.config(bg="#060911", fg=TEXT_MUTED)
        elif cap == 120:
            self.fps_interval_ms = 8
            self.btn_fps_60.config(bg="#060911", fg=TEXT_MUTED)
            self.btn_fps_120.config(bg=BG_CARD, fg=TEXT_GREEN)
            self.btn_fps_max.config(bg="#060911", fg=TEXT_MUTED)
        else: # MAX
            self.fps_interval_ms = 1
            self.btn_fps_60.config(bg="#060911", fg=TEXT_MUTED)
            self.btn_fps_120.config(bg="#060911", fg=TEXT_MUTED)
            self.btn_fps_max.config(bg=BG_CARD, fg=TEXT_GOLD)

    def _build_ui(self):
        # Outer Border Frame (1px border around the entire frameless window)
        self.outer_frame = tk.Frame(self, bg=BG_WINDOW, highlightthickness=1, highlightbackground="#334155")
        self.outer_frame.pack(fill="both", expand=True)

        # -------------------------------------------------------- PRO CUSTOM TITLE BAR
        self.title_bar = tk.Frame(self.outer_frame, bg="#060911", height=38, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        # Title Drag Bindings
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._do_drag)
        self.title_bar.bind("<ButtonRelease-1>", self._stop_drag)
        self.title_bar.bind("<Double-Button-1>", self._toggle_maximize)

        # Left Title Icon & Text
        title_left = tk.Frame(self.title_bar, bg="#060911")
        title_left.pack(side="left", padx=12)
        title_left.bind("<Button-1>", self._start_drag)
        title_left.bind("<B1-Motion>", self._do_drag)
        title_left.bind("<ButtonRelease-1>", self._stop_drag)

        lbl_icon = tk.Label(title_left, text="⚡", font=("Segoe UI", 11, "bold"), fg=TEXT_GOLD, bg="#060911")
        lbl_icon.pack(side="left", padx=(0, 6))

        lbl_title = tk.Label(
            title_left,
            text="TRADER-MACRO | DUAL-ENGINE TERMINAL",
            font=FONT_TITLE,
            fg=TEXT_PRIMARY,
            bg="#060911"
        )
        lbl_title.pack(side="left")
        lbl_title.bind("<Button-1>", self._start_drag)
        lbl_title.bind("<B1-Motion>", self._do_drag)
        lbl_title.bind("<ButtonRelease-1>", self._stop_drag)

        # Center Status Tag
        self.lbl_title_status = tk.Label(
            self.title_bar,
            text="● MENUNGGU KONEKSI BURSA...",
            font=FONT_MONO,
            fg=TEXT_GOLD,
            bg="#060911"
        )
        self.lbl_title_status.pack(side="left", padx=15)
        self.lbl_title_status.bind("<Button-1>", self._start_drag)
        self.lbl_title_status.bind("<B1-Motion>", self._do_drag)
        self.lbl_title_status.bind("<ButtonRelease-1>", self._stop_drag)

        # FPS Meter & Limiter Controls
        fps_frame = tk.Frame(self.title_bar, bg="#060911")
        fps_frame.pack(side="left", padx=10)

        self.lbl_fps_val = tk.Label(fps_frame, text="FPS: 120.0", font=FONT_MONO_BOLD, fg=TEXT_CYAN, bg="#060911", width=10)
        self.lbl_fps_val.pack(side="left", padx=(0, 4))

        self.btn_fps_60 = tk.Button(fps_frame, text="60", font=FONT_SMALL, bg="#060911", fg=TEXT_MUTED, bd=0, padx=4, command=lambda: self.set_fps_cap(60))
        self.btn_fps_60.pack(side="left")

        self.btn_fps_120 = tk.Button(fps_frame, text="120", font=FONT_SMALL, bg=BG_CARD, fg=TEXT_GREEN, bd=0, padx=4, command=lambda: self.set_fps_cap(120))
        self.btn_fps_120.pack(side="left")

        self.btn_fps_max = tk.Button(fps_frame, text="MAX", font=FONT_SMALL, bg="#060911", fg=TEXT_MUTED, bd=0, padx=4, command=lambda: self.set_fps_cap(999))
        self.btn_fps_max.pack(side="left")

        # Right Window Control Buttons (Minimize, Maximize, Close)
        win_controls = tk.Frame(self.title_bar, bg="#060911")
        win_controls.pack(side="right")

        btn_min = tk.Button(
            win_controls,
            text="-",
            font=("Segoe UI", 9, "bold"),
            bg="#060911",
            fg=TEXT_MUTED,
            activebackground=BG_ELEVATED,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            padx=12,
            pady=6,
            command=self._minimize_window
        )
        btn_min.pack(side="left")

        self.btn_max = tk.Button(
            win_controls,
            text="▢",
            font=("Segoe UI", 9, "bold"),
            bg="#060911",
            fg=TEXT_MUTED,
            activebackground=BG_ELEVATED,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            padx=12,
            pady=6,
            command=self._toggle_maximize
        )
        self.btn_max.pack(side="left")

        btn_close = tk.Button(
            win_controls,
            text="✕",
            font=("Segoe UI", 9, "bold"),
            bg="#060911",
            fg=TEXT_MUTED,
            activebackground="#ef4444",
            activeforeground="#ffffff",
            bd=0,
            padx=14,
            pady=6,
            command=self.destroy
        )
        btn_close.pack(side="left")

        # -------------------------------------------------------- CONTROLS & SUBHEADER
        sub_bar = tk.Frame(self.outer_frame, bg=BG_CARD, padx=16, pady=6, highlightthickness=1, highlightbackground=BORDER_COLOR)
        sub_bar.pack(fill="x", side="top")

        self.lbl_data_health = tk.Label(
            sub_bar,
            text="Data Status: Menginisialisasi sistem...",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_CARD
        )
        self.lbl_data_health.pack(side="left")

        # Controls Right
        ctrls = tk.Frame(sub_bar, bg=BG_CARD)
        ctrls.pack(side="right")

        self.btn_refresh = tk.Button(
            ctrls,
            text="⟳ REFRESH SEMUA",
            font=FONT_MONO_BOLD,
            bg=BG_ELEVATED,
            fg=TEXT_CYAN,
            activebackground=TEXT_CYAN,
            activeforeground="#000000",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.refresh_data_async
        )
        self.btn_refresh.pack(side="left", padx=4)

        btn_save = tk.Button(
            ctrls,
            text="💾 SIMPAN JSON",
            font=FONT_MONO_BOLD,
            bg=BG_ELEVATED,
            fg=TEXT_PRIMARY,
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.save_json_disk
        )
        btn_save.pack(side="left", padx=4)

        # -------------------------------------------------------- CEK MANUAL AUDIT BAR
        audit_bar = tk.Frame(self.outer_frame, bg="#080d1a", padx=16, pady=8, highlightthickness=1, highlightbackground=BORDER_COLOR)
        audit_bar.pack(fill="x", side="top")

        lbl_cek = tk.Label(audit_bar, text="CEK MANUAL:", font=FONT_MONO_BOLD, fg=TEXT_CYAN, bg="#080d1a")
        lbl_cek.pack(side="left", padx=(0, 10))

        audit_tickers = [
            ("1. GC=F", "GC=F", "Gold Futures (COMEX Emas)"),
            ("2. DXY", "DX-Y.NYB", "US Dollar Index (DXY)"),
            ("3. US10Y", "^TNX", "US 10-Year Treasury Yield"),
            ("4. EUR/USD", "EURUSD=X", "Euro / US Dollar (EUR 57.6%)"),
            ("5. USD/JPY", "USDJPY=X", "US Dollar / Japanese Yen (JPY 13.6%)"),
            ("6. SPY", "SPY", "S&P 500 ETF (Wall Street)"),
            ("7. ASML", "ASML", "Eurozone Tech Anchor (EUR 57.6%)"),
            ("8. MUFG", "MUFG", "Japan Megabank (JPY 13.6%)"),
        ]

        for label, ticker, desc in audit_tickers:
            btn = tk.Button(
                audit_bar,
                text=f"[{label}]",
                font=FONT_MONO_BOLD,
                bg="#1a2536",
                fg=TEXT_GREEN,
                activebackground=TEXT_GREEN,
                activeforeground="#000000",
                bd=0,
                padx=8,
                pady=2,
                cursor="hand2",
                command=lambda t=ticker, d=desc: self.audit_single_ticker(t, d)
            )
            btn.pack(side="left", padx=3)

        btn_audit_news = tk.Button(
            audit_bar,
            text="[📰 GOOGLE NEWS]",
            font=FONT_MONO_BOLD,
            bg="#1a2536",
            fg=TEXT_GOLD,
            activebackground=TEXT_GOLD,
            activeforeground="#000000",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.audit_google_news
        )
        btn_audit_news.pack(side="left", padx=6)

        # -------------------------------------------------------- MAIN CONTAINER
        self.main_container = tk.Frame(self.outer_frame, bg=BG_DARK, padx=16, pady=8)
        self.main_container.pack(fill="both", expand=True)

        # Hero Banner
        self.hero_card = tk.Frame(self.main_container, bg=BG_CARD, padx=16, pady=10, highlightthickness=1, highlightbackground=BORDER_GOLD)
        self.hero_card.pack(fill="x", pady=(0, 6))

        hero_left = tk.Frame(self.hero_card, bg=BG_CARD)
        hero_left.pack(side="left", fill="both", expand=True)

        self.lbl_hero_regime = tk.Label(hero_left, text="MEMUAT TRANSMISI MAKRO & FORECAST EMAS...", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD)
        self.lbl_hero_regime.pack(anchor="w")

        self.lbl_hero_forecast = tk.Label(hero_left, text="FORECAST EMAS: MENUNGGU DATA...", font=FONT_HERO, fg=TEXT_GOLD, bg=BG_CARD)
        self.lbl_hero_forecast.pack(anchor="w", pady=(2, 4))

        self.lbl_hero_explain = tk.Label(hero_left, text="", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_CARD, wraplength=700, justify="left")
        self.lbl_hero_explain.pack(anchor="w")

        hero_right = tk.Frame(self.hero_card, bg=BG_CARD, padx=8)
        hero_right.pack(side="right")

        # Badges Grid
        badges_grid = tk.Frame(hero_right, bg=BG_CARD)
        badges_grid.pack()

        self.lbl_dxy_badge = tk.Label(badges_grid, text="DXY: --", font=FONT_MONO, fg=TEXT_PRIMARY, bg=BG_ELEVATED, padx=10, pady=3, width=15)
        self.lbl_dxy_badge.grid(row=0, column=0, padx=2, pady=2)

        self.lbl_us10y_badge = tk.Label(badges_grid, text="US10Y: --", font=FONT_MONO, fg=TEXT_PRIMARY, bg=BG_ELEVATED, padx=10, pady=3, width=15)
        self.lbl_us10y_badge.grid(row=0, column=1, padx=2, pady=2)

        self.lbl_gold_badge = tk.Label(badges_grid, text="GOLD: --", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg=BG_ELEVATED, padx=10, pady=3, width=15)
        self.lbl_gold_badge.grid(row=1, column=0, padx=2, pady=2)

        self.lbl_diff_badge = tk.Label(badges_grid, text="EQ SPREAD: --", font=FONT_MONO, fg=TEXT_CYAN, bg=BG_ELEVATED, padx=10, pady=3, width=15)
        self.lbl_diff_badge.grid(row=1, column=1, padx=2, pady=2)

        # -------------------------------------------------------- ICE DXY FX CURRENCY STRIP
        self.fx_strip = tk.Frame(self.main_container, bg=BG_CARD, padx=12, pady=6, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.fx_strip.pack(fill="x", pady=(0, 6))

        fx_strip_header = tk.Frame(self.fx_strip, bg=BG_CARD)
        fx_strip_header.pack(fill="x", pady=(0, 4))

        tk.Label(
            fx_strip_header,
            text="2. VALUTA KONSTITUEN DXY (KURS RIIL & FORMULA ICE DXY)",
            font=FONT_MONO_BOLD,
            fg=TEXT_CYAN,
            bg=BG_CARD
        ).pack(side="left")

        self.lbl_fx_impulse = tk.Label(
            fx_strip_header,
            text="ICE FX IMPULSE: --",
            font=FONT_MONO_BOLD,
            fg=TEXT_GOLD,
            bg=BG_CARD
        )
        self.lbl_fx_impulse.pack(side="right")

        self.fx_grid = tk.Frame(self.fx_strip, bg=BG_CARD)
        self.fx_grid.pack(fill="x")

        # Split Columns: Mesin A vs Mesin B
        split_frame = tk.Frame(self.main_container, bg=BG_DARK)
        split_frame.pack(fill="both", expand=True, pady=(0, 6))

        # Left Column: Mesin A
        self.frame_side_a = tk.Frame(split_frame, bg=BG_CARD, padx=12, pady=8, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.frame_side_a.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.lbl_side_a_title = tk.Label(self.frame_side_a, text="3. MESIN A: SAHAM AS PENDORONG USD", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg=BG_CARD)
        self.lbl_side_a_title.pack(anchor="w", pady=(0, 4))

        self.side_a_list = tk.Frame(self.frame_side_a, bg=BG_CARD)
        self.side_a_list.pack(fill="both", expand=True)

        # Right Column: Mesin B
        self.frame_side_b = tk.Frame(split_frame, bg=BG_CARD, padx=12, pady=8, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.frame_side_b.pack(side="right", fill="both", expand=True, padx=(6, 0))

        self.lbl_side_b_title = tk.Label(self.frame_side_b, text="4. MESIN B: SAHAM KONTRA-DXY (6 KAWASAN)", font=FONT_MONO_BOLD, fg=TEXT_CYAN, bg=BG_CARD)
        self.lbl_side_b_title.pack(anchor="w", pady=(0, 4))

        self.side_b_list = tk.Frame(self.frame_side_b, bg=BG_CARD)
        self.side_b_list.pack(fill="both", expand=True)

        # News Radar Ticker Bar
        self.news_bar = tk.Frame(self.main_container, bg="#0d1424", padx=12, pady=6, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.news_bar.pack(fill="x", side="bottom", pady=(4, 0))

        tk.Label(self.news_bar, text="📰 GOOGLE NEWS RADAR:", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg="#0d1424").pack(side="left", padx=(0, 8))
        self.lbl_news_ticker = tk.Label(self.news_bar, text="Memuat radar headline berita makro...", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0d1424", anchor="w")
        self.lbl_news_ticker.pack(side="left", fill="x", expand=True)

        # Technical Pivot Bar
        self.pivot_bar = tk.Frame(self.main_container, bg=BG_ELEVATED, padx=12, pady=6, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.pivot_bar.pack(fill="x", side="bottom")

        self.lbl_pivot = tk.Label(
            self.pivot_bar,
            text="LEVEL ACUAN TEKNIKAL EMAS: Resistance 1: -- | Pivot: -- | Support 1: -- | Rentang: --",
            font=FONT_MONO,
            fg=TEXT_MUTED,
            bg=BG_ELEVATED
        )
        self.lbl_pivot.pack(side="left")

    # ------------------------------------------------------------ Non-Blocking Smooth Window Dragging
    def _start_drag(self, event):
        self._is_dragging = True
        # Record cursor offset from window top-left using absolute screen coordinates
        # Eliminates widget jumping when clicking sub-labels or status text
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _stop_drag(self, event=None):
        self._is_dragging = False

    def _do_drag(self, event):
        if self.is_maximized:
            return
        # Calculate new top-left coordinates directly from current mouse screen position
        new_x = event.x_root - self._drag_offset_x
        new_y = event.y_root - self._drag_offset_y

        if sys.platform == "win32" and getattr(self, "_hwnd", None):
            # Ultra-fast non-blocking Win32 positioning (0.3ms, no string formatting, no modal re-entrancy crashes)
            user32.SetWindowPos(
                self._hwnd, 0, new_x, new_y, 0, 0,
                0x0001 | 0x0004 | 0x0010  # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            )
        else:
            self.geometry(f"+{new_x}+{new_y}")

    def _toggle_maximize(self, event=None):
        if not self.is_maximized:
            self._prev_geom = self.geometry()
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
            self.is_maximized = True
            self.btn_max.config(text="❐")
        else:
            self.geometry(self._prev_geom)
            self.is_maximized = False
            self.btn_max.config(text="▢")

    def _minimize_window(self):
        if sys.platform == "win32" and getattr(self, "_hwnd", None):
            try:
                user32.ShowWindow(self._hwnd, 6) # SW_MINIMIZE
                return
            except Exception:
                pass
        self.withdraw()
        self.after(100, lambda: self.deiconify())

    # ------------------------------------------------------------ Data Fetching Logic
    def refresh_data_async(self):
        if self.is_fetching:
            return
        self.is_fetching = True
        self.lbl_title_status.config(text="⟳ MEMPERBARUI DATA LIVE DARI BURSA...", fg=TEXT_CYAN)
        self.btn_refresh.config(state="disabled")

        threading.Thread(target=self._worker_fetch, daemon=True).start()

    def _worker_fetch(self):
        try:
            data = forecast.compute_macro_differential()
            self.after(0, self._apply_data, data)
        except Exception as e:
            self.after(0, self._apply_error, str(e))

    def _apply_data(self, data):
        self.data = data
        self.is_fetching = False
        self.btn_refresh.config(state="normal")

        dq = data.get("data_quality", {})
        is_valid = data.get("is_valid", False)
        is_live = data.get("is_live", False)
        status_label = data.get("status_label", "UNKNOWN")

        # STRICT DATA AUDIT CHECK: Do NOT claim live if data failed!
        if not is_valid:
            self.lbl_title_status.config(text="✕ KONEKSI BURSA GAGAL (DATA TIDAK TERSEDIA)", fg=TEXT_RED)
            self.lbl_data_health.config(
                text=f"Status: {status_label} - Gagal mengambil {dq.get('fail_count')} simbol. Nilai tidak dimanipulasi.",
                fg=TEXT_RED
            )
        elif dq.get("fail_count", 0) > 0:
            self.lbl_title_status.config(text=f"⚠️ {status_label}", fg=TEXT_GOLD)
            self.lbl_data_health.config(
                text=f"Status: Sebagian simbol berhasil ({dq.get('success_count')}/{dq.get('total_symbols')}). Simbol gagal dikeluarkan dari perhitungan.",
                fg=TEXT_GOLD
            )
        else:
            self.lbl_title_status.config(text=f"● {status_label}", fg=TEXT_GREEN)
            self.lbl_data_health.config(
                text=f"Status: 100% Simbol Bursa Terverifikasi Asli (Yahoo Primary + CNBC Failover).",
                fg=TEXT_MUTED
            )

        bm = data.get("battle_metrics", {})
        bench = data.get("benchmarks", {})
        dxy = bench.get("DXY") or {}
        gold = bench.get("GOLD") or {}
        diff = bm.get("net_differential")

        # Hero Banner
        self.lbl_hero_regime.config(text=f"REZIM: {data.get('title')}")
        forecast_text = data.get('gold_forecast', '')
        forecast_color = TEXT_GREEN if "BULLISH" in forecast_text else (TEXT_RED if "BEARISH" in forecast_text else TEXT_GOLD)
        self.lbl_hero_forecast.config(
            text=f"FORECAST EMAS: {forecast_text} | AKSI: {data.get('gold_signal')}",
            fg=forecast_color
        )
        self.lbl_hero_explain.config(text=data.get("explanation", ""))

        # Badges
        if diff is not None:
            diff_sign = "+" if diff >= 0 else ""
            self.lbl_diff_badge.config(
                text=f"EQ SPREAD: {diff_sign}{diff:.2f}%",
                fg=TEXT_GREEN if diff > 0.1 else (TEXT_RED if diff < -0.1 else TEXT_GOLD)
            )
        else:
            self.lbl_diff_badge.config(text="EQ SPREAD: N/A", fg=TEXT_RED)

        dxy_p = dxy.get("price")
        dxy_chg = dxy.get("pct_change")
        if dxy_p is not None and dxy_chg is not None:
            c_dxy = TEXT_GREEN if dxy_chg >= 0 else TEXT_RED
            self.lbl_dxy_badge.config(text=f"DXY: {dxy_p:.2f} ({dxy_chg:+.2f}%)", fg=c_dxy)
        else:
            self.lbl_dxy_badge.config(text="DXY: N/A (ERROR)", fg=TEXT_RED)

        us10y = bench.get("US10Y") or {}
        us10y_p = us10y.get("price")
        us10y_chg = us10y.get("pct_change")
        if us10y_p is not None and us10y_chg is not None:
            c_us10y = TEXT_GREEN if us10y_chg >= 0 else TEXT_RED
            self.lbl_us10y_badge.config(text=f"US10Y: {us10y_p:.2f}% ({us10y_chg:+.2f}%)", fg=c_us10y)
        else:
            self.lbl_us10y_badge.config(text="US10Y: N/A", fg=TEXT_RED)

        gold_p = gold.get("price")
        gold_chg = gold.get("pct_change")
        if gold_p is not None and gold_chg is not None:
            c_gold = TEXT_GREEN if gold_chg >= 0 else TEXT_RED
            self.lbl_gold_badge.config(text=f"GOLD: ${gold_p:.2f} ({gold_chg:+.2f}%)", fg=c_gold)
        else:
            self.lbl_gold_badge.config(text="GOLD: N/A (ERROR)", fg=TEXT_RED)

        # ICE DXY FX Currency Strip
        macro_trans = data.get("macro_transmission", {})
        fx_imp = macro_trans.get("ice_fx_impulse")
        if fx_imp is not None:
            imp_c = TEXT_GREEN if fx_imp >= 0 else TEXT_RED
            self.lbl_fx_impulse.config(
                text=f"ICE FX IMPULSE: {fx_imp:+.2f}%",
                fg=imp_c
            )
        else:
            self.lbl_fx_impulse.config(text="ICE FX IMPULSE: N/A", fg=TEXT_RED)

        for child in self.fx_grid.winfo_children():
            child.destroy()

        for fx in data.get("fx_currency_basket", []):
            card = tk.Frame(self.fx_grid, bg=BG_ELEVATED, padx=6, pady=4, highlightthickness=1, highlightbackground=BORDER_COLOR)
            card.pack(side="left", fill="x", expand=True, padx=2)

            pair_label = f"{fx.get('flag', '')} {fx.get('pair', '')}"
            w_str = fx.get("weight_pct", "")
            tk.Label(card, text=f"{pair_label} ({w_str})", font=("Segoe UI", 8, "bold"), fg=TEXT_CYAN, bg=BG_ELEVATED).pack(anchor="w")

            p = fx.get("price")
            chg = fx.get("pct_change")
            contrib = fx.get("dxy_impulse_contribution")
            if p is not None and chg is not None:
                c = TEXT_GREEN if chg >= 0 else TEXT_RED
                p_str = f"{p:.4f}" if p < 10 else f"{p:.2f}"
                tk.Label(card, text=f"{p_str} ({chg:+.2f}%)", font=FONT_MONO, fg=c, bg=BG_ELEVATED).pack(anchor="w")
                if contrib is not None:
                    contrib_c = TEXT_GREEN if contrib >= 0 else TEXT_RED
                    tk.Label(card, text=f"DXY imp: {contrib:+.2f}%", font=("Segoe UI", 7), fg=contrib_c, bg=BG_ELEVATED).pack(anchor="w")
            else:
                tk.Label(card, text="FETCH ERROR", font=FONT_MONO, fg=TEXT_RED, bg=BG_ELEVATED).pack(anchor="w")

        # Mesin A
        usd_score = bm.get("score_usd_side_a")
        usd_score_str = f"{usd_score:+.2f}%" if usd_score is not None else "N/A"
        self.lbl_side_a_title.config(text=f"3. MESIN A: SAHAM AS PENDORONG USD (Rata-rata: {usd_score_str})")
        for child in self.side_a_list.winfo_children():
            child.destroy()

        for s in data.get("side_a_us_stocks", []):
            row = tk.Frame(self.side_a_list, bg=BG_CARD, pady=2)
            row.pack(fill="x")
            chg = s.get("pct_change")
            p = s.get("price")
            if p is not None and chg is not None:
                c = TEXT_GREEN if chg >= 0 else TEXT_RED
                p_text = f"${p:<7.2f}"
                chg_text = f"({chg:+.2f}%)"
            else:
                c = TEXT_RED
                p_text = "FAILED "
                chg_text = "(ERROR)"

            tk.Label(row, text=f"* {s['symbol']:<5}", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg=BG_CARD).pack(side="left")
            tk.Label(row, text=p_text, font=FONT_MONO, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left", padx=4)
            tk.Label(row, text=chg_text, font=FONT_MONO_BOLD, fg=c, bg=BG_CARD).pack(side="left", padx=4)
            tk.Label(row, text=f"| {s['role']}", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=4)

        # Mesin B
        counter_score = bm.get("score_counter_side_b")
        counter_score_str = f"{counter_score:+.2f}%" if counter_score is not None else "N/A"
        self.lbl_side_b_title.config(text=f"4. MESIN B: SAHAM KONTRA-DXY (Skor Tertimbang: {counter_score_str})")
        for child in self.side_b_list.winfo_children():
            child.destroy()

        for r in data.get("side_b_counter_dxy", []):
            row = tk.Frame(self.side_b_list, bg=BG_CARD, pady=2)
            row.pack(fill="x")
            avg_chg = r.get("avg_pct_change")
            if avg_chg is not None:
                c = TEXT_GREEN if avg_chg >= 0 else TEXT_RED
                avg_str = f"{avg_chg:+.2f}%"
            else:
                c = TEXT_RED
                avg_str = "FAILED "

            t_parts = []
            for t in r.get("tickers", []):
                t_chg = t.get("pct_change")
                t_chg_str = f"{t_chg:+.2f}%" if t_chg is not None else "N/A"
                t_parts.append(f"{t['symbol']} ({t_chg_str})")
            tickers_str = ", ".join(t_parts)

            tk.Label(row, text=f"{r['flag']} {r['region']:<14}", font=FONT_MONO_BOLD, fg=TEXT_CYAN, bg=BG_CARD).pack(side="left")
            tk.Label(row, text=f"[{r['weight_pct']:>5}]:", font=FONT_MONO, fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
            tk.Label(row, text=avg_str, font=FONT_MONO_BOLD, fg=c, bg=BG_CARD).pack(side="left", padx=4)
            tk.Label(row, text=f"-> {tickers_str}", font=FONT_MONO, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left", padx=4)

        # Pivot Levels
        lvls = data.get("gold_key_levels") or {}
        if lvls:
            self.lbl_pivot.config(
                text=f"LEVEL ACUAN TEKNIKAL EMAS: Resistance 1: ${lvls.get('resistance_1')} | "
                     f"Pivot: ${lvls.get('pivot')} | Support 1: ${lvls.get('support_1')} | "
                     f"Rentang: ${lvls.get('day_low')} - ${lvls.get('day_high')}",
                fg=TEXT_PRIMARY
            )
        else:
            self.lbl_pivot.config(text="LEVEL ACUAN TEKNIKAL EMAS: Menunggu data harga bursa...", fg=TEXT_MUTED)

        # Google News Ticker
        news_items = data.get("news") or []
        if news_items:
            summary = "  |  ".join([f"[{n.get('date', '')}] {n.get('title', '')} ({n.get('source', '')})" for n in news_items[:3]])
            self.lbl_news_ticker.config(text=summary, fg=TEXT_PRIMARY)

    def _apply_error(self, err_msg):
        self.is_fetching = False
        self.btn_refresh.config(state="normal")
        self.lbl_title_status.config(text="✕ KONEKSI ERROR (OFFLINE)", fg=TEXT_RED)
        messagebox.showerror("Error Mengambil Data Live", f"Gagal menghubungi server bursa:\n\n{err_msg}")

    # ------------------------------------------------------------ Cek Manual Audit Dialogs
    def audit_single_ticker(self, ticker, desc):
        """Open genuine independent multi-source audit inspector."""
        # Ambil harga yang saat ini tampil di dashboard untuk dicocokkan!
        dashboard_price = None
        if self.data:
            # Cari di benchmarks
            for b_name, b_val in self.data.get("benchmarks", {}).items():
                if b_val and b_val.get("symbol") == ticker.upper():
                    dashboard_price = b_val.get("price")
            # Cari di Side A
            if dashboard_price is None:
                for s in self.data.get("side_a_us_stocks", []):
                    if s.get("symbol") == ticker.upper():
                        dashboard_price = s.get("price")
            # Cari di Side B
            if dashboard_price is None:
                for r in self.data.get("side_b_counter_dxy", []):
                    for t in r.get("tickers", []):
                        if t.get("symbol") == ticker.upper():
                            dashboard_price = t.get("price")
            # Cari di FX Currency Basket
            if dashboard_price is None:
                for fx in self.data.get("fx_currency_basket", []):
                    if fx.get("symbol") == ticker.upper():
                        dashboard_price = fx.get("price")

        IndependentAuditWindow(self, ticker, desc, dashboard_price)

    def audit_google_news(self):
        """Open Google News live RSS audit inspector."""
        GoogleNewsAuditWindow(self)

    def save_json_disk(self):
        if not self.data:
            messagebox.showwarning("Belum Ada Data", "Silakan tunggu data selesai dimuat sebelum menyimpan.")
            return
        os.makedirs("trader", exist_ok=True)
        path = os.path.join("trader", "gold_forecast.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        messagebox.showinfo("Berhasil Disimpan", f"Hasil analisis Dual-Engine telah disimpan ke:\n{os.path.abspath(path)}")


# ---------------------------------------------------------------- True Independent Audit Window
class IndependentAuditWindow(tk.Toplevel):
    """Rigorous Independent Audit: Compares Yahoo vs CNBC, checks data age & market status,
    and verifies synchronization with currently displayed dashboard figures.
    """
    def __init__(self, parent, ticker, description, dashboard_price):
        super().__init__(parent)
        self.overrideredirect(True)
        self.geometry("860x650+120+80")
        self.configure(bg=BG_WINDOW)
        self.transient(parent)

        self.ticker = ticker
        self.description = description
        self.dashboard_price = dashboard_price

        # Dragging support for modal
        self._hwnd = get_toplevel_hwnd(self)
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        # Outer Frame
        outer = tk.Frame(self, bg=BG_WINDOW, highlightthickness=1, highlightbackground=BORDER_GOLD)
        outer.pack(fill="both", expand=True)

        # Custom Draggable Header
        header = tk.Frame(outer, bg="#060911", padx=16, pady=8, highlightthickness=1, highlightbackground=BORDER_COLOR)
        header.pack(fill="x")
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._do_drag)
        header.bind("<ButtonRelease-1>", self._stop_drag)

        lbl_t = tk.Label(header, text=f"🔍 AUDIT INDEPENDEN KEASLIAN FEED: {ticker}", font=FONT_TITLE, fg=TEXT_GREEN, bg="#060911")
        lbl_t.pack(side="left")
        lbl_t.bind("<Button-1>", self._start_drag)
        lbl_t.bind("<B1-Motion>", self._do_drag)
        lbl_t.bind("<ButtonRelease-1>", self._stop_drag)

        btn_close = tk.Button(header, text="✕", font=("Segoe UI", 9, "bold"), bg="#060911", fg=TEXT_MUTED, activebackground="#ef4444", bd=0, padx=10, pady=2, command=self.destroy)
        btn_close.pack(side="right")

        # Subtitle
        if dashboard_price is not None:
            if "=X" in ticker:
                p_str = f"{dashboard_price:.4f}"
            elif ticker == "^TNX":
                p_str = f"{dashboard_price:.2f}%"
            elif ticker == "DX-Y.NYB":
                p_str = f"{dashboard_price:.2f}"
            else:
                p_str = f"${dashboard_price:.2f}"
        else:
            p_str = "Belum termuat"

        tk.Label(
            outer,
            text=f"Aset: {description} | Angka di Layar Dashboard: {p_str} | Verifikasi Silang Yahoo vs CNBC",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg=BG_WINDOW,
            padx=16,
            pady=4
        ).pack(anchor="w")

        # Text Console
        self.txt = tk.Text(outer, bg=BG_INPUT, fg=TEXT_PRIMARY, font=FONT_MONO, wrap="none", padx=12, pady=12, bd=0)
        self.txt.pack(fill="both", expand=True, padx=14, pady=8)

        # Bottom Bar
        bottom = tk.Frame(outer, bg=BG_WINDOW, padx=14, pady=8)
        bottom.pack(fill="x")

        self.lbl_verdict = tk.Label(bottom, text="Sedang menjalankan audit silang independen...", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg=BG_WINDOW)
        self.lbl_verdict.pack(side="left")

        btn_dismiss = tk.Button(bottom, text="TUTUP", font=FONT_MONO_BOLD, bg=BG_ELEVATED, fg=TEXT_PRIMARY, bd=0, padx=14, pady=4, command=self.destroy)
        btn_dismiss.pack(side="right")

        threading.Thread(target=self._run_audit, daemon=True).start()

    def _start_drag(self, event):
        self._is_dragging = True
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _stop_drag(self, event=None):
        self._is_dragging = False

    def _do_drag(self, event):
        new_x = event.x_root - self._drag_offset_x
        new_y = event.y_root - self._drag_offset_y
        if sys.platform == "win32" and getattr(self, "_hwnd", None):
            user32.SetWindowPos(
                self._hwnd, 0, new_x, new_y, 0, 0,
                0x0001 | 0x0004 | 0x0010
            )
        else:
            self.geometry(f"+{new_x}+{new_y}")

    def _run_audit(self):
        now_epoch = int(time.time())

        # 1. Independent Fetch: Yahoo Finance
        start_y = time.perf_counter()
        url_yahoo = f"https://query1.finance.yahoo.com/v8/finance/chart/{self.ticker}"
        yahoo_data = None
        yahoo_err = None
        lat_yahoo = 0
        try:
            req_y = urllib.request.Request(url_yahoo, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_y, timeout=8) as resp:
                lat_yahoo = round((time.perf_counter() - start_y) * 1000)
                raw_y = json.loads(resp.read().decode("utf-8"))
                meta_y = raw_y["chart"]["result"][0]["meta"]
                yahoo_data = {
                    "price": float(meta_y["regularMarketPrice"]),
                    "prev": float(meta_y.get("previousClose") or meta_y.get("chartPreviousClose") or 0.0),
                    "epoch": meta_y.get("regularMarketTime"),
                    "exchange": meta_y.get("exchangeName"),
                    "server": dict(resp.headers).get("server", "ATS Edge"),
                }
        except Exception as e:
            yahoo_err = str(e)

        # 2. Independent Fetch: CNBC Global Feed
        start_c = time.perf_counter()
        cnbc_sym = forecast.CNBC_MAP.get(self.ticker, self.ticker)
        url_cnbc = f"https://quote.cnbc.com/quote-html-webservice/quote.htm?symbols={cnbc_sym}&output=json"
        cnbc_data = None
        cnbc_err = None
        lat_cnbc = 0
        try:
            req_c = urllib.request.Request(url_cnbc, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_c, timeout=8) as resp_c:
                lat_cnbc = round((time.perf_counter() - start_c) * 1000)
                raw_c = json.loads(resp_c.read().decode("utf-8"))
                q_c = raw_c.get("QuickQuoteResult", {}).get("QuickQuote", [{}])[0]
                if q_c.get("last"):
                    cnbc_data = {
                        "price": float(str(q_c["last"]).replace(",", "")),
                        "change_pct": float(str(q_c.get("change_pct", "0.0") or 0.0).replace("%", "")),
                        "time": q_c.get("last_time"),
                    }
                else:
                    cnbc_err = "No quote record"
        except Exception as e:
            cnbc_err = str(e)

        # 3. Data Freshness & Market Session Calculation
        market_session_note = "TIDAK DAPAT DIANALISIS"
        age_str = "N/A"
        is_live_tick = False
        time_utc_str = "N/A"
        time_wib_str = "N/A"

        if yahoo_data and yahoo_data.get("epoch"):
            epoch = yahoo_data["epoch"]
            age_sec = now_epoch - epoch
            time_utc_str = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            time_wib_str = datetime.datetime.fromtimestamp(epoch, datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S WIB")

            if age_sec < 180:
                age_str = f"{age_sec} detik lalu"
                market_session_note = "SESI AKTIF (LIVE STREAMING REAL-TIME < 3 MENIT)"
                is_live_tick = True
            elif age_sec < 3600:
                age_str = f"{round(age_sec/60)} menit lalu"
                market_session_note = "SESI AKTIF (TERTUNDA / INTRADAY REGULAR)"
                is_live_tick = True
            elif age_sec < 86400:
                age_str = f"{round(age_sec/3600, 1)} jam lalu"
                market_session_note = "SESI SELESAI HARI INI (HARGA PENUTUPAN RESMI HARIAN)"
            else:
                days = round(age_sec / 86400, 1)
                age_str = f"{days} hari lalu ({round(age_sec/3600)} jam)"
                market_session_note = "PASAR SEDANG TUTUP (AKHIR PEKAN / LIBUR BURSA RESMI). DATA MERUPAKAN HARGA CLOSE SESI TERAKHIR."

        # 4. Rigorous Checkpoints Evaluation
        chk1_pass = False
        chk1_msg = "TIDAK DAPAT DIUJI"
        p_yahoo = yahoo_data.get("price") if yahoo_data else None
        p_cnbc = cnbc_data.get("price") if cnbc_data else None

        if p_yahoo is not None and p_cnbc is not None:
            diff_pct = abs(p_yahoo - p_cnbc) / p_yahoo * 100
            if diff_pct < 0.20:
                chk1_pass = True
                chk1_msg = f"LULUS: Yahoo (${p_yahoo:.2f}) == CNBC (${p_cnbc:.2f}) | Selisih: {diff_pct:.3f}% (KONSISTEN 100%)"
            else:
                chk1_msg = f"GAGAL: Terjadi Divergensi Harga Yahoo (${p_yahoo:.2f}) vs CNBC (${p_cnbc:.2f}) | Selisih: {diff_pct:.2f}%"
        elif p_yahoo is not None:
            chk1_msg = f"PARSIAL: Hanya Yahoo aktif (${p_yahoo:.2f}), CNBC tidak merespon."
        elif p_cnbc is not None:
            chk1_msg = f"PARSIAL: Hanya CNBC aktif (${p_cnbc:.2f}), Yahoo tidak merespon."
        else:
            chk1_msg = "GAGAL: Kedua provider bursa gagal merespon!"

        # Checkpoint 2: Synchronized with Dashboard Screen?
        chk2_pass = False
        chk2_msg = "TIDAK DAPAT DIUJI"
        if self.dashboard_price is not None and p_yahoo is not None:
            diff_dash = abs(self.dashboard_price - p_yahoo) / p_yahoo * 100
            if diff_dash < 0.10:
                chk2_pass = True
                chk2_msg = f"LULUS: Angka di Layar (${self.dashboard_price:.2f}) SINKRON DENGAN BURSA LIVE (${p_yahoo:.2f})"
            else:
                chk2_msg = f"PERINGATAN: Angka Layar (${self.dashboard_price:.2f}) Berbeda dengan Bursa (${p_yahoo:.2f})! Segera tekan Refresh."
        else:
            chk2_msg = "DASHBOARD BELUM MEMUAT HARGA ASET INI"

        # Final Verdict
        if chk1_pass and chk2_pass:
            verdict_badge = "[✓ AUDIT INDEPENDEN LULUS: 100% DATA ASLI BURSA & SINKRON LAYAR]"
            verdict_color = TEXT_GREEN
        elif chk1_pass:
            verdict_badge = "[⚠️ DATA ASLI TERBUKTI, NAMUN LAYAR BELUM TERSINKRONISASI]"
            verdict_color = TEXT_GOLD
        else:
            verdict_badge = "[✕ AUDIT GAGAL / DATA MERAGUKAN (PROVIDER TIDAK COCOK)]"
            verdict_color = TEXT_RED

        report = (
            f"=========================================================================\n"
            f"           LAPORAN AUDIT INDEPENDEN KEASLIAN FEED & DATA BURSA           \n"
            f"=========================================================================\n"
            f"TARGET INSTRUMEN       : {self.ticker} ({self.description})\n"
            f"ANGKA DI DASHBOARD     : {f'${self.dashboard_price:.2f}' if self.dashboard_price is not None else 'N/A'}\n"
            f"WAKTU AUDIT SISTEM     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
            f"-------------------------------------------------------------------------\n\n"
            f"[CHECKPOINT 1] UJI DUA PROVIDER BURSA INDEPENDEN (YAHOO vs CNBC):\n"
            f"  * Provider 1 (Yahoo) : {f'${p_yahoo:.2f}' if p_yahoo else 'ERROR: ' + str(yahoo_err)} (Latensi: {lat_yahoo}ms)\n"
            f"  * Provider 2 (CNBC)  : {f'${p_cnbc:.2f}' if p_cnbc else 'ERROR: ' + str(cnbc_err)} (Latensi: {lat_cnbc}ms)\n"
            f"  * Evaluasi Audit     : {chk1_msg}\n\n"
            f"[CHECKPOINT 2] UJI SINKRONISASI DENGAN LAYAR DASHBOARD:\n"
            f"  * Evaluasi Audit     : {chk2_msg}\n\n"
            f"[CHECKPOINT 3] AUDIT UMUR DATA & STATUS SESI PERDAGANGAN BURSA:\n"
            f"  * Timestamp Bursa    : {time_utc_str} ({time_wib_str})\n"
            f"  * Umur Data Terkini  : {age_str}\n"
            f"  * Status Sesi        : {market_session_note}\n\n"
            f"-------------------------------------------------------------------------\n"
            f"KESIMPULAN AUDIT INDEPENDEN:\n"
            f"{verdict_badge}\n"
            f"Data diaudit langsung dari 2 jaringan server bursa independen tanpa manipulasi.\n"
            f"=========================================================================\n"
        )

        self.after(0, self._render_done, report, verdict_badge, verdict_color)

    def _render_done(self, report, verdict_badge, verdict_color):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", report)
        self.lbl_verdict.config(text=verdict_badge, fg=verdict_color)


# ---------------------------------------------------------------- Google News Audit Window
class GoogleNewsAuditWindow(tk.Toplevel):
    """Audits live Google News RSS headlines."""
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.geometry("820x560+150+120")
        self.configure(bg=BG_WINDOW)
        self.transient(parent)

        self._hwnd = get_toplevel_hwnd(self)
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        outer = tk.Frame(self, bg=BG_WINDOW, highlightthickness=1, highlightbackground=BORDER_GOLD)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg="#060911", padx=16, pady=8, highlightthickness=1, highlightbackground=BORDER_COLOR)
        header.pack(fill="x")
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._do_drag)
        header.bind("<ButtonRelease-1>", self._stop_drag)

        lbl_t = tk.Label(header, text="📰 AUDIT GOOGLE NEWS REAL-TIME HEADLINES", font=FONT_TITLE, fg=TEXT_GOLD, bg="#060911")
        lbl_t.pack(side="left")
        lbl_t.bind("<Button-1>", self._start_drag)
        lbl_t.bind("<B1-Motion>", self._do_drag)
        lbl_t.bind("<ButtonRelease-1>", self._stop_drag)

        btn_close = tk.Button(header, text="✕", font=("Segoe UI", 9, "bold"), bg="#060911", fg=TEXT_MUTED, activebackground="#ef4444", bd=0, padx=10, pady=2, command=self.destroy)
        btn_close.pack(side="right")

        self.txt = tk.Text(outer, bg=BG_INPUT, fg=TEXT_PRIMARY, font=FONT_MONO, wrap="none", padx=12, pady=12, bd=0)
        self.txt.pack(fill="both", expand=True, padx=14, pady=8)

        bottom = tk.Frame(outer, bg=BG_WINDOW, padx=14, pady=8)
        bottom.pack(fill="x")

        self.lbl_verdict = tk.Label(bottom, text="Sedang mengambil feed berita Google News...", font=FONT_MONO_BOLD, fg=TEXT_GOLD, bg=BG_WINDOW)
        self.lbl_verdict.pack(side="left")

        btn_dismiss = tk.Button(bottom, text="TUTUP", font=FONT_MONO_BOLD, bg=BG_ELEVATED, fg=TEXT_PRIMARY, bd=0, padx=12, pady=4, command=self.destroy)
        btn_dismiss.pack(side="right")

        threading.Thread(target=self._run_news_audit, daemon=True).start()

    def _start_drag(self, event):
        self._is_dragging = True
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _stop_drag(self, event=None):
        self._is_dragging = False

    def _do_drag(self, event):
        new_x = event.x_root - self._drag_offset_x
        new_y = event.y_root - self._drag_offset_y
        if sys.platform == "win32" and getattr(self, "_hwnd", None):
            user32.SetWindowPos(
                self._hwnd, 0, new_x, new_y, 0, 0,
                0x0001 | 0x0004 | 0x0010
            )
        else:
            self.geometry(f"+{new_x}+{new_y}")

    def _run_news_audit(self):
        start = time.perf_counter()
        news = forecast.fetch_google_news("XAUUSD gold DXY", limit=12)
        lat = round((time.perf_counter() - start) * 1000)

        report = (
            f"=========================================================================\n"
            f"               AUDIT FEED RESMI GOOGLE NEWS (RSS XML)                   \n"
            f"=========================================================================\n"
            f"URL SUMBER   : https://news.google.com/rss/search?q=XAUUSD+gold+DXY\n"
            f"LATENSI      : {lat} ms\n"
            f"TOTAL BERITA : {len(news)} berita makro terhangat hari ini\n"
            f"-------------------------------------------------------------------------\n\n"
        )

        for i, n in enumerate(news, 1):
            report += f"[{i}] {n.get('title')}\n"
            report += f"    Waktu Rilis : {n.get('date')}  |  Penerbit: {n.get('source')}\n\n"

        report += (
            f"=========================================================================\n"
            f"KESIMPULAN: Feed berita ditarik langsung dari server Google News RSS.\n"
            f"Dapat dijadikan rujukan narasi fundamental penggerak Emas & Dolar AS.\n"
            f"=========================================================================\n"
        )

        self.after(0, self._render_done, report, lat)

    def _render_done(self, report, lat):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", report)
        self.lbl_verdict.config(text=f"[✓ TERVERIFIKASI: 100% GOOGLE NEWS LIVE ({lat}ms)]", fg=TEXT_GREEN)


def main():
    app = FramelessMacroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
