# System Architecture

## Directory Structure

```
root/
├── main.py                    # CLI entry point, MagazineWorkflow
├── config.py                  # All constants, UserConfig, prompts
├── core/
│   ├── logger.py              # Logging, HeartbeatMonitor, NetworkErrorHandler,
│   │                          # UnifiedRetryPolicy, JSONLWriter, ResponseValidator,
│   │                          # APIResponseValidator, UnifiedLLMLogger
│   └── pdf_utils.py           # PDFBatchManager, ArticleMerger, PDFPreprocessor,
│                              # JSONParser, clean_articles_list, TableExtractor
├── extractors/
│   ├── pdf_extractor.py       # PDFArticleExtractor — Gemini API + PDF batch processing
│   └── docx_extractor.py      # DOCXArticleExtractor — DOCX parsing
├── processors/
│   ├── image_processor.py     # ImageExtractor, ImageCleaner, RuleBasedCoverSelector,
│   │                          # RuleBasedCaptionGenerator, RuleBasedImageMatcher
│   ├── vision_processor.py    # VisionLLMClient, VisionImageProcessor — Gemini Vision API
│   └── translator.py          # ArticleTranslator — LLM translation
├── generators/
│   ├── html_generator.py      # AIHTMLGenerator — LLM HTML generation
│   ├── html_postprocessor.py  # HTML post-processing, CSS injection
│   └── output_generator.py    # PDFGenerator, DOCXGenerator, ExcelGenerator
├── pipeline/
│   ├── file_processor.py      # BatchFileProcessor, SequentialFileProcessor,
│   │                          # ThreadSafeLogger
│   └── progress_manager.py    # ProgressManager — session/checkpoint management
└── engines/
    ├── mineru/                 # Alternative: MinerU API extraction engine
    └── babeldoc/               # Alternative: BabelDoc PDF translation engine
```

## Dependency Direction

Strict one-way. No circular imports.

```
main.py
  └── pipeline, extractors, processors, generators, config

pipeline
  └── extractors, processors, generators, core, config

extractors
  └── processors, core, config

processors
  └── core, config

generators
  └── processors, core, config

core
  └── config (only)

engines/*
  └── fully isolated — no imports from root packages
```

## Key Mechanisms

### 11-Stage Progress Tracking
`pipeline/progress_manager.py` — `ProgressManager` tracks each file through 11 named stages. State is persisted to disk after every stage transition, enabling resume from the last completed stage on restart.

### Batch PDF Processing
`core/pdf_utils.py` — `PDFBatchManager` splits large PDFs into overlapping page batches. Overlap pages ensure articles that span a batch boundary are captured in full by at least one batch.

### Dual Image Processing
Two independent paths, selected per-run:
- Rule-based: `processors/image_processor.py` — heuristic cover selection, caption matching, no API calls.
- Vision AI: `processors/vision_processor.py` — `VisionImageProcessor` sends images to Gemini Vision for semantic analysis.

### Parallel Execution
`pipeline/file_processor.py` — `BatchFileProcessor` runs files concurrently via `ThreadPoolExecutor`. A `threading.Semaphore` caps simultaneous Gemini API calls to stay within rate limits. `SequentialFileProcessor` provides a single-file fallback path.
