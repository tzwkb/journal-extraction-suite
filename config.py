
from typing import Dict

class Constants:

    OUTPUT_BASE_DIR = "output"
    OUTPUT_JSON_DIR = "output/json"
    OUTPUT_EXCEL_DIR = "output/excel"
    OUTPUT_HTML_DIR = "output/html"
    IMAGE_OUTPUT_DIR = "output/image"

    LOGS_BASE_DIR = "logs"
    LOGS_LLM_RESPONSES_DIR = "logs/llm_responses"
    LOGS_COMPONENTS_DIR = "logs/components"

    FAILED_FILES_LOG = "logs/failed_files.jsonl"

    OUTLINE_SUBDIR = "outline"
    BATCHES_SUBDIR = ".cache/batches"
    ARTICLES_SUBDIR = "articles"

    LLM_LOG_EXTRACTION = "logs/llm_responses/extraction.jsonl"
    LLM_LOG_OUTLINE = "logs/llm_responses/outline.jsonl"
    LLM_LOG_TRANSLATION = "logs/llm_responses/translation.jsonl"
    LLM_LOG_TRANSLATION_ERRORS = "logs/llm_responses/global/translation_errors.jsonl"
    LLM_LOG_HTML = "logs/llm_responses/html_generation.jsonl"
    LLM_LOG_VISION = "logs/llm_responses/vision.jsonl"
    
    LLM_RESPONSE_LOG_PREFIX = "llm_response_batch_"
    ALL_BATCHES_FILENAME_TEMPLATE = "all_batches_{timestamp}.json"
    FINAL_ARTICLES_FILENAME_TEMPLATE = "final_articles_{timestamp}.json"
    
    POSITION_COMPLETE = "complete"
    POSITION_START = "start"
    POSITION_MIDDLE = "middle"
    POSITION_END = "end"
    
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_FORBIDDEN = 403
    HTTP_NOT_FOUND = 404
    HTTP_RATE_LIMIT = 429
    RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
    
    MARKDOWN_CODE_BLOCK_PATTERN = r'^```(?:json)?\s*\n'
    MARKDOWN_CODE_BLOCK_END_PATTERN = r'\n```\s*$'

class UserConfig:
    
    
    
    PDF_API_KEY = "sk-mQVaSBa9k2hu3iNTMziOTNwOPYqDu73EC77QwA5X0uz8R4cp"
    PDF_API_BASE_URL = "https://liangjiewis.com/v1"
    PDF_API_MODEL = "gemini-2.5-flash"

    TRANSLATION_API_KEY = "sk-mQVaSBa9k2hu3iNTMziOTNwOPYqDu73EC77QwA5X0uz8R4cp"
    TRANSLATION_API_BASE_URL = "https://liangjiewis.com/v1"
    TRANSLATION_API_MODEL = "gemini-2.5-flash"
    
    HTML_API_KEY = "sk-mQVaSBa9k2hu3iNTMziOTNwOPYqDu73EC77QwA5X0uz8R4cp"
    HTML_API_BASE_URL = "https://liangjiewis.com/v1"
    HTML_API_MODEL = "gemini-2.5-flash"

    PAGES_PER_BATCH = 6
    OVERLAP_PAGES = 2
    MAX_RETRIES = 10
    RETRY_DELAY = 2
    REQUEST_INTERVAL = 0.5
    MAX_WORKERS = 8
    OUTLINE_PAGES_PER_SEGMENT = 50
    PDF_API_TIMEOUT = (30, 600)
    PDF_TEMPERATURE = 0.1
    PDF_BATCH_RETRIES = 3
    PDF_BATCH_RETRY_WAIT_MIN = 1.0
    PDF_BATCH_RETRY_WAIT_MAX = 3.0
    PDF_GLOBAL_RETRY_COUNT = 2
    PDF_MAX_TOKENS = 65536
    PDF_JSON_FIX_MAX_ATTEMPTS = 5

    DOCX_MAX_TOKENS = 65536
    
    TITLE_SIMILARITY_THRESHOLD = 0.82
    
    SIMILARITY_WEIGHTS = {
        'levenshtein': 0.25,
        'jaccard_word': 0.20,
        'sequence': 0.25,
        'contains': 0.05,
        'keywords': 0.25
    }
    
    CONTENT_DUPLICATE_THRESHOLD = 0.7
    
    TRANSLATION_TIMEOUT = (30, 600)
    TRANSLATION_CONTENT_MAX_CHARS = 8000
    TRANSLATION_TEMPERATURE = 0.3
    TRANSLATION_MAX_RETRIES = 5
    TRANSLATION_RETRY_DELAY = 2
    TRANSLATION_MAX_WORKERS = 4
    TRANSLATION_MAX_TOKENS = 65536

    HTML_TEMPERATURE = 0.1
    HTML_MAX_TOKENS = 65536
    HTML_TIMEOUT = (30, 600)
    HTML_CONCURRENT_REQUESTS = 4
    HTML_API_MAX_RETRIES = 5
    HTML_ARTICLE_RETRIES = 2
    HTML_BATCH_MAX_RETRIES = 2
    HTML_REQUEST_DELAY = 0.3
    HTML_RETRY_DELAY = 2
    HTML_ARTICLE_RETRY_DELAY = 1.0
    
    HTML_ENABLE_SENSITIVE_WORDS_FILTER = True
    
    SENSITIVE_WORDS = [
        '基于规则的国际秩序',
        '大政府', '小政府', '建制派', '深层势力', 
        '精英', '官僚主义', '自由市场', '社会主义', '福利国家', 
        '平权行动', '觉醒文化', '财政责任', '霸权主义', '核心利益', 
        '接触政策', '遏制政策', '反恐战争', '土著居民', '非法移民',
        '习近平', '抗议者', '原住民', '自由', '放纵', '改革', 
        '颠覆', '暴徒', '土著', '移民'
    ]
    
    HTML_ENABLE_AD_REMOVAL = True
    
    AD_KEYWORDS = [
        '广告',
        '广告：',
        'Advertisement',
        'AD:',
        'Sponsored',
        '赞助',
    ]
    
    PDF_GENERATION_TIMEOUT = 600
    PDF_GENERATION_MAX_RETRIES = 3
    PDF_GENERATION_RETRY_DELAY = 2
    PDF_FILE_REMOVE_RETRIES = 3
    PDF_FILE_REMOVE_DELAY = 1
    DOCX_FILE_REMOVE_RETRIES = 3
    DOCX_FILE_REMOVE_DELAY = 1
    
    CASE_SENSITIVE = False
    WHOLE_WORD_ONLY = True
    
    MAX_CONCURRENT_PDF_FILES = 8

    SEQUENTIAL_EXECUTOR_CONFIG = {
        'max_concurrent_files': 4,
        'file_min_api_guarantee': 8,
        'global_api_concurrency': 40,
        'per_file_max_workers': 12,
        'global_task_queue_size': 400,
        'queue_overflow_strategy': 'delay',
        'enable_watchdog': True,
        'watchdog_timeout': 300,
        'log_executor_stats': True,
        'stats_interval': 30,
    }

    IMAGE_MIN_FILE_SIZE = 10 * 1024
    IMAGE_MIN_WIDTH = 400
    IMAGE_MIN_HEIGHT = 300
    IMAGE_MIN_COLOR_RICHNESS = 0.20

    IMAGE_SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif']
    IMAGE_EXCLUDE_FORMATS = ['webp']

    IMAGE_POSITION_TOP_THRESHOLD = 0.33
    IMAGE_POSITION_BOTTOM_THRESHOLD = 0.67
    IMAGE_BOUNDARY_TOP_STRICT = 0.15
    IMAGE_BOUNDARY_BOTTOM_STRICT = 0.85

    COVER_MAX_IMAGES = 5

    ENABLE_VISION_API = True

    IMAGE_RULE_BASED_CONFIG = {
        'cover_selection': 'highest_quality',

        'caption_strategy': 'position_based',

        'matching_strategy': 'page_proximity',
    }

    VISION_API_TEMPERATURE = 0.1
    VISION_THINGKING_BUDGET=0
    VISION_API_MAX_OUTPUT_TOKENS = 65536
    VISION_API_TIMEOUT = 600
    VISION_API_MAX_RETRIES = 20
    VISION_API_RETRY_DELAY = 3
    VISION_API_REQUEST_INTERVAL = 1.0
    VISION_API_LOG_THROTTLE_INTERVAL = 10
    VISION_API_MAX_WORKERS = 2
    VISION_API_IMAGES_PER_GROUP = 1

    VISION_PAGE_SCREENSHOT_DPI = 150

    VISION_COVER_CONFIDENCE_HIGH = 0.6
    VISION_COVER_CONFIDENCE_LOW = 0.2

    IMAGE_ENABLE_FULLPAGE_FILTER = False

    IMAGE_FULLPAGE_WIDTH_RATIO = 0.85
    IMAGE_FULLPAGE_HEIGHT_RATIO = 0.85
    IMAGE_FULLPAGE_AREA_RATIO = 0.75
    IMAGE_FULLPAGE_ASPECT_DIFF = 0.15

    IMAGE_LOOSE_MIN_FILE_SIZE = 50 * 1024
    IMAGE_LOOSE_MIN_DIMENSION = 100
    IMAGE_LOOSE_MAX_ASPECT_RATIO = 10
    IMAGE_LOOSE_MIN_COLOR_RICHNESS = 0.1

    LOG_LEVEL = "INFO"
    LOG_BUFFER_MAX_SIZE = 20
    LOG_FLUSH_INTERVAL = 0.5
    LOG_ERROR_RATE_LIMIT_SECONDS = 5

