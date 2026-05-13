"""
screenTranslator – Windows Overlay Application
Entry point.
"""
from __future__ import annotations

import sys
import signal

from overlay.window import OverlayWindow


def main() -> None:
    """Launch the overlay window."""
    overlay = OverlayWindow()

    # Handle Ctrl+C gracefully in case it's run from a terminal
    def _handle_signal(sig, frame):
        overlay.stop()

    signal.signal(signal.SIGINT, _handle_signal)

    try:
        overlay.run()
    except KeyboardInterrupt:
        overlay.stop()


if __name__ == "__main__":
    main()