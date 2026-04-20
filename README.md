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

Copy and edit the config file:

```bash
cp config.example.yaml config.yaml
```

Set your Gemini API key in `config.yaml`:

```yaml
api:
  gemini_api_key: "YOUR_API_KEY"
```

**Run**

```bash
python main.py
```

Place input files in the configured input directory. The pipeline will process all PDF and DOCX files found there.

---

## Project Structure

```
journal-extraction-suite/
├── main.py                  # Entry point
├── config.yaml              # Runtime configuration
├── core/                    # Shared utilities, logging, config loader
├── extractors/              # PDF and DOCX extraction modules
├── processors/              # Deduplication, cleaning, image processing
├── generators/              # Excel, HTML, PDF, DOCX output generators
├── pipeline/                # Stage orchestration and checkpoint management
├── engines/
│   ├── mineru/              # Alternative engine: MinerU-based extraction
│   └── babeldoc/            # Alternative engine: BabelDoc-based extraction
└── docs/                    # Full documentation
```

The root pipeline is the default engine. MinerU and BabelDoc are drop-in alternatives under `engines/`.

---

## Configuration

Key parameters in `config.yaml`:

| Parameter | Default | Description |
|---|---|---|
| `api.gemini_api_key` | — | Gemini API key (required) |
| `processing.concurrent_files` | `20` | Parallel file workers |
| `processing.concurrent_batches` | `100` | Parallel translation batches |
| `image.mode` | `rule` | Image processing mode: `rule` or `vision` |
| `image.min_size_kb` | `10` | Minimum image size to extract |
| `image.min_width` | `400` | Minimum image width (px) |
| `image.min_height` | `300` | Minimum image height (px) |
| `output.formats` | `[excel, html, pdf, docx]` | Output formats to generate |
| `output.dir` | `./output` | Output directory |
| `pipeline.checkpoint_dir` | `./checkpoints` | Checkpoint storage path |

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full parameter reference.

---

## Output Structure

```
output/
├── excel/
│   └── articles.xlsx
├── html/
│   ├── index.html
│   └── images/
├── pdf/
│   └── output.pdf
└── docx/
    └── output.docx
```

Checkpoints are stored separately under `checkpoints/` and allow resuming from any of the 11 pipeline stages.

---

## Recovery Tools

```bash
# Resume from JSON cache after interruption
python recover_progress_from_json.py

# Check and fix leaked translation placeholders
python check_and_fix_leaked_placeholders.py
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
