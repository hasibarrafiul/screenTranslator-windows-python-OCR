"""
Windows API helpers for window management.
"""
from __future__ import annotations

from ctypes import windll
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TOOLWINDOW = 0x80
LWA_ALPHA = 0x02
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0001
SWP_NOSIZE = 0x0002


def get_hwnd(root: tk.Tk) -> int:
    """Return the native HWND of a tkinter root window."""
    return windll.user32.GetParent(root.winfo_id())


def set_topmost(root: tk.Tk) -> None:
    """Keep the window above all others."""
    hwnd = get_hwnd(root)
    windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


def hide_from_taskbar(root: tk.Tk) -> None:
    """Remove the window from the taskbar and alt-tab switcher."""
    hwnd = get_hwnd(root)
    ex = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW)


def enable_layered(root: tk.Tk) -> None:
    """Enable WS_EX_LAYERED for per-pixel alpha support."""
    hwnd = get_hwnd(root)
    windll.user32.SetWindowLongW(
        hwnd,
        GWL_EXSTYLE,
        windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED,
    )


def apply_opacity(root: tk.Tk, value: float) -> None:
    """Set window opacity (0.0 – 1.0)."""
    alpha = int(max(0, min(255, value * 255)))
    windll.user32.SetLayeredWindowAttributes(get_hwnd(root), 0, alpha, LWA_ALPHA)