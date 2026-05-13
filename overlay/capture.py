"""
Screen capture and OCR module using native Windows OCR (WinRT).
No external OCR engines required – uses the built-in Windows.Media.Ocr API.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageGrab

import winrt.windows.globalization as globalization
import winrt.windows.graphics.imaging as imaging
import winrt.windows.media.ocr as ocr
import winrt.windows.storage.streams as streams


LANGUAGES: dict[str, str] = {
    "en": "English",
    "ja": "日本語",
}


class ScreenCapture:
    """Captures the primary monitor and runs native Windows OCR."""

    def __init__(self) -> None:
        self._last_text: str = ""
        self._last_text_by_lang: dict[str, str] = {}
        self._engines: dict[str, ocr.OcrEngine] = {}

    @property
    def last_text(self) -> str:
        return self._last_text

    def last_text_for(self, lang_tag: str) -> str:
        return self._last_text_by_lang.get(lang_tag, "")

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

    def capture_and_ocr(self, lang_tag: str = "en") -> str:
        """
        Capture the full primary monitor and run OCR for the given language.
        Returns the extracted text.
        """
        img = ImageGrab.grab()
        software_bitmap = self._pil_to_software_bitmap(img)

        engine = self._ensure_engine(lang_tag)
        result_op = engine.recognize_async(software_bitmap)
        result_op.wait(15000)
        result: ocr.OcrResult = result_op.get_results()

        lines = [line.text for line in result.lines]
        text = "\n".join(lines).strip()

        self._last_text = text
        self._last_text_by_lang[lang_tag] = text
        return text