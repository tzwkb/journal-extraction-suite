# 配置说明 / Configuration Guide

📖 [返回主文档](../README.md) | 📚 [系统架构](ARCHITECTURE.md) | 🔧 [Vision API](VISION_API.md)

---

## 📑 目录

- [1. API配置](#1-api配置-api-configuration)
  - [1.1 PDF提取API](#11-pdf提取api)
  - [1.2 翻译API](#12-翻译api)
  - [1.3 HTML生成API](#13-html生成api)
  - [1.4 Vision API](#14-vision-api)
- [2. PDF处理参数](#2-pdf处理参数-pdf-processing)
  - [2.1 批次分割参数](#21-批次分割参数)
  - [2.2 重试和超时](#22-重试和超时)
  - [2.3 并发控制](#23-并发控制)
- [3. DOCX处理参数](#3-docx处理参数-docx-processing)
- [4. 文章去重参数](#4-文章去重参数-deduplication)
  - [4.1 相似度阈值](#41-相似度阈值)
  - [4.2 混合算法权重](#42-混合算法权重)
- [5. 翻译参数](#5-翻译参数-translation)
  - [5.1 并发和超时](#51-并发和超时)
  - [5.2 重试配置](#52-重试配置)
- [6. HTML生成参数](#6-html生成参数-html-generation)
  - [6.1 并发配置](#61-并发配置)
  - [6.2 重试策略](#62-重试策略)
  - [6.3 敏感词过滤](#63-敏感词过滤)
  - [6.4 广告页去除](#64-广告页去除)
- [7. PDF/DOCX生成参数](#7-pdfdocx生成参数-document-generation)
- [8. 术语库配置](#8-术语库配置-glossary)
- [9. 图片处理参数](#9-图片处理参数-image-processing)
  - [9.1 图片清洗标准](#91-图片清洗标准)
  - [9.2 图片位置判断](#92-图片位置判断)
  - [9.3 封面图片配置](#93-封面图片配置)
  - [9.4 Vision API参数](#94-vision-api参数)
- [10. 批量处理参数](#10-批量处理参数-batch-processing)
- [11. 执行器配置](#11-执行器配置-executor-configuration)
  - [11.1 执行器模式选择](#111-执行器模式选择)
  - [11.2 单文件顺序执行器配置](#112-单文件顺序执行器配置)
  - [11.3 预设配置](#113-预设配置)
- [12. 日志配置](#12-日志配置-logging)
- [13. 性能调优指南](#13-性能调优指南-performance-tuning)
  - [13.1 并发优化](#131-并发优化)
  - [13.2 超时优化](#132-超时优化)
  - [13.3 重试优化](#133-重试优化)

---

## 1. API配置 / API Configuration

### 1.1 PDF提取API

用于PDF文章提取和Vision图片处理。

```python
# config.py
class UserConfig:
    # PDF提取/VISION API
    PDF_API_KEY = "your-gemini-api-key"
    PDF_API_BASE_URL = "https://your-api-url/v1"
    PDF_API_MODEL = "gemini-2.5-flash"
```

**推荐配置**：

| 提供商 | 模型 | 成本 | 速率限制 | 适用场景 |
|--------|------|------|---------|---------|
| **Google (推荐)** | gemini-2.5-flash | $0.15/1M tokens | 500 req/min | 生产环境 |
| OpenAI | gpt-4o | $5/1M tokens | 60 req/min | 高质量需求 |

**优势对比**：

| 指标 | Gemini 2.5 Flash | GPT-4o |
|------|----------------|--------|
| **速率限制** | 500 req/min | 60 req/min |
| **成本** | $0.15/1M tokens | $5/1M tokens |
| **支持并发** | 500 | 60 |
| **PDF支持** | ✅ 原生 | ✅ |
| **Vision支持** | ✅ | ✅ |

### 1.2 翻译API

用于文章翻译（标题、内容、作者、图片描述）。

```python
# config.py
class UserConfig:
    # 翻译API
    TRANSLATION_API_KEY = "your-gemini-api-key"
    TRANSLATION_API_BASE_URL = "https://your-api-url/v1"
    TRANSLATION_API_MODEL = "gemini-2.5-flash"
```

**推荐配置**：同PDF提取API（使用相同模型以简化管理）

### 1.3 HTML生成API

用于将文章内容生成HTML格式。

```python
# config.py
class UserConfig:
    # HTML生成API
    HTML_API_KEY = "your-gemini-api-key"
    HTML_API_BASE_URL = "https://your-api-url/v1"
    HTML_API_MODEL = "gemini-2.5-flash"
```

**推荐配置**：同PDF提取API

### 1.4 Vision API

Vision API使用与PDF提取相同的配置（共享API密钥）。

**专用参数**：

```python
# config.py
class UserConfig:
    # Vision API专用参数
    VISION_API_TEMPERATURE = 0.1  # 温度（越低越确定）
    VISION_API_MAX_OUTPUT_TOKENS = 65536  # 最大输出Token
    VISION_API_TIMEOUT = 120  # 超时时间（秒）
    VISION_API_MAX_RETRIES = 5  # 最大重试次数
    VISION_API_RETRY_DELAY = 5  # 重试延迟（秒）
    VISION_API_MAX_WORKERS = 100  # 并发线程数
    VISION_API_IMAGES_PER_GROUP = 1  # 每组图片数
```

---

## 2. PDF处理参数 / PDF Processing

### 2.1 批次分割参数

**核心参数**：

```python
# config.py
class UserConfig:
    # 批次分割
    PAGES_PER_BATCH = 6  # 每批6页（推荐）
    OVERLAP_PAGES = 1  # 前后重叠1页
    OUTLINE_PAGES_PER_SEGMENT = 50  # 大纲生成页数
```

**调优指南**：

| 参数 | 推荐值 | 说明 | 影响 |
|------|--------|------|------|
| `PAGES_PER_BATCH` | 6 | 每批处理的页数 | 值越小，精度越高但API调用越多 |
| `OVERLAP_PAGES` | 1 | 批次重叠页数 | 确保跨页文章完整性 |
| `OUTLINE_PAGES_PER_SEGMENT` | 50 | 大纲生成分析页数 | 足够识别所有文章标题 |

**批次大小影响**：

```
PAGES_PER_BATCH = 6（推荐）：
- 100页PDF = 17批次
- API调用次数: 17次
- 优点: 精度高，不易截断
- 缺点: API调用较多

PAGES_PER_BATCH = 10（激进）：
- 100页PDF = 10批次
- API调用次数: 10次
- 优点: 速度快，成本低
- 缺点: 容易超出Token限制
```

### 2.2 重试和超时

```python
# config.py
class UserConfig:
    # API级重试（技术错误）
    MAX_RETRIES = 10  # 最大重试10次
    RETRY_DELAY = 2  # 基础延迟2秒（指数退避）
    PDF_API_TIMEOUT = 1800  # 超时时间30分钟

    # 批次级重试（质量错误）
    PDF_BATCH_RETRIES = 5  # 批次最大重试5次
    PDF_BATCH_RETRY_WAIT_MIN = 0.5  # 最小等待0.5秒
    PDF_BATCH_RETRY_WAIT_MAX = 1  # 最大等待1秒

    # 全局重试
    PDF_GLOBAL_RETRY_COUNT = 3  # 全局重试3次
```

**指数退避计算**：

```
重试次数 | 等待时间 | 公式
--------|---------|------
1       | 2秒     | 2 * 2^0
2       | 4秒     | 2 * 2^1
3       | 8秒     | 2 * 2^2
...     | ...     | ...
10      | 1024秒  | 2 * 2^9
```

### 2.3 并发控制

```python
# config.py
class UserConfig:
    # 批次级并发
    MAX_WORKERS = 100  # 100并发批次处理（推荐）
    REQUEST_INTERVAL = 0.1  # 请求间隔0.1秒

    # Token限制
    PDF_MAX_TOKENS = 65536  # Gemini 2.5 Flash限制
```

**并发配置对比**：

| 配置 | 批次并发 | 请求间隔 | 预计吞吐量 | 适用场景 |
|------|---------|---------|-----------|---------|
| **保守** | 50 | 0.2秒 | 60-80 PDF/小时 | API不稳定 |
| **推荐** | 100 | 0.1秒 | 80-120 PDF/小时 | 生产环境 |
| **激进** | 200 | 0.05秒 | 120-150 PDF/小时 | API稳定 |

---

## 3. DOCX处理参数 / DOCX Processing

```python
# config.py
class UserConfig:
    # DOCX提取
    DOCX_MAX_TOKENS = 65536  # 最大输出Token
```

**说明**：DOCX提取采用整文件处理，不分批次。

---

## 4. 文章去重参数 / Deduplication

### 4.1 相似度阈值

```python
# config.py
class UserConfig:
    # 标题相似度阈值（0-1）
    TITLE_SIMILARITY_THRESHOLD = 0.82  # 推荐值

    # 内容重复判断阈值
    CONTENT_DUPLICATE_THRESHOLD = 0.7
```

**阈值调优**：

| 阈值 | 去重策略 | 适用场景 | 副作用 |
|------|---------|---------|--------|
| **0.75-0.80** | 宽松 | 标题差异大的期刊 | 可能漏判相似标题 |
| **0.80-0.82** | 平衡（推荐） | 一般期刊 | 平衡准确率和召回率 |
| **0.82-0.85** | 严格 | 标题相似度高的期刊 | 可能误判不同标题 |

### 4.2 混合算法权重

```python
# config.py
class UserConfig:
    # 混合相似度算法权重（总和=1.0）
    SIMILARITY_WEIGHTS = {
        'levenshtein': 0.25,    # 编辑距离
        'jaccard_word': 0.20,   # 词级别Jaccard
        'sequence': 0.25,       # SequenceMatcher
        'contains': 0.05,       # 包含关系
        'keywords': 0.25        # 关键词相似度
    }
```

**权重调优示例**：

```python
# 场景1：强调精确匹配（学术期刊）
SIMILARITY_WEIGHTS = {
    'levenshtein': 0.35,  # 提高编辑距离权重
    'sequence': 0.35,     # 提高序列匹配权重
    'jaccard_word': 0.15,
    'keywords': 0.10,
    'contains': 0.05
}

# 场景2：强调语义相似（新闻期刊）
SIMILARITY_WEIGHTS = {
    'keywords': 0.40,     # 提高关键词权重
    'jaccard_word': 0.30,  # 提高词汇重叠权重
    'levenshtein': 0.15,
    'sequence': 0.10,
    'contains': 0.05
}
```

---

## 5. 翻译参数 / Translation

### 5.1 并发和超时

```python
# config.py
class UserConfig:
    # 翻译并发
    TRANSLATION_MAX_WORKERS = 100  # 100并发翻译
    TRANSLATION_TIMEOUT = 300  # 超时5分钟
    TRANSLATION_TEMPERATURE = 0.3  # 温度参数
    TRANSLATION_MAX_TOKENS = 65536  # 最大输出Token
```

### 5.2 重试配置

```python
# config.py
class UserConfig:
    # 翻译重试
    TRANSLATION_MAX_RETRIES = 10  # 最大重试10次
    TRANSLATION_RETRY_DELAY = 2  # 基础延迟2秒（指数退避）
```

**翻译质量验证**：

系统自动验证：
1. 译文不能与原文完全相同
2. 译文不能为空
3. 译文长度应与原文接近（允许±50%）

---

## 6. HTML生成参数 / HTML Generation

### 6.1 并发配置

```python
# config.py
class UserConfig:
    # HTML生成并发
    HTML_CONCURRENT_REQUESTS = 100  # 100并发生成
    HTML_REQUEST_DELAY = 0.1  # 请求间隔0.1秒
    HTML_TIMEOUT = 300  # 超时5分钟
```

### 6.2 重试策略

```python
# config.py
class UserConfig:
    # HTML生成重试
    HTML_API_MAX_RETRIES = 10  # API级最大重试10次
    HTML_ARTICLE_RETRIES = 3  # 单篇文章立即重试3次
    HTML_BATCH_MAX_RETRIES = 3  # 批量重试3次
    HTML_RETRY_DELAY = 2  # 基础延迟2秒
    HTML_ARTICLE_RETRY_DELAY = 0.5  # 单篇延迟0.5秒
```

### 6.3 敏感词过滤

```python
# config.py
class UserConfig:
    # 敏感词过滤开关
    HTML_ENABLE_SENSITIVE_WORDS_FILTER = True  # 启用过滤

    # 敏感词列表（按长度排序，长词优先）
    SENSITIVE_WORDS = [
        '基于规则的国际秩序',  # 最长的词优先
        '大政府', '小政府', '建制派', '深层势力',
        '精英', '官僚主义', '自由市场', '社会主义', '福利国家',
        '平权行动', '觉醒文化', '财政责任', '霸权主义', '核心利益',
        '接触政策', '遏制政策', '反恐战争', '土著居民', '非法移民',
        '习近平', '抗议者', '原住民', '自由', '放纵', '改革',
        '颠覆', '暴徒', '土著', '移民'
    ]
```

**过滤规则**：
- 长词优先匹配（避免短词误杀）
- 完全匹配（不使用正则，避免误判）
- 删除整句（包含敏感词的句子整体移除）

**自定义敏感词**：

```python
# 添加自定义敏感词
SENSITIVE_WORDS = [
    # 原有敏感词...
    '您的敏感词1',
    '您的敏感词2',
]
```

### 6.4 广告页去除

```python
# config.py
class UserConfig:
    # 广告页去除开关
    HTML_ENABLE_AD_REMOVAL = True  # 启用广告去除

    # 广告识别关键词（不区分大小写）
    AD_KEYWORDS = [
        '广告',           # 中文"广告"
        '广告：',         # 中文带冒号
        'Advertisement', # 英文"Advertisement"
        'AD:',           # 英文缩写
        'Sponsored',     # 赞助内容
        '赞助',          # 中文"赞助"
    ]
```

**去除逻辑**：
- 检查文章标题是否包含关键词
- 大小写不敏感
- 匹配即删除整篇文章

---

## 7. PDF/DOCX生成参数 / Document Generation

```python
# config.py
class UserConfig:
    # PDF生成
    PDF_GENERATION_TIMEOUT = 600  # 超时10分钟
    PDF_GENERATION_MAX_RETRIES = 3  # 最大重试3次
    PDF_GENERATION_RETRY_DELAY = 2  # 重试延迟2秒

    # 文件删除重试（Windows文件锁问题）
    PDF_FILE_REMOVE_RETRIES = 3  # 删除重试3次
    PDF_FILE_REMOVE_DELAY = 1  # 重试延迟1秒
    DOCX_FILE_REMOVE_RETRIES = 3
    DOCX_FILE_REMOVE_DELAY = 1
```

---

## 8. 术语库配置 / Glossary

```python
# config.py
class UserConfig:
    # 术语库配置
    CASE_SENSITIVE = False  # 不区分大小写（推荐）
    WHOLE_WORD_ONLY = True  # 仅匹配完整单词（推荐）
```

**配置说明**：

| 参数 | 推荐值 | 说明 | 示例 |
|------|--------|------|------|
| `CASE_SENSITIVE` | False | 不区分大小写 | "NATO" 匹配 "nato" |
| `WHOLE_WORD_ONLY` | True | 完整单词匹配 | "cloud" 不匹配 "cloudy" |

**术语库格式**：

```
terminology/通用库术语-20241008.xlsx

| 英文术语          | 中文术语   |
|------------------|-----------|
| cybersecurity    | 网络安全   |
| SANDF            | 南非国防军 |
| cloud computing  | 云计算     |
```

---

## 9. 图片处理参数 / Image Processing

### 9.1 图片清洗标准

```python
# config.py
class UserConfig:
    # 图片清洗标准（宽松模式）
    IMAGE_MIN_FILE_SIZE = 10 * 1024  # 最小10KB
    IMAGE_MIN_WIDTH = 400  # 最小宽度400px
    IMAGE_MIN_HEIGHT = 300  # 最小高度300px
    IMAGE_MIN_COLOR_RICHNESS = 0.20  # 最小色彩丰富度20%

    # 图片格式配置
    IMAGE_SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif']
    IMAGE_EXCLUDE_FORMATS = ['webp']  # 排除WebP（兼容性问题）
```

**清洗标准对比**：

| 场景 | MIN_FILE_SIZE | MIN_WIDTH | MIN_HEIGHT | COLOR_RICHNESS | 说明 |
|------|--------------|-----------|------------|----------------|------|
| **宽松（推荐）** | 10KB | 400px | 300px | 20% | 保留更多图片 |
| **中等** | 30KB | 600px | 450px | 20% | 平衡质量和数量 |
| **严格** | 50KB | 800px | 600px | 20% | 仅高质量图片 |

**色彩丰富度说明**：

```
色彩丰富度 = 唯一颜色数 / 总像素数

示例：
- 彩色照片: 0.8-1.0 ✅ 通过
- 灰度图表: 0.3-0.6 ✅ 通过
- 纯色块: <0.2 ❌ 过滤
```

### 9.2 图片位置判断

```python
# config.py
class UserConfig:
    # 图片位置阈值（用于智能匹配）
    IMAGE_POSITION_TOP_THRESHOLD = 0.33  # 顶部区域（y < 0.33）
    IMAGE_POSITION_BOTTOM_THRESHOLD = 0.67  # 底部区域（y > 0.67）
    IMAGE_BOUNDARY_TOP_STRICT = 0.15  # 极端顶部（y < 0.15）
    IMAGE_BOUNDARY_BOTTOM_STRICT = 0.85  # 极端底部（y > 0.85）
```

**位置坐标系统**：

```
  0.0 ──────────────────── 页面顶部
   ↓
  0.15 ───────────────────  极端顶部边界
   ↓
  0.33 ───────────────────  顶部区域边界
   ↓
  0.67 ───────────────────  底部区域边界
   ↓
  0.85 ───────────────────  极端底部边界
   ↓
  1.0 ──────────────────── 页面底部
```

### 9.3 封面图片配置

```python
# config.py
class UserConfig:
    # 封面图片配置
    COVER_MAX_IMAGES = 5  # 最多保留5张候选封面
```

### 9.4 Vision API参数

```python
# config.py
class UserConfig:
    # Vision API配置
    VISION_API_TEMPERATURE = 0.1  # 温度（推荐0.1）
    VISION_API_MAX_OUTPUT_TOKENS = 65536  # 最大Token
    VISION_API_TIMEOUT = 120  # 超时120秒
    VISION_API_MAX_RETRIES = 5  # 最大重试5次
    VISION_API_RETRY_DELAY = 5  # 重试延迟5秒
    VISION_API_MAX_WORKERS = 100  # 并发线程100
    VISION_API_IMAGES_PER_GROUP = 1  # 每组1张图片（推荐）

    # 页面截图DPI
    VISION_PAGE_SCREENSHOT_DPI = 150  # 150 DPI（推荐）

    # 封面置信度阈值
    VISION_COVER_CONFIDENCE_HIGH = 0.6  # 高置信度阈值
    VISION_COVER_CONFIDENCE_LOW = 0.2   # 低置信度阈值
```

**Vision API调优**：

| 参数 | 推荐值 | 说明 | 调优建议 |
|------|--------|------|---------|
| `VISION_API_IMAGES_PER_GROUP` | 1 | 每组图片数 | 1-5张，避免超时 |
| `VISION_API_MAX_WORKERS` | 100 | 并发线程 | 根据API速率限制调整 |
| `VISION_PAGE_SCREENSHOT_DPI` | 150 | 页面截图DPI | 150-300，更高更清晰但更慢 |

---

## 10. 批量处理参数 / Batch Processing

```python
# config.py
class UserConfig:
    # 文件级并发控制
    MAX_CONCURRENT_PDF_FILES = 20  # 同时处理20个PDF（推荐）
```

**并发配置计算**：

```
总并发容量 = MAX_CONCURRENT_PDF_FILES × MAX_WORKERS
推荐配置: 20文件 × 100批次 = 2000并发
预计吞吐量: 80-120 PDF/小时
```

**调优建议**：

| 场景 | MAX_CONCURRENT_PDF_FILES | 预计吞吐量 | 内存占用 |
|------|------------------------|-----------|---------|
| **低配机器** | 10 | 40-60 PDF/小时 | ~4GB |
| **推荐配置** | 20 | 80-120 PDF/小时 | ~8GB |
| **高配机器** | 30 | 120-150 PDF/小时 | ~12GB |

---

## 11. 执行器配置 / Executor Configuration

**新增功能（v2.12.0）：** 双执行器架构，根据文件数量选择合适的处理模式。

### 11.1 执行器模式选择

系统提供两种执行器模式：

| 模式 | 适用场景 | 文件并发 | API并发 | 内存占用 | 推荐使用 |
|------|----------|---------|---------|---------|---------|
| **批量并发模式** | < 50 文件 | 20 | 无限制 | 高 (~8GB) | 小批量快速处理 |
| **单文件顺序模式** | 50+ 文件 | 2-8 | 50-100 | 可控 (~4GB) | 大批量稳定处理 |

**选择建议：**

```python
# 场景1：处理 10-30 个文件
# 推荐：批量并发模式（默认）
# 优势：最快速度，充分利用API

# 场景2：处理 100-500 个文件
# 推荐：单文件顺序模式（Balanced 预设）
# 优势：稳定可控，防止资源爆炸

# 场景3：处理 1000+ 个文件
# 推荐：单文件顺序模式（Conservative 预设）
# 优势：极致稳定，长时间运行无忧
```

### 11.2 单文件顺序执行器配置

**基础配置：**

```python
# config.py
class UserConfig:
    # 单文件顺序执行器配置
    SEQUENTIAL_EXECUTOR_CONFIG = {
        # 文件级并发控制
        'max_concurrent_files': 4,  # 同时处理的文件数（推荐 2-8）

        # 全局 API 并发限制
        'global_api_concurrency': 75,  # 跨所有文件/模块的API并发总数（推荐 50-100）

        # 每文件 worker 数
        'per_file_max_workers': 28,  # 每个文件内的并发worker数（自动计算）

        # 防饿死保障
        'file_min_api_guarantee': 10,  # 每个文件最少保证的API槽位数

        # 队列大小控制
        'global_task_queue_size': 500,  # 任务队列上限（防止内存爆炸）

        # 溢出策略
        'queue_overflow_strategy': 'delay',  # 队列满时的策略：delay（延迟）或 reject（拒绝）

        # 监控配置
        'enable_watchdog': True,  # 启用看门狗（检测死锁）
        'watchdog_timeout': 300,  # 看门狗超时时间（秒，5分钟）

        # 统计日志
        'log_executor_stats': True,  # 启用执行器统计日志
        'stats_interval': 30,  # 统计日志间隔（秒）
    }
```

**配置参数详解：**

#### max_concurrent_files
- **说明：** 同时处理的文件数量
- **推荐值：** 2-8（根据系统资源调整）
- **影响：**
  - 值越大：并发度越高，速度越快，但内存占用更高
  - 值越小：更稳定，内存占用更低，但速度较慢
- **计算公式：**
  ```python
  理论最大并发 = max_concurrent_files × per_file_max_workers
  实际API并发 = min(理论最大并发, global_api_concurrency)
  ```

#### global_api_concurrency
- **说明：** 全局 API 并发上限（跨所有文件和模块）
- **推荐值：** 50-100
- **影响：**
  - 值越大：API吞吐量越高，但可能触发API限流
  - 值越小：更稳定，但处理速度较慢
- **建议：**
  - Google Gemini API：75-100（500 req/min 限制）
  - OpenAI API：50-60（60 req/min 限制）

#### per_file_max_workers
- **说明：** 每个文件内的worker数量
- **推荐值：** 自动计算（根据 global_api_concurrency 和 max_concurrent_files）
- **自动计算公式：**
  ```python
  per_file_max_workers = max(
      10,  # 最小值
      int(global_api_concurrency * 1.5 / max_concurrent_files)
  )
  ```
- **示例：**
  ```python
  # Balanced 预设
  per_file_max_workers = 75 * 1.5 / 4 = 28

  # Conservative 预设
  per_file_max_workers = 50 * 1.5 / 2 = 37
  ```

#### file_min_api_guarantee
- **说明：** 每个文件最少保证的 API 槽位数（防饿死机制）
- **推荐值：** 10
- **作用：** 确保每个文件都能获得最少的 API 资源，防止某些文件长时间无法获得 API 槽位

#### global_task_queue_size
- **说明：** 全局任务队列的最大大小
- **推荐值：** max_concurrent_files × per_file_max_workers × 5
- **作用：** 防止任务队列无限增长导致内存溢出（OOM）
- **策略：** 队列满时新任务会被阻塞（backpressure）

#### queue_overflow_strategy
- **说明：** 队列满时的处理策略
- **可选值：**
  - `'delay'`：延迟提交，阻塞等待有空位（推荐）
  - `'reject'`：拒绝任务，抛出异常
- **推荐：** 使用 `'delay'` 策略以保证所有任务都能执行

#### enable_watchdog 和 watchdog_timeout
- **说明：** 看门狗监控机制，检测死锁和卡顿
- **推荐值：**
  - `enable_watchdog`: True
  - `watchdog_timeout`: 300（5分钟）
- **作用：** 如果某个文件超过 300 秒没有进展，看门狗会发出警告

### 11.3 预设配置

系统提供三种预设配置，可直接使用：

```python
# config.py
class UserConfig:
    EXECUTOR_PRESETS = {
        # 保守模式 - 适合 1000+ 文件
        'conservative': {
            'max_concurrent_files': 2,
            'global_api_concurrency': 50,
            'per_file_max_workers': 35,
            'file_min_api_guarantee': 10,
            'global_task_queue_size': 200,
            'queue_overflow_strategy': 'delay',
            'enable_watchdog': True,
            'watchdog_timeout': 600,  # 10分钟
            'log_executor_stats': True,
            'stats_interval': 60,
        },

        # 均衡模式 - 适合 100-500 文件（推荐）
        'balanced': {
            'max_concurrent_files': 4,
            'global_api_concurrency': 75,
            'per_file_max_workers': 28,
            'file_min_api_guarantee': 10,
            'global_task_queue_size': 500,
            'queue_overflow_strategy': 'delay',
            'enable_watchdog': True,
            'watchdog_timeout': 300,  # 5分钟
            'log_executor_stats': True,
            'stats_interval': 30,
        },

        # 激进模式 - 适合 < 100 文件
        'aggressive': {
            'max_concurrent_files': 8,
            'global_api_concurrency': 100,
            'per_file_max_workers': 18,
            'file_min_api_guarantee': 10,
            'global_task_queue_size': 1000,
            'queue_overflow_strategy': 'delay',
            'enable_watchdog': True,
            'watchdog_timeout': 180,  # 3分钟
            'log_executor_stats': True,
            'stats_interval': 15,
        }
    }
```

**预设对比：**

| 预设 | 文件并发 | API并发 | Worker数 | 队列大小 | 看门狗超时 | 适用场景 |
|------|---------|---------|---------|---------|-----------|---------|
| **Conservative** | 2 | 50 | 35 | 200 | 10分钟 | 1000+ 文件，极致稳定 |
| **Balanced** | 4 | 75 | 28 | 500 | 5分钟 | 100-500 文件，平衡速度与稳定性 |
| **Aggressive** | 8 | 100 | 18 | 1000 | 3分钟 | < 100 文件，最大化速度 |

**性能预估：**

| 预设 | 预计吞吐量 | 内存占用 | CPU占用 | 风险等级 |
|------|-----------|---------|---------|---------|
| **Conservative** | 20-30 文件/小时 | ~3GB | 20-30% | 极低 |
| **Balanced** | 40-60 文件/小时 | ~4GB | 30-50% | 低 |
| **Aggressive** | 60-80 文件/小时 | ~6GB | 50-70% | 中 |

**使用示例：**

```python
# 方式1：使用预设（推荐）
from config import UserConfig

# 获取 Balanced 预设
preset_config = UserConfig.EXECUTOR_PRESETS['balanced']

# 创建处理器
from pipeline.file_processor import SequentialFileProcessor
processor = SequentialFileProcessor(
    config=preset_config,
    progress_manager=progress_manager
)

# 方式2：自定义配置
custom_config = {
    'max_concurrent_files': 6,
    'global_api_concurrency': 80,
    'per_file_max_workers': 20,
    # ... 其他参数
}
processor = SequentialFileProcessor(
    config=custom_config,
    progress_manager=progress_manager
)

# 方式3：在 main.py 中交互式选择
# 运行 main.py，在 "步骤5: 选择处理模式" 中选择：
# - 选项 2：单文件顺序模式
# - 预设：Conservative / Balanced / Aggressive
```

---

## 12. 日志配置 / Logging

```python
# config.py
class UserConfig:
    # 日志配置
    LOG_LEVEL = "DEBUG"  # 日志级别
    LOG_BUFFER_MAX_SIZE = 10  # 日志缓冲区大小
    LOG_FLUSH_INTERVAL = 0.3  # 刷新间隔（秒）
    LOG_ERROR_RATE_LIMIT_SECONDS = 3  # 错误限流（秒）
```

**日志级别说明**：

| 级别 | 用途 | 输出内容 | 适用场景 |
|------|------|---------|---------|
| **DEBUG** | 详细调试 | 所有日志 | 开发/调试 |
| **INFO** | 一般信息 | 重要进度 | 生产环境 |
| **WARNING** | 警告 | 警告和错误 | 生产环境 |
| **ERROR** | 错误 | 仅错误 | 静默运行 |

**日志文件位置**：

```
logs/
├── sessions/
│   └── session_20251202_105730.log  # 会话日志
├── pdf_extractor.log  # PDF提取日志
├── translator.log  # 翻译日志
└── html_generator.log  # HTML生成日志
```

---

## 13. 性能调优指南 / Performance Tuning

### 13.1 并发优化

**推荐配置（稳健模式）**：

```python
# config.py - 稳健平衡模式（推荐）
MAX_CONCURRENT_PDF_FILES = 20  # 文件级并发
MAX_WORKERS = 100  # 批次级并发
TRANSLATION_MAX_WORKERS = 100  # 翻译并发
HTML_CONCURRENT_REQUESTS = 100  # HTML并发
VISION_API_MAX_WORKERS = 100  # Vision并发
```

**预期性能**：
- 吞吐量: 80-120 PDF/小时
- 内存占用: ~8GB
- CPU占用: 40-60%

**激进配置（高性能模式）**：

```python
# config.py - 激进高性能模式
MAX_CONCURRENT_PDF_FILES = 30
MAX_WORKERS = 150
TRANSLATION_MAX_WORKERS = 150
HTML_CONCURRENT_REQUESTS = 150
VISION_API_MAX_WORKERS = 150
```

**预期性能**：
- 吞吐量: 120-150 PDF/小时
- 内存占用: ~12GB
- CPU占用: 60-80%
- ⚠️ 风险: 可能触发API速率限制

### 13.2 超时优化

**推荐超时配置**：

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `PDF_API_TIMEOUT` | 1800秒 (30分钟) | 大文件处理 |
| `TRANSLATION_TIMEOUT` | 300秒 (5分钟) | 快速失败 |
| `HTML_TIMEOUT` | 300秒 (5分钟) | 快速失败 |
| `VISION_API_TIMEOUT` | 120秒 (2分钟) | 图片处理 |

**超时问题排查**：

```
1. 检查API响应时间
   - 使用logs/查看实际响应时间
   - 如果平均>60秒，考虑增加超时

2. 检查网络状况
   - ping api.openai.com 或 api.gemini.com
   - 如果延迟>500ms，考虑使用代理

3. 检查批次大小
   - 如果PAGES_PER_BATCH过大，减小批次
   - 推荐: 6页/批次
```

### 13.3 重试优化

**推荐重试配置**：

```python
# 技术错误（网络/服务器）
MAX_RETRIES = 10  # 充分重试
RETRY_DELAY = 2  # 指数退避

# 质量错误（AI输出）
PDF_BATCH_RETRIES = 5  # 适度重试
HTML_ARTICLE_RETRIES = 3  # 快速重试
```

**重试次数建议**：

| 场景 | 推荐重试次数 | 理由 |
|------|------------|------|
| **API稳定** | 5次 | 减少等待时间 |
| **API不稳定** | 10次 | 确保成功率 |
| **质量错误** | 3次 | 快速失败，避免浪费 |

**指数退避优化**：

```python
# 快速退避（适合API稳定）
RETRY_DELAY = 1  # 1→2→4→8→16→32→64→128→256→512

# 平衡退避（推荐）
RETRY_DELAY = 2  # 2→4→8→16→32→64→128→256→512→1024

# 慢速退避（适合API极不稳定）
RETRY_DELAY = 5  # 5→10→20→40→80→160→320→640→1280→2560
```

---

## 🔗 相关文档

- 📚 [系统架构](ARCHITECTURE.md) - 完整架构设计
- 🖼️ [图片处理指南](IMAGE_PROCESSING.md) - 图片处理流程
- 🔧 [Vision API指南](VISION_API.md) - Vision API详细用法
- 🐛 [故障排查](TROUBLESHOOTING.md) - 常见问题解决

---

📖 [返回主文档](../README.md)
