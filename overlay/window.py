"""
Overlay window orchestrator.
Slim coordinator that uses win32, ui, and pipeline modules.

Three states:
  * Mini         – draggable circular button
  * Settings     – side panel with language selectors (double click)
  * Fullscreen   – full-screen overlay showing positioned translation (single click)
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from overlay.config import OverlayConfig
from overlay.pipeline import Pipeline
from overlay import win32
from overlay import ui


DOUBLE_CLICK_INTERVAL = 300


class OverlayWindow:
    def __init__(self, config: Optional[OverlayConfig] = None) -> None:
        self.config = config or OverlayConfig.load()
        self._pipeline = Pipeline()

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None

        # Mini state
        self._mini_x = self.config.mini_x
        self._mini_y = self.config.mini_y
        self._circle_cx = 0
        self._circle_cy = 0
        self._circle_r = 0

        # Drag
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_win_x = 0
        self._drag_win_y = 0
        self._dragging = False

        # Click timer
        self._click_timer_id: Optional[str] = None

        # Expanded panel widget refs
        self._ow = None  # orig_widget
        self._tw = None  # trans_widget
        self._fc = None  # from_combo
        self._tc = None  # to_combo
        self._sc = None  # save_checkbutton
        self._pe = None  # path_entry
        self._pb = None  # path_browse_btn

    # ── State transitions ─────────────────────────────────────────────

    def _show_mini(self) -> None:
        assert self._root and self._canvas
        s = self.config.mini_size
        self._root.geometry(f"{s}x{s}+{self._mini_x}+{self._mini_y}")
        self._canvas.delete("all")
        cx, cy, r = ui.draw_mini_circle(self._canvas, s, self.config, self._on_mini_press)
        self._circle_cx, self._circle_cy, self._circle_r = cx, cy, r
        win32.apply_opacity(self._root, self.config.mini_opacity)

    def _show_expanded(self) -> None:
        """30 % side panel with original + translation and language selectors."""
        assert self._root and self._canvas
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        pw = int(sw * self.config.expanded_width_pct)
        cx = self._mini_x + self.config.mini_size // 2
        on_left = cx < sw // 2
        x = 0 if on_left else sw - pw

        self._root.geometry(f"{pw}x{sh}+{x}+0")

        ui.destroy_panel_widgets(self._fc, self._tc, self._ow, self._tw)
        self._canvas.delete("all")

        def _lc(src: str, tgt: str) -> None:
            self._pipeline.re_process_with_langs(
                src, tgt, self._root,
                self._update_text_displays,
                self._refresh_panel_text,
            )

        def _cc(key: str, value) -> None:
            """Persist config changes from the settings panel."""
            setattr(self.config, key, value)
            self.config.save()

        refs = ui.draw_settings_panel(
            self._canvas, pw, sh, on_left, self.config,
            self._pipeline.source_lang,
            self._pipeline.target_lang,
            on_lang_change=_lc,
            on_minimise=self._show_mini,
            on_config_change=_cc,
        )
        self._fc = refs["from_combo"]
        self._tc = refs["to_combo"]
        self._sc = refs["save_check"]
        self._pe = refs["path_entry"]
        self._pb = refs["browse_btn"]

        win32.apply_opacity(self._root, self.config.expanded_opacity)

    def _show_fullscreen_translation(self) -> None:
        """Full-screen overlay showing only the translated text."""
        assert self._root and self._canvas
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()

        # Destroy any lingering panel widgets (combos, check, entry, buttons) first
        ui.destroy_panel_widgets(self._fc, self._tc, self._ow, self._tw,
                                 self._sc, self._pe, self._pb)
        self._fc = self._tc = self._ow = self._tw = None
        self._sc = self._pe = self._pb = None

        self._root.geometry(f"{sw}x{sh}+0+0")
        self._canvas.delete("all")

        ui.draw_fullscreen_overlay(
            self._canvas, sw, sh, self.config,
            self._pipeline.lines,
            on_dismiss=self._show_mini,
        )

        win32.apply_opacity(self._root, self.config.expanded_opacity)

    # ── Text helpers ──────────────────────────────────────────────────

    def _update_text_displays(self, orig: str, trans: str) -> None:
        for w, t in ((self._ow, orig), (self._tw, trans)):
            if w is not None:
                w.config(state="normal")
                w.delete("1.0", "end")
                w.insert("1.0", t)
                w.config(state="disabled")

    def _refresh_panel_text(self) -> None:
        self._update_text_displays(self._pipeline.original_text, self._pipeline.translated_text)

    # ── Mini button events ────────────────────────────────────────────

    def _on_mini_press(self, event: tk.Event) -> None:
        dx, dy = event.x - self._circle_cx, event.y - self._circle_cy
        if dx * dx + dy * dy > self._circle_r * self._circle_r:
            return
        self._dragging = False
        self._drag_start_x, self._drag_start_y = event.x_root, event.y_root
        self._drag_win_x, self._drag_win_y = self._mini_x, self._mini_y
        assert self._canvas
        self._canvas.bind("<B1-Motion>", self._on_mini_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_mini_release)

    def _on_mini_drag(self, event: tk.Event) -> None:
        self._dragging = True
        self._mini_x = max(0, self._drag_win_x + event.x_root - self._drag_start_x)
        self._mini_y = max(0, self._drag_win_y + event.y_root - self._drag_start_y)
        assert self._root
        self._root.geometry(f"+{self._mini_x}+{self._mini_y}")

    def _on_mini_release(self, event: tk.Event) -> None:
        assert self._canvas
        self._canvas.unbind("<B1-Motion>")
        self._canvas.unbind("<ButtonRelease-1>")
        if self._dragging:
            self._dragging = False
            return
        assert self._root
        if self._click_timer_id is not None:
            self._root.after_cancel(self._click_timer_id)
            self._click_timer_id = None
            self._on_double_click()
        else:
            self._click_timer_id = self._root.after(DOUBLE_CLICK_INTERVAL, self._on_single_click)

    def _on_single_click(self) -> None:
        """Single click: capture + OCR + translate, then show full-screen translation."""
        self._click_timer_id = None
        # Capture + translate then show fullscreen overlay
        self._pipeline.capture_and_process(
            self._root,
            on_done=self._show_fullscreen_translation,
            save_cfg=(self.config.save_translations, self.config.save_path),
        )

    def _on_double_click(self) -> None:
        """Double click: open the expanded side panel."""
        self._show_expanded()

    # ── Public API ────────────────────────────────────────────────────

    def run(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(bg=self.config.bg_color)
        self._root.attributes("-alpha", self.config.mini_opacity)
        win32.enable_layered(self._root)

        self._canvas = tk.Canvas(self._root, highlightthickness=0, borderwidth=0, bg=self.config.bg_color)
        self._canvas.pack(fill="both", expand=True)

        self._show_mini()
        win32.hide_from_taskbar(self._root)
        self._root.after(10, lambda: win32.set_topmost(self._root))
        self._root.deiconify()
        self._root.mainloop()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)