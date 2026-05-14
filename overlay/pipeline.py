"""
Capture → OCR → Translate pipeline.
Manages background threads and the cached screenshot for language switching.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from overlay.capture import ScreenCapture, LANGUAGES, OcrBox
from overlay.translation import translate_text

if TYPE_CHECKING:
    import tkinter as tk


@dataclass
class PositionedLine:
    """A single line of translated text with original bounding-box info."""
    x: float
    y: float
    width: float
    height: float
    text: str  # translated text


@dataclass
class FullResult:
    """Holds the complete capture → OCR → translate output."""
    original_text: str = ""
    translated_text: str = ""
    lines: list[PositionedLine] = field(default_factory=list)


def _append_unique_lines(file_path: str, new_text: str) -> None:
    """Append lines from *new_text* to *file_path* if not already present."""
    if not new_text.strip():
        return
    existing = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                existing.add(line.rstrip("\n").rstrip("\r"))
    except FileNotFoundError:
        pass
    with open(file_path, "a", encoding="utf-8") as f:
        for line in new_text.split("\n"):
            line = line.strip()
            if line and line not in existing:
                f.write(line + "\n")
                existing.add(line)


class Pipeline:
    """Handles screen capture, OCR, and translation in background threads."""

    def __init__(self) -> None:
        self._capture = ScreenCapture()
        self._result = FullResult()
        self.source_lang: str = "ja"
        self.target_lang: str = "en"
        self._cached_screenshot: Optional[bytes] = None

    @property
    def original_text(self) -> str:
        return self._result.original_text

    @property
    def translated_text(self) -> str:
        return self._result.translated_text

    @property
    def lines(self) -> list[PositionedLine]:
        return self._result.lines

    def capture_and_process(self, root: tk.Tk, on_done: Callable,
                             save_cfg: tuple[bool, str] = (False, "")) -> None:
        """Capture screen, OCR with source lang, translate to target lang.

        *save_cfg* is a tuple of (save_enabled, file_path) to optionally
        persist unique translated lines to a text file.
        """
        def _run() -> None:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.save(buf, format="BMP")
                self._cached_screenshot = buf.getvalue()

                ocr_data = self._capture.capture_ocr_structured(self.source_lang)
                self._result.original_text = ocr_data.plain_text()
                lines_text = [box.text for box in ocr_data.lines]

                combined_text = "\n".join(lines_text)
                if combined_text.strip():
                    translated = translate_text(combined_text, source=self.source_lang, target=self.target_lang)
                    self._result.translated_text = translated
                else:
                    translated = ""
                    self._result.translated_text = ""

                translated_lines = translated.split("\n") if translated else []
                result_lines = []
                for idx, box in enumerate(ocr_data.lines):
                    trans_text = translated_lines[idx] if idx < len(translated_lines) else box.text
                    result_lines.append(PositionedLine(
                        x=box.x, y=box.y, width=box.width, height=box.height, text=trans_text,
                    ))
                self._result.lines = result_lines

                # Save to file if enabled (deduplicated)
                save_enabled, file_path = save_cfg
                if save_enabled and file_path and translated.strip():
                    _append_unique_lines(file_path, translated)

                root.after(0, on_done)
            except Exception as exc:
                self._result.original_text = f"[Error: {exc}]"
                root.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def re_process_with_langs(self, src_tag: str, tgt_tag: str,
                              root: tk.Tk,
                              status_cb: Callable, update_cb: Callable) -> None:
        """Re-OCR the cached screenshot with new languages."""
        if self._cached_screenshot is None:
            self.source_lang = src_tag
            self.target_lang = tgt_tag
            self.capture_and_process(root, update_cb)
            return

        def _run() -> None:
            try:
                from PIL import Image as PILImage
                img = PILImage.open(io.BytesIO(self._cached_screenshot))
                sb = self._capture._pil_to_software_bitmap(img)
                eng = self._capture._ensure_engine(src_tag)
                rop = eng.recognize_async(sb)
                rop.wait(15000)
                result = rop.get_results()
                lines_text = [line.text for line in result.lines]
                text = "\n".join(lines_text).strip()

                self.source_lang = src_tag
                self.target_lang = tgt_tag
                self._result.original_text = text
                if text.strip():
                    translated = translate_text(text, source=src_tag, target=tgt_tag)
                    self._result.translated_text = translated

                    translated_lines = translated.split("\n")
                    boxes = []
                    for line in result.lines:
                        r = line.words[0].bounding_rect
                        min_x, min_y = r.x, r.y
                        max_x, max_y = r.x + r.width, r.y + r.height
                        for w in line.words[1:]:
                            wr = w.bounding_rect
                            min_x = min(min_x, wr.x)
                            min_y = min(min_y, wr.y)
                            max_x = max(max_x, wr.x + wr.width)
                            max_y = max(max_y, wr.y + wr.height)
                        boxes.append(OcrBox(x=min_x, y=min_y,
                                            width=max_x - min_x, height=max_y - min_y, text=line.text))

                    result_lines = []
                    for idx, box in enumerate(boxes):
                        trans_text = translated_lines[idx] if idx < len(translated_lines) else box.text
                        result_lines.append(PositionedLine(
                            x=box.x, y=box.y, width=box.width, height=box.height, text=trans_text,
                        ))
                    self._result.lines = result_lines
                else:
                    self._result.translated_text = ""
                    self._result.lines = []
                root.after(0, update_cb)
            except Exception as exc:
                self._result.translated_text = f"[Error: {exc}]"
                root.after(0, update_cb)
        threading.Thread(target=_run, daemon=True).start()