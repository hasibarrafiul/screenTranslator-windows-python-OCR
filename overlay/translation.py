"""
Translation module using deep-translator.
"""
from __future__ import annotations

from deep_translator import GoogleTranslator


# Cache for translation results: (source_text, source_lang, target_lang) -> translated_text
_translation_cache: dict[tuple[str, str, str], str] = {}


def translate_text(text: str, source: str, target: str) -> str:
    """
    Translate `text` from `source` to `target` using Google Translate.
    Language codes should be short codes like 'en', 'ja'.
    """
    if not text.strip():
        return ""

    cache_key = (text, source, target)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    try:
        translator = GoogleTranslator(source=source, target=target)
        result = translator.translate(text)
        _translation_cache[cache_key] = result
        return result
    except Exception as exc:
        return f"[Translation Error: {exc}]"