class PDFExtractionPrompts:
    
    SYSTEM_PROMPT = """You are an expert at extracting and structuring content from military and defense journal PDFs.

Your expertise includes:
- Accurately identifying article titles, subtitles, and authors
- Extracting complete article content while preserving paragraph structure
- Understanding military terminology and technical concepts
- Recognizing article boundaries and continuation across pages
- Handling multiple languages (English, Russian)

Extraction principles:
- Extract ALL content, even short sections (minimum ~100 words)
- Preserve the original text exactly - DO NOT translate or modify
- Maintain paragraph structure with proper line breaks
- Remove all footnotes and annotations
- Use exact titles from Table of Contents when provided
- Output ONLY valid JSON in markdown code block format"""
    
    OUTLINE_EXTRACTION_PROMPT = """Analyze this journal/magazine PDF and create a comprehensive outline with context summary.

DOCUMENT: First {outline_pages} pages (Total {total_pages} pages)

**YOUR TASKS:**

**TASK 1: Extract Table of Contents (if exists)**
1. Locate the Table of Contents (usually in the first few pages)
2. Extract EVERY article/section listed in the Contents
3. Include ALL types of content:
   - Feature articles
   - Regular columns/departments  
   - Short articles and news items
   - Special sections
4. Use the exact titles as they appear in the Contents
5. If an entry has sub-items, treat it as ONE article (don't split)

**TASK 2: Identify Journal Information**
- Journal name: e.g., "ARMY AVIATION", "Military Review"
- Issue number: e.g., "2024-01", "Vol.73 No.2", "January 2024"
- Language: "English" or "Russian"

**TASK 3: Generate Content Summary (CRITICAL for guiding extraction)**
Analyze the first {outline_pages} pages and provide:

1. **Journal Type Identification:**
   - Is this a multi-article magazine/journal? → `multi-article-magazine`
   - OR a single short research paper/academic article (typically <30 pages)? → `single-research-paper`
   - OR a long document with a table of contents listing named chapters/sections (e.g., a book chapter, report, or long monograph with Chapter 1, Chapter 2, etc.)? → `long-document-with-chapters`
   - OR a mix of both? → `mixed`

   **KEY DISTINCTION:**
   - `single-research-paper`: Has standard academic sections (Abstract, Introduction, Method, Results, Discussion, Conclusion). These sections are NOT separate articles — treat the whole paper as ONE article.
   - `long-document-with-chapters`: Has a Table of Contents listing named chapters or major sections with distinct topics/titles (e.g., "Chapter 1: History of...", "Part II: Analysis of..."). Each chapter/section SHOULD be extracted as a SEPARATE article.

2. **Article Structure Overview:**
   For EACH major article/paper detected, describe:
   - Main title
   - Article type (e.g., "Research Paper", "News Article", "Opinion Piece")
   - Structure (e.g., "Academic paper with Abstract, Introduction, Method, Results, Conclusion")
   - Page range (if visible)

3. **Important Guidance for Batch Processing:**
   - If this is an academic paper: Specify the main title and warn that section headings (Method, Results, etc.) are NOT separate articles
   - If this is a magazine: List expected article titles
   - Any special formatting or layout notes

**TASK 4: Generate Extraction Notes (for AI batch processors)**
These notes will be passed to AI agents processing later batches. Help them avoid mistakes by documenting:

1. **Layout Challenges**: Describe complex layouts (multi-column, sidebars, text wrapping, etc.)
2. **Common Pitfalls**: What might be confused during extraction? (headers as titles, footer fragments, ads, etc.)
3. **Special Sections**: Fixed columns or recurring content types they'll encounter
4. **Image Patterns**: How are images typically used? (captions, placement, decorative vs informational)
5. **Recommendations**: Your expert advice based on analyzing these {outline_pages} pages

Think of this as leaving notes for future extractors: "Watch out for X", "Pages have Y pattern", "Don't confuse Z with article titles"

**Output Format:**
Return a JSON object with this structure:
{{
  "journal_name": "Magazine Name",
  "issue_number": "Issue Number (e.g., 2024-01, Vol.73 No.2, etc.)",
  "language": "English or Russian",
  "journal_type": "multi-article-magazine | single-research-paper | long-document-with-chapters | mixed",
  "content_summary": "A detailed summary of the journal structure to guide batch processing. Include: 1) Main articles and their titles, 2) Article types and structures, 3) Important notes about section headings vs article titles. This summary will be provided to subsequent extraction batches as context.",
  "articles": [
    {{
      "title": "Article Title",
      "subtitle": "Subtitle if any",
      "authors": "Author name(s) if listed",
      "article_type": "research-paper | news-article | opinion | column | other",
      "structure_notes": "e.g., 'Academic paper with sections: Method, Results, Discussion' or 'Short news article'"
    }}
  ],
  "extraction_notes": {{
    "layout_challenges": [
      "Describe layout complexities that may cause extraction difficulties",
      "Examples: multi-column layouts, text wrapping around images, dense tables, complex formatting"
    ],
    "common_pitfalls": [
      "List potential extraction errors you noticed or anticipate",
      "Examples: headers being mistaken for titles, footers with article fragments, advertisement pages"
    ],
    "special_sections": [
      "Identify fixed sections or special content types",
      "Examples: 'Letters to Editor' section on pages 5-8, regular 'News Briefs' column, photo essays"
    ],
    "image_patterns": [
      "Describe how images are used in this journal",
      "Examples: large hero images at article starts, inline diagrams with captions, decorative borders on every page"
    ],
    "recommendations": "Overall advice for subsequent batch extraction based on your analysis of the first {outline_pages} pages. What should the extraction AI watch out for? What patterns did you notice?"
  }}
}}

**SPECIAL HANDLING FOR RESEARCH PAPERS:**
If you detect this is a research paper (indicators: Abstract, Introduction, Method, Results):
- List it as ONE article with the main paper title
- In "structure_notes", list the section headings (e.g., "Contains sections: Abstract, Introduction, Method, Results, Discussion, Conclusion")
- In "content_summary", CLEARLY state: "This is a single research paper titled '[Title]'. Section headings like Method, Results, Discussion are NOT separate articles."

**SPECIAL HANDLING FOR LONG DOCUMENTS WITH CHAPTERS:**
If you detect this is a long document with a Table of Contents listing named chapters/sections:
- List EACH chapter/section as a SEPARATE article in the "articles" array
- Use the exact chapter/section title from the Table of Contents
- In "content_summary", CLEARLY state: "This is a long document with chapters. Each chapter listed in the TOC should be extracted as a SEPARATE article."
- Set journal_type to "long-document-with-chapters"
- Indicators: TOC with Chapter 1/2/3, Part I/II/III, named sections with distinct topics, document >30 pages

**CRITICAL:**
- If NO Table of Contents exists, still provide the content_summary!
- You have to pick the language of the article from the context summary, and you can only use the language of the article, you cannot use other languages.
- The content_summary is MANDATORY - it guides all subsequent extraction batches
- Be detailed in content_summary - it's the most important field
- Return ONLY valid JSON in markdown code block format: ```json ... ```"""
    
    ARTICLE_EXTRACTION_EN = """Transcribe this PDF content exactly as it appears:
DOCUMENT: Pages {page_range}

{context_info}

This is a portion of a journal/magazine. Your task is to copy the article text from these pages without interpretation.

**ABSOLUTE RULES (DO NOT BREAK):**
- Copy the PDF text verbatim. Do NOT summarize, paraphrase, analyze, or invent any sentences.
- Do NOT write explanatory lead-ins such as "This article will explore..." unless those words are printed in the PDF.
- Only return text that physically exists in the supplied pages. If something is unclear or unreadable, leave it blank rather than guessing.
- Maintain original order and paragraph boundaries. Never merge or rearrange paragraphs.

**CRITICAL: Read the CONTEXT SUMMARY above carefully!**
- It tells you whether this is a research paper or multi-article magazine
- It provides main article titles and their structures
- Follow its guidance on section headings vs article titles

**IF Table of Contents is provided above:**
1. PRIMARY TASK: MATCH content to titles in the Table of Contents (use EXACT titles)
2. SECONDARY TASK: Identify articles NOT in the TOC:
   - Short articles, columns, editor's notes, special sections
   - These often appear between major articles
   - Give them descriptive titles based on their content
   - Mark with "not_in_toc": true

**IF NO Table of Contents is provided:**
1. Use the CONTEXT SUMMARY to identify article titles
2. For academic papers: Use the MAIN PAPER TITLE (not section headings like Method, Results)
3. For magazines: Extract article titles as you normally would
4. If title is not visible, use null

**ACADEMIC PAPER DETECTION (refer to CONTEXT SUMMARY):**
If the CONTEXT SUMMARY indicates this is a research paper (`single-research-paper`):
- Section headings (Abstract, Introduction, Method, Results, Discussion, Conclusion, etc.) are NOT separate articles
- Use the MAIN PAPER TITLE specified in the context summary
- Extract all content under that ONE title verbatim
- Do NOT create separate entries for Method, Results, etc.

**LONG DOCUMENT WITH CHAPTERS (refer to CONTEXT SUMMARY):**
If the CONTEXT SUMMARY indicates this is a long document with chapters (`long-document-with-chapters`):
- Each chapter/section listed in the TOC IS a separate article
- Use the EXACT chapter/section title from the TOC
- Extract ONLY the content belonging to that chapter in these pages
- A chapter may span multiple batches — extract whatever portion appears in these pages

For EACH article or article fragment, extract:
1. title:
   - If in TOC: Use EXACT title from Table of Contents
   - If NOT in TOC: Create descriptive title based on content
2. subtitle: Article subtitle (use null if not available)
3. authors: Author list, comma-separated (use null if not available)
4. content: Article content from these pages (KEEP ORIGINAL TEXT, DO NOT TRANSLATE)
5. not_in_toc: Boolean - true if this article was NOT found in the Table of Contents (default: false)

Important notes:
- **Extract ALL content, even short sections (minimum ~100 words)**
- Preserve content integrity, including all paragraphs
- Distinguish articles from other content (TOC, advertisements, headers/footers)
- **CRITICAL: Extract original text as-is. DO NOT translate, summarize, interpret, or add connective text.**
- **CRITICAL: When TOC is provided, ALL extracted content must use TOC titles.**
- **REMOVE ALL FOOTNOTES AND FOOT ANNOTATIONS** - Do not include footnote numbers, references, or footnote text in the content.
- **ADD LINE BREAKS BETWEEN PARAGRAPHS** - Separate each paragraph with a newline (\\n) for better readability.
- **SKIP ALL TABLES** - Do NOT transcribe table content. Tables will be extracted separately by a dedicated table processor. Instead, insert a placeholder: `[TABLE: <caption or brief description>]` where the table appears.

JSON format requirements:
- Must return a valid JSON array format
- Special characters (quotes, newlines) in string values will be handled automatically
- content field: Keep original text, do not truncate - FULL CONTENT REQUIRED
- Use null for missing values, not empty strings

**OUTPUT FORMAT: Use markdown code block for extended output capacity**
Return JSON array wrapped in markdown code block (this allows longer responses):
```json
[
  {{
    "title": "Article Title from TOC",
    "subtitle": "Subtitle",
    "authors": "Author1, Author2",
    "content": "Article content from these pages...",
    "not_in_toc": false
  }},
  {{
    "title": "Short Editorial Note",
    "subtitle": null,
    "authors": "Editor Name",
    "content": "Editorial content not listed in TOC...",
    "not_in_toc": true
  }}
]
```

If no article content found in these pages, return:
```json
[]
```

**CRITICAL INSTRUCTIONS:**
1. MUST use markdown code block format: ```json ... ```
2. Code block format allows you to output MUCH LONGER responses
3. Include COMPLETE article content - do NOT truncate or summarize
4. Extract ALL articles found in these pages, no matter how long the output
5. If you run out of space, prioritize article content over other fields"""
    
    ARTICLE_EXTRACTION_RU = """Дословно перепишите этот PDF-документ без каких-либо добавлений:
ДОКУМЕНТ: Страницы {page_range}

{context_info}

Это часть журнала/издания. Ваша задача - дословно переписать текст статей с этих страниц.

**ЖЕЛЕЗНЫЕ ПРАВИЛА (НЕЛЬЗЯ НАРУШАТЬ):**
- Копируйте текст PDF слово в слово. НЕЛЬЗЯ делать пересказы, интерпретации, аналитические вставки или придумывать предложения.
- Не пишите вступления вроде «В этой статье рассматривается…», если этой фразы нет в PDF.
- Передавайте только тот текст, который реально присутствует на указанных страницах. Если фрагмент нечитаем, оставьте его пустым, не догадывайтесь.
- Сохраняйте исходный порядок и границы абзацев. Не объединяйте и не переставляйте абзацы.

**КРИТИЧНО: Внимательно прочитайте КОНТЕКСТНОЕ РЕЗЮМЕ выше!**
- Оно сообщает, является ли это научной статьей или журналом с несколькими статьями
- Оно предоставляет названия основных статей и их структуру
- Следуйте его указаниям относительно заголовков разделов и заголовков статей

**ЕСЛИ Оглавление предоставлено выше:**
1. ОСНОВНАЯ ЗАДАЧА: СОПОСТАВЬТЕ содержание с заголовками в Оглавлении (используйте ТОЧНЫЕ заголовки)
2. ДОПОЛНИТЕЛЬНАЯ ЗАДАЧА: Найдите статьи НЕ в Оглавлении:
   - Короткие статьи, колонки, заметки редактора, специальные разделы
   - Они часто появляются между основными статьями
   - Дайте им описательные заголовки на основе содержания
   - Отметьте как "not_in_toc": true

**ЕСЛИ Оглавление НЕ предоставлено:**
1. Используйте КОНТЕКСТНОЕ РЕЗЮМЕ для определения заголовков статей
2. Для научных статей: Используйте ОСНОВНОЕ НАЗВАНИЕ СТАТЬИ (не заголовки разделов как Метод, Результаты)
3. Для журналов: Извлекайте заголовки статей как обычно
4. Если заголовок не виден, используйте null

**ОПРЕДЕЛЕНИЕ НАУЧНОЙ СТАТЬИ (см. КОНТЕКСТНОЕ РЕЗЮМЕ):**
Если КОНТЕКСТНОЕ РЕЗЮМЕ указывает, что это научная статья (`single-research-paper`):
- Заголовки разделов (Аннотация, Введение, Метод, Результаты, Обсуждение, Заключение и т.д.) НЕ являются отдельными статьями
- Используйте ОСНОВНОЕ НАЗВАНИЕ СТАТЬИ, указанное в контекстном резюме
- Переписывайте все содержание под этим ОДНИМ заголовком дословно
- НЕ создавайте отдельные записи для Метода, Результатов и т.д.

**ДЛИННЫЙ ДОКУМЕНТ С ГЛАВАМИ (см. КОНТЕКСТНОЕ РЕЗЮМЕ):**
Если КОНТЕКСТНОЕ РЕЗЮМЕ указывает, что это длинный документ с главами (`long-document-with-chapters`):
- Каждая глава/раздел из Оглавления является ОТДЕЛЬНОЙ статьёй
- Используйте ТОЧНОЕ название главы/раздела из Оглавления
- Извлекайте ТОЛЬКО содержание этой главы на данных страницах
- Глава может занимать несколько батчей — извлекайте ту часть, которая есть на этих страницах

Для КАЖДОЙ статьи или фрагмента статьи извлеките:
1. title: 
   - Если в Оглавлении: Используйте ТОЧНЫЙ заголовок из Оглавления
   - Если НЕ в Оглавлении: Создайте описательный заголовок на основе содержания
2. subtitle: Подзаголовок статьи (используйте null, если недоступен)
3. authors: Список авторов через запятую (используйте null, если недоступен)
4. content: Содержание статьи с этих страниц (СОХРАНЯЙТЕ ОРИГИНАЛЬНЫЙ ТЕКСТ, НЕ ПЕРЕВОДИТЕ)
5. not_in_toc: Логическое значение - true если статья НЕ найдена в Оглавлении (по умолчанию: false)

Важные примечания:
- **Извлекайте ВСЁ содержание, даже короткие разделы (минимум ~100 слов)**
- Сохраняйте целостность содержания, включая все абзацы
- Отличайте статьи от другого содержания (Оглавление, реклама, колонтитулы)
- **КРИТИЧНО: Извлекайте оригинальный текст как есть. НЕ переводите, не пересказывайте, не добавляйте связок.**
- **КРИТИЧНО: Когда предоставлено Оглавление, ВСЁ извлеченное содержание должно использовать заголовки из Оглавления.**
- **УДАЛИТЕ ВСЕ СНОСКИ И ПРИМЕЧАНИЯ** - Не включайте номера сносок, ссылки или текст сносок в содержание.
- **ДОБАВЬТЕ РАЗРЫВЫ СТРОК МЕЖДУ АБЗАЦАМИ** - Разделяйте каждый абзац новой строкой (\\n) для лучшей читаемости.

Требования к формату JSON:
- Должен возвращать действительный массив JSON
- Специальные символы (кавычки, переносы строк) в строковых значениях будут обработаны автоматически
- Поле content: Сохраняйте оригинальный текст, не усекайте - ТРЕБУЕТСЯ ПОЛНОЕ СОДЕРЖАНИЕ
- Используйте null для отсутствующих значений, не пустые строки

**ФОРМАТ ВЫВОДА: Используйте блок кода markdown для расширенной выходной емкости**
Верните массив JSON, обернутый в блок кода markdown (это позволяет более длинные ответы):
```json
[
  {{
    "title": "Заголовок из Оглавления",
    "subtitle": "Подзаголовок",
    "authors": "Автор1, Автор2",
    "content": "Содержание статьи с этих страниц...",
    "not_in_toc": false
  }},
  {{
    "title": "Короткая заметка редактора",
    "subtitle": null,
    "authors": "Имя редактора",
    "content": "Содержание не из Оглавления...",
    "not_in_toc": true
  }}
]
```

Если содержание статей не найдено на этих страницах, верните:
```json
[]
```

**КРИТИЧНЫЕ ИНСТРУКЦИИ:**
1. ДОЛЖЕН использовать формат блока кода markdown: ```json ... ```
2. Формат блока кода позволяет выводить ГОРАЗДО БОЛЕЕ ДЛИННЫЕ ответы
3. Включите ПОЛНОЕ содержание статьи - НЕ усекайте и не обобщайте
4. Извлеките ВСЕ статьи, найденные на этих страницах, независимо от длины вывода
5. Если у вас закончится место, приоритизируйте содержание статьи над другими полями"""

