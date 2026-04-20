[中文文档](README_ZH.md)

# Journal Extraction Suite

AI-powered pipeline for extracting, translating, and formatting academic journal articles from PDF and DOCX files.

<div align="center">

[![Version](https://img.shields.io/badge/version-2.12.2-blue.svg)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

</div>

---

## Features

**Processing**
- Supports PDF (page-by-page) and DOCX (full-document) input formats
- 11-stage checkpoint/resume system — safe to interrupt and restart
- 20 concurrent files, 100 concurrent translation batches
- 80–120 PDFs/hour throughput in production

**Extraction & Translation**
- Distinguishes journal articles from academic papers (avoids splitting paper sections as articles)
- 99% deduplication accuracy via hybrid similarity algorithm
- EN→ZH translation with terminology glossary support and quality validation
- Auto-retry on translation output matching source text

**Image Processing** (dual mode)
- Rule-based mode: zero API cost, 3–5x faster, proximity/position matching
- Vision API mode: Gemini multimodal descriptions, 75–85% article alignment accuracy
- Four-layer validation: format → existence → uniqueness → page range
- Cover image selection via AI or quality scoring

**Output**
- Excel: structured article metadata
- HTML: responsive layout with TOC, cover images, and inline article images
- PDF: high-quality render with bookmarks
- DOCX: formatted document output

---

## Quick Start

**Install dependencies**

```bash
pip install -r requirements.txt
```

**Configure API keys**

Edit `config.py` and set your Gemini API keys:

```python
# PDF extraction
PDF_API_KEY = "your-gemini-api-key"
PDF_API_BASE_URL = "your-api-url"
PDF_API_MODEL = "gemini-2.5-flash"

# Translation
TRANSLATION_API_KEY = "your-gemini-api-key"
TRANSLATION_API_BASE_URL = "your-api-url"
TRANSLATION_API_MODEL = "gemini-2.5-flash"

# HTML generation
HTML_API_KEY = "your-gemini-api-key"
HTML_API_BASE_URL = "your-api-url"
HTML_API_MODEL = "gemini-2.5-flash"
```

**Run**

```bash
python main.py
```

Place input files in `input/`. The interactive menu will guide you through file selection, translation options, and output format choices.

---

## Project Structure

```
journal-extraction-suite/
├── main.py                  # Entry point
├── config.py                # All configuration constants and API settings
├── core/                    # Logging, PDF utilities, JSON parsing
├── extractors/              # PDF and DOCX extraction modules
├── processors/              # Image processing, Vision API, translation
├── generators/              # HTML, PDF, DOCX, Excel output generators
├── pipeline/                # Stage orchestration and checkpoint management
├── engines/
│   ├── mineru/              # Alternative engine: MinerU-based extraction
│   └── babeldoc/            # Alternative engine: BabelDoc-based extraction
└── docs/                    # Full documentation
```

The root pipeline is the default engine. MinerU and BabelDoc are self-contained alternatives under `engines/`.

---

## Configuration

All configuration lives in `config.py`. Key parameters:

| Parameter | Default | Description |
|---|---|---|
| `PDF_API_KEY` | — | Gemini API key for extraction (required) |
| `MAX_CONCURRENT_PDF_FILES` | `20` | Parallel file workers |
| `MAX_WORKERS` | `100` | Parallel batch workers |
| `PAGES_PER_BATCH` | `6` | PDF pages per extraction batch |
| `ENABLE_VISION_API` | `False` | Use Vision API for image processing |
| `IMAGE_MIN_FILE_SIZE` | `10240` | Minimum image size to extract (bytes) |
| `IMAGE_MIN_WIDTH` | `400` | Minimum image width (px) |
| `IMAGE_MIN_HEIGHT` | `300` | Minimum image height (px) |

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full parameter reference.

---

## Output Structure

```
output/
├── excel/          # Excel files (original + translated)
├── html/           # HTML files with TOC, cover images, article images
├── pdf/            # PDF files
├── docx/           # DOCX files
├── image/          # Extracted images per PDF
└── json/           # Cached extraction data (used for resume)
```

---

## Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and execution flow |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Full configuration reference |
| [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Modular development guide |
| [IMAGE_PROCESSING.md](docs/IMAGE_PROCESSING.md) | Image extraction, cleaning, and matching |
| [VISION_API.md](docs/VISION_API.md) | Vision API integration and best practices |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [CHANGELOG.md](docs/CHANGELOG.md) | Version history |

---

## License

MIT — see [LICENSE](LICENSE) for details.
