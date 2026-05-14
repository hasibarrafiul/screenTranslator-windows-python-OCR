"""
Drawing functions for the overlay window states.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from overlay.capture import LANGUAGES

if TYPE_CHECKING:
    from overlay.config import OverlayConfig


def draw_mini_circle(canvas: tk.Canvas, size: int, cfg: OverlayConfig,
                     bind_handler: Callable) -> tuple[int, int, int]:
    """Draw the circular mini button. Returns (center_x, center_y, radius)."""
    bg = cfg.bg_color
    canvas.create_rectangle(0, 0, size, size, fill=bg, outline="")

    cx = cy = size // 2
    r = (size // 2) - 2

    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       fill=cfg.accent_color, outline=cfg.accent_color, width=0)
    canvas.create_text(cx, cy, text="ST",
                       fill=cfg.fg_color,
                       font=(cfg.font_family, int(size * 0.28), "bold"))
    canvas.bind("<Button-1>", bind_handler)
    return cx, cy, r


def destroy_panel_widgets(from_combo, to_combo, orig_widget, trans_widget):
    """Destroy all ttk/Text widgets from a previous panel draw."""
    for wgt in (from_combo, to_combo, orig_widget, trans_widget):
        if wgt is not None:
            try:
                wgt.destroy()
            except Exception:
                pass


def draw_settings_panel(canvas: tk.Canvas, w: int, h: int, on_left: bool,
                        cfg: OverlayConfig,
                        source_lang: str,
                        target_lang: str,
                        on_lang_change: Callable[[str, str], None],
                        on_minimise: Callable) -> dict:
    """
    Draw the settings panel on *canvas* (size w×h) with language selectors only.

    Returns a dict with widget references: from_combo, to_combo
    """
    bg = cfg.bg_color
    fg = cfg.fg_color
    accent = cfg.accent_color
    font = cfg.font_family

    header_h = 70

    # Full background
    canvas.create_rectangle(0, 0, w, h, fill=bg, outline="")
    canvas.create_rectangle(0, 0, w, header_h, fill=bg, outline="")

    # ── Title ──
    tx, anc = (12, "w") if on_left else (w - 12, "e")
    canvas.create_text(tx, 14, text="Screen Translator by Fahim",
                       fill=fg, font=(font, 11, "bold"), anchor=anc)

    # ── Minimise button ──
    br = 14
    bcx = w - 14 - 14 if on_left else 14 + 14
    canvas.create_oval(bcx - br, 28 - br, bcx + br, 28 + br,
                       fill=accent, outline="", tags="minimise_btn")
    canvas.create_line(bcx - 6, 28, bcx + 6, 28,
                       fill=fg, width=2, tags="minimise_icon")

    # ── Language selectors ──
    cy, cw, ch = header_h - 30, 90, 22
    total = cw * 2 + 12 + 80
    rx = (w - total) // 2

    canvas.create_text(rx + 4, header_h - 24, text="From:",
                       fill=fg, font=(font, 10), anchor="w")
    from_var = tk.StringVar(value=LANGUAGES.get(source_lang, source_lang))
    fc = ttk.Combobox(canvas, textvariable=from_var,
                      values=list(LANGUAGES.values()),
                      state="readonly", font=(font, 9), width=8)
    fc.place(x=rx + 42, y=cy, width=cw, height=ch)

    to_x = rx + 42 + cw + 12
    canvas.create_text(to_x + 4, header_h - 24, text="To:",
                       fill=fg, font=(font, 10), anchor="w")
    to_var = tk.StringVar(value=LANGUAGES.get(target_lang, target_lang))
    tc = ttk.Combobox(canvas, textvariable=to_var,
                      values=list(LANGUAGES.values()),
                      state="readonly", font=(font, 9), width=8)
    tc.place(x=to_x + 28, y=cy, width=cw, height=ch)

    def _lc(*a):
        s, t = source_lang, target_lang
        for tag, disp in LANGUAGES.items():
            if disp == from_var.get():
                s = tag
            if disp == to_var.get():
                t = tag
        if s != source_lang or t != target_lang:
            on_lang_change(s, t)

    fc.bind("<<ComboboxSelected>>", _lc)
    tc.bind("<<ComboboxSelected>>", _lc)

    # ── Minimise binding ──
    canvas.tag_bind("minimise_btn", "<Button-1>",
                    lambda e: on_minimise())
    canvas.tag_bind("minimise_icon", "<Button-1>",
                    lambda e: on_minimise())

    return {
        "from_combo": fc,
        "to_combo": tc,
        "from_var": from_var,
        "to_var": to_var,
    }


def draw_fullscreen_overlay(canvas: tk.Canvas, w: int, h: int,
                             cfg: OverlayConfig,
                             lines: list,
                             on_dismiss: Callable) -> None:
    """
    Full-screen overlay drawing each translated line at its original
    bounding-box position.  *lines* should be a list of objects with
    .x, .y, .width, .height, .text attributes.

    Click anywhere or press Escape to dismiss back to mini mode.
    """
    bg = cfg.bg_color
    fg = cfg.fg_color
    accent = cfg.accent_color
    font = cfg.font_family

    canvas.create_rectangle(0, 0, w, h, fill=bg, outline="")

    # Close button in top-right corner
    br = 16
    bcx = w - 16 - 16
    bcy = 16 + br
    canvas.create_oval(bcx - br, bcy - br, bcx + br, bcy + br,
                       fill=accent, outline="", tags="fs_dismiss_btn")
    canvas.create_text(bcx, bcy, text="✕",
                       fill=fg, font=(font, 14, "bold"), tags="fs_dismiss_txt")

    # Draw each translated line at its original position
    for line in lines:
        if not line.text.strip():
            continue
        # Scale font size to box height (roughly 80% of the OCR text height)
        font_size = max(8, int(line.height * 0.75))
        canvas.create_text(
            line.x, line.y,
            text=line.text,
            fill=fg,
            font=(font, font_size),
            anchor="nw",  # top-left anchor matches original position
        )

    # Dismiss handlers
    def _dismiss(*a):
        on_dismiss()

    canvas.tag_bind("fs_dismiss_btn", "<Button-1>", _dismiss)
    canvas.tag_bind("fs_dismiss_txt", "<Button-1>", _dismiss)
    canvas.bind("<Button-1>", _dismiss)
    canvas.master.bind("<Escape>", lambda e: _dismiss())