class DOCXExtractionPrompts:
    
    SYSTEM_PROMPT = """You are an expert at extracting and structuring content from military and defense journal documents.

Your expertise includes:
- Accurately identifying article titles, subtitles, and authors
- Extracting complete article content while preserving paragraph structure
- Understanding military terminology and technical concepts
- Recognizing article boundaries in document files
- Handling multiple languages (English, Russian)

Extraction principles:
- Extract ALL content, even short sections (minimum ~100 words)
- Preserve the original text exactly - DO NOT translate or modify
- Maintain paragraph structure with proper line breaks
- Remove all footnotes and annotations
- Use exact titles from Table of Contents when provided
- Output ONLY valid JSON in markdown code block format"""
    
    OUTLINE_EXTRACTION_PROMPT = """Analyze this journal/magazine DOCX document and create a comprehensive outline with context summary.

FILE: {docx_filename}

**YOUR TASKS:**

**TASK 1: Extract Table of Contents (if exists)**
1. Locate the Table of Contents (usually at the beginning)
2. Extract EVERY article/section listed in the Contents
3. Include ALL types of content:
   - Feature articles
   - Regular columns/departments  
   - Short articles and news items
   - Special sections
4. Use the exact titles as they appear in the Contents
5. If an entry has sub-items, treat it as ONE article (don't split)

**TASK 2: Identify Journal Information**
- Journal name: e.g., "ARMY AVIATION", "Military Review"
- Issue number: e.g., "2024-01", "Vol.73 No.2", "January 2024"
- Language: "English" or "Russian"

**TASK 3: Generate Content Summary (CRITICAL for guiding extraction)**
Analyze the document and provide:

1. **Journal Type Identification:**
   - Is this a multi-article magazine/journal? 
   - OR a single research paper/academic article?
   - OR a mix of both?

2. **Article Structure Overview:**
   For EACH major article/paper detected, describe:
   - Main title
   - Article type (e.g., "Research Paper", "News Article", "Opinion Piece")
   - Structure (e.g., "Academic paper with Abstract, Introduction, Method, Results, Conclusion")

3. **Important Guidance for Extraction:**
   - If this is an academic paper: Specify the main title and warn that section headings (Method, Results, etc.) are NOT separate articles
   - If this is a magazine: List expected article titles
   - Any special formatting or layout notes

**Output Format:**
Return a JSON object with this structure:
{{
  "journal_name": "Magazine Name",
  "issue_number": "Issue Number (e.g., 2024-01, Vol.73 No.2, etc.)",
  "language": "English or Russian",
  "journal_type": "multi-article-magazine | single-research-paper | long-document-with-chapters | mixed",
  "content_summary": "A detailed summary of the journal structure to guide extraction. Include: 1) Main articles and their titles, 2) Article types and structures, 3) Important notes about section headings vs article titles.",
  "articles": [
    {{
      "title": "Article Title",
      "subtitle": "Subtitle if any",
      "authors": "Author name(s) if listed",
      "article_type": "research-paper | news-article | opinion | column | other",
      "structure_notes": "e.g., 'Academic paper with sections: Method, Results, Discussion' or 'Short news article'"
    }}
  ]
}}

**SPECIAL HANDLING FOR RESEARCH PAPERS:**
If you detect this is a research paper (indicators: Abstract, Introduction, Method, Results):
- List it as ONE article with the main paper title
- In "structure_notes", list the section headings (e.g., "Contains sections: Abstract, Introduction, Method, Results, Discussion, Conclusion")
- In "content_summary", CLEARLY state: "This is a single research paper titled '[Title]'. Section headings like Method, Results, Discussion are NOT separate articles."

**SPECIAL HANDLING FOR LONG DOCUMENTS WITH CHAPTERS:**
If you detect this is a long document with a Table of Contents listing named chapters/sections:
- List EACH chapter/section as a SEPARATE article in the "articles" array
- Use the exact chapter/section title from the Table of Contents
- In "content_summary", CLEARLY state: "This is a long document with chapters. Each chapter listed in the TOC should be extracted as a SEPARATE article."
- Set journal_type to "long-document-with-chapters"
- Indicators: TOC with Chapter 1/2/3, Part I/II/III, named sections with distinct topics, document >30 pages

**CRITICAL:**
- If NO Table of Contents exists, still provide the content_summary!
- The content_summary is MANDATORY - it guides the extraction
- Be detailed in content_summary - it's the most important field
- Return ONLY valid JSON in markdown code block format: ```json ... ```"""
    
    ARTICLE_EXTRACTION_EN = """Transcribe this DOCX document:
FILE: {docx_filename}

{context_info}

This is a journal/magazine document. Your task is to extract all article content.

**CRITICAL: Read the CONTEXT SUMMARY above carefully!**
- It tells you whether this is a research paper or multi-article magazine
- It provides main article titles and their structures
- Follow its guidance on section headings vs article titles

**IF Table of Contents is provided above:**
1. PRIMARY TASK: MATCH content to titles in the Table of Contents (use EXACT titles)
2. SECONDARY TASK: Identify articles NOT in the TOC:
   - Short articles, columns, editor's notes, special sections
   - Give them descriptive titles based on their content
   - Mark with "not_in_toc": true

**IF NO Table of Contents is provided:**
1. Use the CONTEXT SUMMARY to identify article titles
2. For academic papers: Use the MAIN PAPER TITLE (not section headings like Method, Results)
3. For magazines: Extract article titles as you normally would

**ACADEMIC PAPER DETECTION (refer to CONTEXT SUMMARY):**
If the CONTEXT SUMMARY indicates this is a research paper:
- Section headings (Abstract, Introduction, Method, Results, Discussion, Conclusion, etc.) are NOT separate articles
- Use the MAIN PAPER TITLE specified in the context summary
- Extract all content under that ONE title
- Do NOT create separate entries for Method, Results, etc.

For EACH article, extract:
1. title: 
   - If in TOC: Use EXACT title from Table of Contents
   - If NOT in TOC: Create descriptive title based on content
2. subtitle: Article subtitle (use null if not available)
3. authors: Author list, comma-separated (use null if not available)
4. content: Complete article text (KEEP ORIGINAL TEXT, DO NOT TRANSLATE)
5. not_in_toc: Boolean - true if this article was NOT found in the Table of Contents (default: false)

Important notes:
- **Extract ALL content, even short sections (minimum ~100 words)**
- Preserve content integrity, including all paragraphs
- **CRITICAL: Extract original text as-is. DO NOT translate or modify.**
- **CRITICAL: When TOC is provided, ALL extracted content must use TOC titles.**
- **REMOVE ALL FOOTNOTES AND ANNOTATIONS** - Do not include footnote numbers, references, or footnote text
- **ADD LINE BREAKS BETWEEN PARAGRAPHS** - Separate each paragraph with a newline (\\n) for better readability
- **SKIP ALL TABLES** - Do NOT transcribe table content. Tables will be extracted separately. Instead, insert a placeholder: `[TABLE: <caption or brief description>]` where the table appears.

**OUTPUT FORMAT: Use markdown code block for extended output capacity**
Return a JSON array wrapped in a markdown code block (this allows longer responses):
```json
[
  {{
    "title": "Title from TOC",
    "subtitle": "Subtitle",
    "authors": "Author1, Author2",
    "content": "Complete article content...",
    "not_in_toc": false
  }}
]
```

**CRITICAL INSTRUCTIONS:**
1. MUST use markdown code block format: ```json ... ```
2. Include COMPLETE article content - do NOT truncate or summarize
3. Extract ALL articles found in this document
4. If you run out of space, prioritize article content over other fields"""
    
    ARTICLE_EXTRACTION_RU = """Проанализируйте этот DOCX-документ:
ФАЙЛ: {docx_filename}

{context_info}

Это журнальный/издательский документ. Ваша задача - извлечь все содержание статей.

**КРИТИЧНО: Внимательно прочитайте КОНТЕКСТНОЕ РЕЗЮМЕ выше!**
- Оно сообщает, является ли это научной статьей или журналом с несколькими статьями
- Оно предоставляет названия основных статей и их структуру
- Следуйте его указаниям относительно заголовков разделов и заголовков статей

**ЕСЛИ Оглавление предоставлено выше:**
1. ОСНОВНАЯ ЗАДАЧА: СОПОСТАВЬТЕ содержание с заголовками в Оглавлении (используйте ТОЧНЫЕ заголовки)
2. ДОПОЛНИТЕЛЬНАЯ ЗАДАЧА: Найдите статьи НЕ в Оглавлении:
   - Короткие статьи, колонки, заметки редактора, специальные разделы
   - Дайте им описательные заголовки на основе содержания
   - Отметьте как "not_in_toc": true

**ЕСЛИ Оглавление НЕ предоставлено:**
1. Используйте КОНТЕКСТНОЕ РЕЗЮМЕ для определения заголовков статей
2. Для научных статей: Используйте ОСНОВНОЕ НАЗВАНИЕ СТАТЬИ (не заголовки разделов)
3. Для журналов: Извлекайте заголовки статей как обычно

**ОПРЕДЕЛЕНИЕ НАУЧНОЙ СТАТЬИ (см. КОНТЕКСТНОЕ РЕЗЮМЕ):**
Если КОНТЕКСТНОЕ РЕЗЮМЕ указывает, что это научная статья (`single-research-paper`):
- Заголовки разделов (Аннотация, Введение, Метод, Результаты и т.д.) НЕ являются отдельными статьями
- Используйте ОСНОВНОЕ НАЗВАНИЕ СТАТЬИ, указанное в контекстном резюме
- Извлекайте все содержание под этим ОДНИМ заголовком
- НЕ создавайте отдельные записи для Метода, Результатов и т.д.

**ДЛИННЫЙ ДОКУМЕНТ С ГЛАВАМИ (см. КОНТЕКСТНОЕ РЕЗЮМЕ):**
Если КОНТЕКСТНОЕ РЕЗЮМЕ указывает, что это длинный документ с главами (`long-document-with-chapters`):
- Каждая глава/раздел из Оглавления является ОТДЕЛЬНОЙ статьёй
- Используйте ТОЧНОЕ название главы/раздела из Оглавления
- Извлекайте ТОЛЬКО содержание этой главы на данных страницах
- Глава может занимать несколько батчей — извлекайте ту часть, которая есть на этих страницах

Для КАЖДОЙ статьи извлеките:
1. title: 
   - Если в Оглавлении: Используйте ТОЧНЫЙ заголовок из Оглавления
   - Если НЕ в Оглавлении: Создайте описательный заголовок
2. subtitle: Подзаголовок статьи (используйте null, если недоступен)
3. authors: Список авторов через запятую (используйте null, если недоступен)
4. content: Полное содержание статьи (СОХРАНЯЙТЕ ОРИГИНАЛЬНЫЙ ТЕКСТ, НЕ ПЕРЕВОДИТЕ)
5. not_in_toc: Логическое значение - true если статья НЕ найдена в Оглавлении

Важные примечания:
- **Извлекайте ВСЁ содержание, даже короткие разделы (минимум ~100 слов)**
- Сохраняйте целостность содержания, включая все абзацы
- **КРИТИЧНО: Извлекайте оригинальный текст как есть. НЕ переводите и не изменяйте.**
- **КРИТИЧНО: Когда предоставлено Оглавление, используйте заголовки из Оглавления.**
- **УДАЛИТЕ ВСЕ СНОСКИ И ПРИМЕЧАНИЯ**
- **ДОБАВЬТЕ РАЗРЫВЫ СТРОК МЕЖДУ АБЗАЦАМИ**

**ФОРМАТ ВЫВОДА:**
```json
[
  {{
    "title": "Заголовок из Оглавления",
    "subtitle": "Подзаголовок",
    "authors": "Автор1, Автор2",
    "content": "Полное содержание статьи...",
    "not_in_toc": false
  }}
]
```

**КРИТИЧНЫЕ ИНСТРУКЦИИ:**
1. ДОЛЖЕН использовать формат блока кода markdown: ```json ... ```
2. Включите ПОЛНОЕ содержание статьи - НЕ усекайте
3. Извлеките ВСЕ статьи из документа"""

