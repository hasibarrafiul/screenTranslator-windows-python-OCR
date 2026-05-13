"""
Capture → OCR → Translate pipeline.
Manages background threads and the cached screenshot for language switching.
"""
from __future__ import annotations

import io
import threading
from typing import TYPE_CHECKING, Optional

from overlay.capture import ScreenCapture, LANGUAGES
from overlay.translation import translate_text

if TYPE_CHECKING:
    import tkinter as tk


class Pipeline:
    """Handles screen capture, OCR, and translation in background threads."""

    def __init__(self) -> None:
        self._capture = ScreenCapture()
        self.original_text: str = ""
        self.translated_text: str = ""
        self.source_lang: str = "ja"
        self.target_lang: str = "en"
        self._cached_screenshot: Optional[bytes] = None

    def capture_and_process(self, root: tk.Tk, on_done=None) -> None:
        """Capture screen, OCR with source lang, translate to target lang."""
        def _run() -> None:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.save(buf, format="BMP")
                self._cached_screenshot = buf.getvalue()

                text = self._capture.capture_and_ocr(self.source_lang)
                translated = translate_text(text, source=self.source_lang, target=self.target_lang)
                self.original_text = text
                self.translated_text = translated
                if on_done:
                    root.after(0, on_done)
            except Exception as exc:
                err = f"[Error: {exc}]"
                root.after(0, lambda: setattr(self, "original_text", err))
        threading.Thread(target=_run, daemon=True).start()

    def re_process_with_langs(self, src_tag: str, tgt_tag: str,
                              root: tk.Tk,
                              status_cb, update_cb) -> None:
        """Re-OCR the cached screenshot with new languages."""
        if self._cached_screenshot is None:
            self.source_lang = src_tag
            self.target_lang = tgt_tag
            self.capture_and_process(root, update_cb)
            return

        status_cb(
            f"[OCR running for {LANGUAGES.get(src_tag, src_tag)}...]",
            f"[Translating to {LANGUAGES.get(tgt_tag, tgt_tag)}...]",
        )

        def _run() -> None:
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
                self.original_text = text
                self.translated_text = t
                self.source_lang = src_tag
                self.target_lang = tgt_tag
                root.after(0, update_cb)
            except Exception as exc:
                root.after(0, lambda: update_cb())
        threading.Thread(target=_run, daemon=True).start()