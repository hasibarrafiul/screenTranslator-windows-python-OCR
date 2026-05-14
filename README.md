# screenTranslator – Screen OCR & Translation Overlay

A lightweight Windows overlay that captures your screen, runs OCR, and
translates the text using **Windows native WinRT OCR** + **Google Translate**.

## Behaviour

1. **Mini mode** – a small circular "ST" button that you can **drag** by
   holding the left mouse button. Drops wherever you release it.
2. **Single click** (no drag) → captures the screen, runs OCR with the
   **source language**, translates to the **target language**, and stores
   the result silently.
3. **Double click** → opens the setting panel with languege selection, save translation to text and exit button **original text**
   (top) and its **translation** (bottom).
4. **Expanded panel** – covers ≈30 % of screen width and full height.
   Opens on the **same side** the button sits (left or right based on
   screen centre). Contains:
   - **From** / **To** language dropdowns (English / 日本語)
   - Original text (top half) and translation (bottom half)
   - Minimise button to collapse back to the mini circle
5. Switching the language in the dropdown re‑runs OCR on the **cached
   screenshot** and re-translates – no need to capture again.
## Project Structure

```
screenTranslator/
├── main.py               # Entry point
├── overlay/
│   ├── __init__.py       # Package metadata
│   ├── capture.py        # Screen capture + WinRT OCR engine
│   ├── config.py         # Configuration (dataclass + JSON persistence)
│   ├── translation.py    # Google Translate via deep-translator
│   └── window.py         # Canvas-based overlay (mini & expanded states)
├── requirements.txt
└── README.md
```

## Quick Start

```bash
python main.py
```

## Configuration

On first run the app creates `overlay_config.json` in the project root.

| Key                   | Default   | Description                                     |
|-----------------------|-----------|-------------------------------------------------|
| `mini_size`           | `50`      | Diameter of the circular button (px)            |
| `mini_x`              | `10`      | Distance from left edge (px)                    |
| `mini_y`              | `10`      | Distance from top edge (px)                     |
| `mini_opacity`        | `0.90`    | Mini circle opacity (0.0 – 1.0)                |
| `expanded_width_pct`  | `0.30`    | Panel width as fraction of screen width         |
| `expanded_opacity`    | `0.92`    | Expanded panel opacity (0.0 – 1.0)             |
| `font_family`         | `Segoe UI`| Text font                                       |
| `font_size`           | `13`      | Text font size                                  |
| `bg_color`            | `#1e1e1e` | Background colour                               |
| `fg_color`            | `#ffffff` | Foreground (text) colour                        |
| `accent_color`        | `#0078d4` | Accent colour (circle fill, minimise button)    |

## Features

- **Always-on-top** – never hidden behind other windows.
- **No title bar / borders** – pure overlay look.
- **Per-pixel transparency** – only the circle/panel is visible.
- **Hidden from taskbar & alt‑tab** – uses `WS_EX_TOOLWINDOW`.
- **Language selectors** – choose source (OCR) and target (translation) language
- **Original + Translation** split view in the expanded panel
- **Cached screenshot** – switching languages re-OCR's the same image, no re-capture needed

## Dependencies

### Python packages (install via `pip install -r requirements.txt`)

| Package | Purpose |
|---|---|
| `Pillow` | Screen capture (`ImageGrab`) + image processing |
| `deep-translator` | Google Translate integration |
| `winrt-Windows.Media.Ocr` | Native Windows OCR (WinRT) |
| `winrt-Windows.Globalization` | Language detection for OCR |
| `winrt-Windows.Graphics.Imaging` | Image encoding/decoding for WinRT |
| `winrt-Windows.Storage.Streams` | In-memory stream for WinRT |

### Windows requirement

Windows 10/11 build 17763+ (October 2018 Update) — this is where
`Windows.Media.Ocr` was introduced. No separate OCR engine binary
needs to be installed; it uses the built‑in Windows OCR capabilities.