class HTMLGenerationPrompts:
    
    SYSTEM_PROMPT = """You are an expert HTML generator for academic journal articles.

Your expertise includes:
- Creating clean, semantic HTML5 markup
- Properly structuring content with appropriate tags
- Converting text content into well-formatted HTML
- Handling lists, tables, quotes, and other content types
- Following web accessibility best practices

Output requirements:
- Generate ONLY the article content HTML (no <html>, <head>, or <body> tags)
- Use semantic HTML tags appropriately
- Ensure proper indentation (4 spaces per level)
- Output ONLY the HTML code with no explanations"""

    CONTENT_GENERATION_PROMPT = """I will provide you with an article's metadata and content. Generate clean, semantic HTML for ONLY the article content section (not the full page).

**Article Data:**
- Title: {title}
- Subtitle: {subtitle}
- Authors: {authors}
- Content: {content}

**Requirements:**
1. Generate ONLY the article content HTML (no <html>, <head>, or <body> tags)
2. Start directly with content paragraphs
3. DO NOT repeat the title, subtitle, or authors in the content (they will be displayed separately)
4. Use semantic HTML tags with proper structure:
   - <p> for paragraphs (add class="paragraph" for better styling)
   - <h3>, <h4> for section headings within the article
     **IMPORTANT**: <h3> headings should have MORE space ABOVE (distant from previous content) and LESS space BELOW (close to following content)
   - <ul>/<ol> for lists (add class="content-list" for better styling)
   - <table> for tabular data with proper classes
   - <blockquote> for quotes (add class="highlight-quote")
   - <strong> and <em> for emphasis
   - <div class="section"> to group related content
5. For table-like content, convert to proper HTML tables:
   - Use <table class="content-table">
   - Include <thead> and <tbody>
   - Add <caption> if the table has a title
6. For lists, structure them properly:
   - Use <ul class="content-list"> for unordered lists
   - Use <ol class="numbered-list"> for ordered/numbered lists
   - Use <li> for each list item
7. For quotes or important callouts:
   - Use <blockquote class="highlight-quote"> for blockquotes
   - Use <p class="important-note"> for important notes
8. For multi-paragraph sections, group them:
   - Use <div class="section"> to wrap related paragraphs
9. Preserve all original content - do NOT summarize or omit anything
10. Clean up any redundant information
11. Use proper indentation (4 spaces per level)
12. Add spacing between major sections using empty lines
13. Output ONLY the HTML code, no explanations

**CRITICAL - DO NOT generate image tags:**
14. STRICTLY FORBIDDEN to generate <img> tags - NEVER generate <img>, <figure>, or <figcaption> tags
15. If content mentions images/figures (e.g., "Figure 1", "图2", "See diagram 3"):
    - Keep the text description as plain paragraph: <p class="figure-reference">Figure 1. Description text</p>
    - NEVER generate <img src="path/to/..."> or <img src="xxx.jpg"> placeholders
    - NEVER generate <figure> or <figcaption> tags
16. We don't have actual image files, so ANY <img> tag will be broken
17. Just keep image references as descriptive text paragraphs with class="figure-reference"

**Markdown tables in content:**
18. If content contains Markdown table syntax (lines starting with | and --- separators), convert them to proper HTML:
    - Use <table class="content-table"> with <thead> and <tbody>
    - The bold text before the table (e.g., **Table 1. Title**) should become <caption>
19. If content contains a `[TABLE: description]` placeholder (table not available), render it as:
    <p class="table-placeholder">[Table: description]</p>

**Example Output Format (with better structure):**
<div class="section">
    <p class="paragraph">First paragraph of the article content with proper spacing...</p>
    <p class="paragraph">Second paragraph continuing the discussion...</p>
</div>

<div class="section">
    <h3>Section Heading</h3>
    <p class="paragraph">Section content here...</p>
    
    <ul class="content-list">
        <li>First point with details</li>
        <li>Second point with explanation</li>
        <li>Third point with context</li>
    </ul>
</div>

<div class="section">
    <p class="figure-reference">Figure 1. Schematic diagram of the device structure</p>
    <p class="paragraph">Continue with main content and analysis...</p>
</div>

<div class="section">
    <blockquote class="highlight-quote">
        <p>Important quote or highlighted text that stands out</p>
    </blockquote>
</div>

<div class="section">
    <table class="content-table">
        <caption>Table 1: Summary of Results</caption>
        <thead>
            <tr>
                <th>Column 1</th>
                <th>Column 2</th>
                <th>Column 3</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Data 1</td>
                <td>Data 2</td>
                <td>Data 3</td>
            </tr>
        </tbody>
    </table>
</div>

Now generate the HTML for the provided article with proper structure and classes:"""

