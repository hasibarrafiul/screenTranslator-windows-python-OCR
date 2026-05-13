"""
Overlay window with a draggable circular mini-button and an expandable
side panel that shows screen OCR text and its translation side-by-side.
"""
from __future__ import annotations

import io
import threading
import tkinter as tk
from tkinter import ttk
from ctypes import windll
from typing import Optional

from overlay.capture import ScreenCapture, LANGUAGES
from overlay.config import OverlayConfig
from overlay.translation import translate_text


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TOOLWINDOW = 0x80
LWA_ALPHA = 0x02
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0001
SWP_NOSIZE = 0x0002

DOUBLE_CLICK_INTERVAL = 300

LANG_TAGS = list(LANGUAGES.keys())


class OverlayWindow:
    def __init__(self, config: Optional[OverlayConfig] = None) -> None:
        self.config = config or OverlayConfig.load()
        self._capture = ScreenCapture()

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._expanded = False

        self._mini_size: int = self.config.mini_size
        self._mini_x: int = self.config.mini_x
        self._mini_y: int = self.config.mini_y
        self._mini_circle_center: tuple[int, int] = (0, 0)
        self._mini_circle_radius: int = 0

        self._original_text: str = ""
        self._translated_text: str = ""
        self._cached_screenshot: Optional[bytes] = None

        self._source_lang: str = "ja"
        self._target_lang: str = "en"

        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._drag_win_x: int = 0
        self._drag_win_y: int = 0
        self._dragging: bool = False

        self._click_timer_id: Optional[str] = None

        self._orig_widget: Optional[tk.Text] = None
        self._trans_widget: Optional[tk.Text] = None
        self._from_combo: Optional[ttk.Combobox] = None
        self._to_combo: Optional[ttk.Combobox] = None
        self._from_var: Optional[tk.StringVar] = None
        self._to_var: Optional[tk.StringVar] = None

    # ── Windows API helpers ─────────────────────────────────────────

    def _hwnd(self) -> int:
        assert self._root is not None
        return windll.user32.GetParent(self._root.winfo_id())

    def _set_topmost(self) -> None:
        windll.user32.SetWindowPos(self._hwnd(), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

    def _make_tool_window(self) -> None:
        hwnd = self._hwnd()
        windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW)

    def _apply_opacity(self, value: float) -> None:
        alpha = int(max(0, min(255, value * 255)))
        windll.user32.SetLayeredWindowAttributes(self._hwnd(), 0, alpha, LWA_ALPHA)

    def _screen_size(self) -> tuple[int, int]:
        assert self._root is not None
        return self._root.winfo_screenwidth(), self._root.winfo_screenheight()

    # ── State transitions ───────────────────────────────────────────

    def _show_mini(self) -> None:
        assert self._root is not None and self._canvas is not None
        self._expanded = False
        s = self._mini_size
        self._root.geometry(f"{s}x{s}+{self._mini_x}+{self._mini_y}")
        self._canvas.delete("all")
        self._draw_mini_circle(s)
        self._apply_opacity(self.config.mini_opacity)

    def _show_expanded(self) -> None:
        assert self._root is not None and self._canvas is not None
        self._expanded = True
        sw, sh = self._screen_size()
        pw = int(sw * self.config.expanded_width_pct)
        cx = self._mini_x + self._mini_size // 2
        on_left = cx < sw // 2
        x = 0 if on_left else sw - pw

        self._root.geometry(f"{pw}x{sh}+{x}+0")
        self._canvas.delete("all")
        self._draw_expanded_panel(pw, sh, on_left)
        self._apply_opacity(self.config.expanded_opacity)

    # ── Capture + OCR + Translate ───────────────────────────────────

    def _capture_and_process(self) -> None:
        def _run() -> None:
            assert self._root is not None
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.save(buf, format="BMP")
                self._cached_screenshot = buf.getvalue()
                text = self._capture.capture_and_ocr(self._source_lang)
                translated = translate_text(text, source=self._source_lang, target=self._target_lang)
                self._original_text = text
                self._translated_text = translated
                self._root.after(0, self._refresh_panel_text)
            except Exception as exc:
                self._root.after(0, lambda: setattr(self, "_original_text", f"[Error: {exc}]"))
        threading.Thread(target=_run, daemon=True).start()

    def _re_process_with_langs(self, src_tag: str, tgt_tag: str) -> None:
        if self._cached_screenshot is None:
            self._source_lang, self._target_lang = src_tag, tgt_tag
            self._capture_and_process()
            return
        self._update_text_displays(
            f"[OCR running for {LANGUAGES.get(src_tag, src_tag)}...]",
            f"[Translating to {LANGUAGES.get(tgt_tag, tgt_tag)}...]",
        )
        def _run() -> None:
            assert self._root is not None
            try:
                from PIL import Image as PILImage
                img = PILImage.open(io.BytesIO(self._cached_screenshot))
                sb = self._capture._pil_to_software_bitmap(img)
                eng = self._capture._ensure_engine(src_tag)
                rop = eng.recognize_async(sb)
                rop.wait(15000)
                r = rop.get_results()
                text = "\n".join([ln.text for ln in r.lines]).strip()
                t = translate_text(text, source=src_tag, target=tgt_tag)
                self._capture._last_text_by_lang[src_tag] = text
                self._original_text = text
                self._translated_text = t
                self._source_lang, self._target_lang = src_tag, tgt_tag
                self._root.after(0, self._refresh_panel_text)
            except Exception as exc:
                self._root.after(0, lambda: self._update_text_displays(self._original_text, f"[Error: {exc}]"))
        threading.Thread(target=_run, daemon=True).start()

    def _update_text_displays(self, orig: str, trans: str) -> None:
        for w, t in ((self._orig_widget, orig), (self._trans_widget, trans)):
            if w is not None:
                w.config(state="normal")
                w.delete("1.0", "end")
                w.insert("1.0", t)
                w.config(state="disabled")

    def _refresh_panel_text(self) -> None:
        self._update_text_displays(self._original_text, self._translated_text)

    # ── Drawing – Mini ──────────────────────────────────────────────

    def _draw_mini_circle(self, size: int) -> None:
        assert self._canvas is not None
        bg = self.config.bg_color

        # Draw a dark background rectangle covering the whole mini window,
        # then draw the circle on top.  The canvas bg stays dark at all times.
        self._canvas.create_rectangle(0, 0, size, size, fill=bg, outline="")

        cx = cy = size // 2
        r = (size // 2) - 2
        self._mini_circle_center = (cx, cy)
        self._mini_circle_radius = r

        self._canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.config.accent_color, outline=self.config.accent_color, width=0)
        self._canvas.create_text(cx, cy, text="ST", fill=self.config.fg_color, font=(self.config.font_family, int(size * 0.35), "bold"))
        self._canvas.bind("<Button-1>", self._on_mini_press)
        self._canvas.bind("<Button-3>", lambda e: self.stop())

    # ── Click / drag ────────────────────────────────────────────────

    def _on_mini_press(self, event: tk.Event) -> None:
        cx, cy = self._mini_circle_center
        dx, dy = event.x - cx, event.y - cy
        if dx * dx + dy * dy > self._mini_circle_radius * self._mini_circle_radius:
            return
        self._dragging = False
        self._drag_start_x, self._drag_start_y = event.x_root, event.y_root
        self._drag_win_x, self._drag_win_y = self._mini_x, self._mini_y
        self._canvas.bind("<B1-Motion>", self._on_mini_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_mini_release)

    def _on_mini_drag(self, event: tk.Event) -> None:
        self._dragging = True
        self._mini_x = max(0, self._drag_win_x + event.x_root - self._drag_start_x)
        self._mini_y = max(0, self._drag_win_y + event.y_root - self._drag_start_y)
        assert self._root is not None
        self._root.geometry(f"+{self._mini_x}+{self._mini_y}")

    def _on_mini_release(self, event: tk.Event) -> None:
        self._canvas.unbind("<B1-Motion>")
        self._canvas.unbind("<ButtonRelease-1>")
        if self._dragging:
            self._dragging = False
            return
        assert self._root is not None
        if self._click_timer_id is not None:
            self._root.after_cancel(self._click_timer_id)
            self._click_timer_id = None
            self._on_double_click()
        else:
            self._click_timer_id = self._root.after(DOUBLE_CLICK_INTERVAL, self._on_single_click)

    def _on_single_click(self) -> None:
        self._click_timer_id = None
        self._capture_and_process()

    def _on_double_click(self) -> None:
        self._show_expanded()

    # ── Drawing – Expanded panel ────────────────────────────────────

    def _draw_expanded_panel(self, w: int, h: int, on_left: bool) -> None:
        assert self._canvas is not None and self._root is not None
        bg = self.config.bg_color
        fg = self.config.fg_color
        accent = self.config.accent_color
        font = self.config.font_family

        for wgt in (self._from_combo, self._to_combo, self._orig_widget, self._trans_widget):
            if wgt is not None:
                try: wgt.destroy()
                except Exception: pass
        self._from_combo = self._to_combo = self._orig_widget = self._trans_widget = None

        header_h = 70
        display_orig = self._original_text or "No text captured yet."
        display_trans = self._translated_text or ""

        # Full panel background
        self._canvas.create_rectangle(0, 0, w, h, fill=bg, outline="")
        self._canvas.create_rectangle(0, 0, w, header_h, fill=bg, outline="")

        # Title
        tx, anc = (12, "w") if on_left else (w - 12, "e")
        self._canvas.create_text(tx, 14, text="screenTranslator", fill=fg, font=(font, 12, "bold"), anchor=anc)

        # Minimise
        br = 14
        bcx = w - 14 - 14 if on_left else 14 + 14
        self._canvas.create_oval(bcx - br, 28 - br, bcx + br, 28 + br, fill=accent, outline="", tags="minimise_btn")
        self._canvas.create_line(bcx - 6, 28, bcx + 6, 28, fill=fg, width=2, tags="minimise_icon")

        # Combos
        cy, cw, ch = header_h - 30, 90, 22
        total = cw * 2 + 12 + 80
        rx = (w - total) // 2
        self._canvas.create_text(rx + 4, header_h - 24, text="From:", fill=fg, font=(font, 10), anchor="w")
        self._from_var = tk.StringVar(value=LANGUAGES.get(self._source_lang, self._source_lang))
        fc = ttk.Combobox(self._canvas, textvariable=self._from_var, values=list(LANGUAGES.values()), state="readonly", font=(font, 9), width=8)
        fc.place(x=rx + 42, y=cy, width=cw, height=ch)
        self._from_combo = fc

        to_x = rx + 42 + cw + 12
        self._canvas.create_text(to_x + 4, header_h - 24, text="To:", fill=fg, font=(font, 10), anchor="w")
        self._to_var = tk.StringVar(value=LANGUAGES.get(self._target_lang, self._target_lang))
        tc = ttk.Combobox(self._canvas, textvariable=self._to_var, values=list(LANGUAGES.values()), state="readonly", font=(font, 9), width=8)
        tc.place(x=to_x + 28, y=cy, width=cw, height=ch)
        self._to_combo = tc

        def _lc(*a: object) -> None:
            s, t = self._source_lang, self._target_lang
            for tag, disp in LANGUAGES.items():
                if disp == self._from_var.get(): s = tag
                if disp == self._to_var.get(): t = tag
            if s != self._source_lang or t != self._target_lang:
                self._re_process_with_langs(s, t)
        fc.bind("<<ComboboxSelected>>", _lc)
        tc.bind("<<ComboboxSelected>>", _lc)

        # Split view
        sy = header_h + (h - header_h) // 2
        oh = sy - header_h - 24
        self._canvas.create_text(w // 2, header_h + 4, text="[ Original ]", fill=accent, font=(font, 9, "bold"), anchor="n")
        self._orig_widget = tk.Text(self._canvas, wrap="word", font=(font, self.config.font_size), bg=bg, fg=fg, insertbackground=fg, highlightthickness=0, borderwidth=0, relief="flat", padx=8, pady=2)
        self._orig_widget.insert("1.0", display_orig)
        self._orig_widget.config(state="disabled")
        self._canvas.create_window(w // 2, header_h + 18, window=self._orig_widget, anchor="n", width=w - 4, height=oh - 6)

        self._canvas.create_line(8, sy - 16, w - 8, sy - 16, fill=accent, width=1)
        th_ = h - sy + 16
        self._canvas.create_text(w // 2, sy - 10, text="[ Translation ]", fill=accent, font=(font, 9, "bold"), anchor="n")
        self._trans_widget = tk.Text(self._canvas, wrap="word", font=(font, self.config.font_size), bg=bg, fg=fg, insertbackground=fg, highlightthickness=0, borderwidth=0, relief="flat", padx=8, pady=2)
        self._trans_widget.insert("1.0", display_trans)
        self._trans_widget.config(state="disabled")
        self._canvas.create_window(w // 2, sy, window=self._trans_widget, anchor="n", width=w - 4, height=th_ - 10)

        self._canvas.tag_bind("minimise_btn", "<Button-1>", lambda e: self._root and self._root.after(50, self._show_mini))
        self._canvas.tag_bind("minimise_icon", "<Button-1>", lambda e: self._root and self._root.after(50, self._show_mini))

    # ── Public API ──────────────────────────────────────────────────

    def run(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(bg=self.config.bg_color)
        self._root.attributes("-alpha", self.config.mini_opacity)
        hwnd = self._hwnd()
        windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED)
        self._canvas = tk.Canvas(self._root, highlightthickness=0, borderwidth=0, bg=self.config.bg_color)
        self._canvas.pack(fill="both", expand=True)
        self._show_mini()
        self._make_tool_window()
        self._root.after(10, self._set_topmost)
        self._root.deiconify()
        self._root.bind("<Escape>", lambda e: self.stop())
        self._root.bind("<Control-q>", lambda e: self.stop())
        self._root.bind("<Control-c>", lambda e: self.stop())
        self._root.mainloop()

    def stop(self) -> None:
        if self._root is not None:
            self._root.after(0, self._root.destroy)