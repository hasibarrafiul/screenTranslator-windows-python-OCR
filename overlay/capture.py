"""
Screen capture and OCR module using native Windows OCR (WinRT).
No external OCR engines required – uses the built-in Windows.Media.Ocr API.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageGrab

import winrt.windows.globalization as globalization
import winrt.windows.graphics.imaging as imaging
import winrt.windows.media.ocr as ocr
import winrt.windows.storage.streams as streams

from winrt.windows.foundation import Rect as WinRect


LANGUAGES: dict[str, str] = {
    "en": "English",
    "ja": "日本語",
}


@dataclass
class OcrBox:
    """Bounding box + text for one recognised line."""
    x: float
    y: float
    width: float
    height: float
    text: str


@dataclass
class OcrResult:
    """Full OCR result with structured bounding boxes."""
    lines: list[OcrBox] = field(default_factory=list)

    def plain_text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)


class ScreenCapture:
    """Captures the primary monitor and runs native Windows OCR."""

    def __init__(self) -> None:
        self._last_text: str = ""
        self._last_ocr_result: OcrResult = OcrResult()
        self._last_text_by_lang: dict[str, str] = {}
        self._engines: dict[str, ocr.OcrEngine] = {}

    @property
    def last_text(self) -> str:
        return self._last_text

    def last_result_for(self, lang_tag: str) -> OcrResult:
        return self._last_text_by_lang.get(lang_tag, OcrResult())

    def last_text_for(self, lang_tag: str) -> str:
        return self._last_text_by_lang.get(lang_tag, OcrResult()).plain_text()

    def _ensure_engine(self, lang_tag: str) -> ocr.OcrEngine:
        if lang_tag not in self._engines:
            lang = globalization.Language(lang_tag)
            engine = ocr.OcrEngine.try_create_from_language(lang)
            if engine is None:
                raise RuntimeError(
                    f"Windows OCR engine not available for language '{lang_tag}'"
                )
            self._engines[lang_tag] = engine
        return self._engines[lang_tag]

    def _pil_to_software_bitmap(self, img: Image.Image) -> imaging.SoftwareBitmap:
        """Convert a PIL Image to a WinRT SoftwareBitmap via in-memory BMP."""
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        data = buf.getvalue()

        ras = streams.InMemoryRandomAccessStream()
        ras.size = len(data)

        writer = streams.DataWriter(ras)
        writer.write_bytes(data)
        writer.store_async().wait(5000)

        decoder_op = imaging.BitmapDecoder.create_async(ras)
        decoder_op.wait(5000)
        decoder: imaging.BitmapDecoder = decoder_op.get_results()

        sb_op = decoder.get_software_bitmap_async()
        sb_op.wait(5000)
        return sb_op.get_results()

    def _rect_to_box(self, r: WinRect) -> OcrBox:
        return OcrBox(x=r.x, y=r.y, width=r.width, height=r.height, text="")

    def capture_and_ocr(self, lang_tag: str = "en") -> str:
        """Legacy – returns plain text. Prefer capture_ocr_structured()."""
        result = self.capture_ocr_structured(lang_tag)
        return result.plain_text()

    def capture_ocr_structured(self, lang_tag: str = "en") -> OcrResult:
        """
        Capture the full primary monitor and run OCR.
        Returns structured OcrResult with bounding boxes.
        """
        img = ImageGrab.grab()
        software_bitmap = self._pil_to_software_bitmap(img)

        engine = self._ensure_engine(lang_tag)
        result_op = engine.recognize_async(software_bitmap)
        result_op.wait(15000)
        result: ocr.OcrResult = result_op.get_results()

        boxes = []
        for line in result.lines:
            r = line.words[0].bounding_rect if line.words else WinRect()
            # Merge word bboxes to get the line bbox
            min_x = r.x
            min_y = r.y
            max_x = r.x + r.width
            max_y = r.y + r.height
            for w in line.words[1:]:
                wr = w.bounding_rect
                min_x = min(min_x, wr.x)
                min_y = min(min_y, wr.y)
                max_x = max(max_x, wr.x + wr.width)
                max_y = max(max_y, wr.y + wr.height)
            boxes.append(OcrBox(x=min_x, y=min_y,
                                width=max_x - min_x, height=max_y - min_y,
                                text=line.text))

        ocr_result = OcrResult(lines=boxes)
        self._last_text = ocr_result.plain_text()
        self._last_ocr_result = ocr_result
        self._last_text_by_lang[lang_tag] = ocr_result
        return ocr_result