class TranslationPrompts:
    
    SYSTEM_PROMPT = """你是一位专业的军事期刊翻译专家，精通军事术语、武器装备、战术理论和国防科技领域的翻译。

你的专业能力包括：
- 准确翻译各类军事术语和专业概念
- 熟悉各国武器装备的标准译名
- 理解战术战略理论的专业表达
- 掌握军事文献的写作规范和风格

翻译原则：
1. 保持军事期刊的专业性和严谨性
2. 译文自然流畅，符合目标语言的军事文献表达习惯
3. 保留原文的段落结构和格式
4. URL、邮箱、编号、型号等保持原文不翻译

【关键输出规则】
严格要求：你必须只输出翻译后的文本。
- 不要添加任何前缀，如"译文："或"Translation:"
- 不要添加任何解释或注释
- 不要添加任何引号或括号
- 不要重复原文
- 不要输出错误消息或警告
- 直接从翻译的第一个字开始
- 直接在翻译的最后一个字结束
- 如果翻译失败，不要输出类似"翻译失败"的内容 - 只需输出最佳尝试结果

【极其重要】译文不能与原文完全相同！
- 即使是人名、地名也必须翻译成中文
- 例如：John Smith → 约翰·史密斯，Washington → 华盛顿
- 所有内容都必须翻译，不能直接照搬原文
- 译文完全相同视为翻译失败"""

    CONTENT_TRANSLATION_PROMPT = """请将以下{source_lang}军事文本翻译成{target_lang}。

【待翻译内容】
{text}

【重要输出要求】
1. 仅输出翻译后的{target_lang}文本，不要添加任何其他内容
2. 严禁输出：原文、解释、说明、注释、标记、符号
3. 严禁输出："翻译如下"、"译文："、"以下是翻译"等提示语
4. 严禁输出：错误信息、警告、提示
5. 直接从第一个字开始输出译文，不要有任何前缀

【极其重要的翻译要求】
⚠️ 译文不能与原文完全相同！这是不可接受的！
- 所有内容都必须翻译成中文，包括人名、地名等专有名词
- 人名示例：John Smith → 约翰·史密斯，Barack Obama → 巴拉克·奥巴马
- 地名示例：Washington → 华盛顿，Pentagon → 五角大楼
- 组织名称也要翻译：Department of Defense → 国防部
- 唯一例外：URL、邮箱、武器型号编号（如F-35、M1A2）可保持原文，如果有URL中的元素被误术语替换了，请你修正
- 如果译文与原文完全相同，将被视为翻译失败

【参考文献章节特殊规则】
⚠️ 如果内容包含参考文献章节（References/Bibliography/Works Cited等），请遵循以下规则：
- 章节标题可翻译：References → 参考文献、Bibliography → 参考书目
- 参考文献条目中的以下内容必须保持原文，不得翻译：
  * 期刊名称（Journal names）
  * 作者姓名（Author names）
  * 出版社名称（Publisher names）
  * 论文/书籍标题（Article/Book titles）
  * DOI、ISBN、ISSN等标识符
  * URL和网址
  * 出版年份、卷号、期号、页码
- 简而言之：参考文献章节中除了章节标题外，其他内容都应保持原文

【译文】"""

    TITLE_TRANSLATION_PROMPT = """请将以下军事期刊{field_name}从{source_lang}翻译成{target_lang}。

原文：{text}

【严格输出要求】
1. 仅输出翻译后的{target_lang}{field_name}
2. 严禁添加：引号、书名号、冒号、序号、前缀、后缀
3. 严禁添加："译文："、"翻译："等提示语
4. 严禁添加：解释、说明、注释
5. 直接输出译文，不要有任何额外符号或文字

【极其重要】译文不能与原文完全相同！
- 即使{field_name}中包含人名、地名，也必须翻译成中文
- 例如：John Smith → 约翰·史密斯，Washington → 华盛顿
- 译文与原文完全相同将被视为翻译失败

【译文】"""

    BATCH_TRANSLATION_PROMPT = """你是一位专业的军事期刊翻译专家。请将以下军事期刊文章的各个字段从{source_lang}翻译成{target_lang}。

【待翻译内容（JSON格式）】
```json
{{
  "title": "{title}",
  "subtitle": "{subtitle}",
  "authors": "{authors}",
  "content": "{content}"
}}
```

【严格输出要求】
1. 必须以JSON格式输出，包含以下字段：
   - "title_zh": 翻译后的标题
   - "subtitle_zh": 翻译后的副标题（如果原文为空则输出空字符串）
   - "authors_zh": 翻译后的作者（如果原文为空则输出空字符串）
   - "content_zh": 翻译后的正文

2. 输出示例：
```json
{{
  "title_zh": "翻译后的标题",
  "subtitle_zh": "翻译后的副标题",
  "authors_zh": "翻译后的作者",
  "content_zh": "翻译后的正文内容..."
}}
```

3. 严禁添加任何JSON之外的内容：
   - 不要添加 "```json" 或 "```" 标记
   - 不要添加 "译文："、"翻译结果：" 等前缀
   - 不要添加任何解释、说明、注释
   - 直接输出JSON对象，从 {{ 开始，到 }} 结束

【翻译质量要求】
⚠️ 极其重要：译文不能与原文完全相同！
- 所有内容都必须翻译成中文，包括人名、地名等专有名词
- 人名示例：John Smith → 约翰·史密斯，Barack Obama → 巴拉克·奥巴马
- 地名示例：Washington → 华盛顿，Pentagon → 五角大楼
- 组织名称：Department of Defense → 国防部
- 唯一例外：URL、邮箱、武器型号编号（如F-35、M1A2）可保持原文
- 如果原文被术语库替换了部分内容（如含有中文术语），请保持术语库的替换，翻译剩余部分

【参考文献章节特殊规则】
如果正文包含参考文献章节（References/Bibliography等）：
- 章节标题可翻译：References → 参考文献
- 参考文献条目中的作者姓名、期刊名称、书籍标题、DOI、URL等必须保持原文
- 仅翻译章节标题即可

【输出JSON】"""

def get_prompts(source_language: str = "English") -> Dict[str, str]:
    if source_language == 'Russian':
        return {'article_extraction': PDFExtractionPrompts.ARTICLE_EXTRACTION_RU}
    else:
        return {'article_extraction': PDFExtractionPrompts.ARTICLE_EXTRACTION_EN}

UserConfig.TRANSLATION_SYSTEM_PROMPT = TranslationPrompts.SYSTEM_PROMPT
UserConfig.TRANSLATION_CONTENT_PROMPT = TranslationPrompts.CONTENT_TRANSLATION_PROMPT
UserConfig.TRANSLATION_TITLE_PROMPT = TranslationPrompts.TITLE_TRANSLATION_PROMPT
UserConfig.BATCH_TRANSLATION_PROMPT = TranslationPrompts.BATCH_TRANSLATION_PROMPT

