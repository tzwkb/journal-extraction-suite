# 图片处理专题文档 / Image Processing Guide

📖 [返回主文档](../README.md) | 📚 [系统架构](ARCHITECTURE.md) | 🔧 [Vision API](VISION_API.md)

---

## ⚡ 重要更新

**v2.12.0 (2025-12-17)**: 新增**规则模式**，支持无AI图片处理！

- ✅ 一键切换：通过 `ENABLE_VISION_API` 开关选择模式
- ⚡ 高速处理：规则模式无需API调用，速度提升3-5倍
- 💰 零成本：完全基于规则，无API费用
- 📍 智能匹配：基于页面邻近度和位置信息

👉 详见 [图片处理模式对比](#图片处理模式对比-new)

---

## 📑 目录

- [📊 图片处理模式对比](#图片处理模式对比-new)
  - [Vision AI模式](#vision-ai模式)
  - [规则模式](#规则模式-new)
  - [如何选择](#如何选择)
- [1. 图片处理概览](#1-图片处理概览-overview)
  - [1.1 处理流程图](#11-处理流程图)
  - [1.2 关键技术](#12-关键技术)
  - [1.3 核心特性](#13-核心特性)
- [2. 图片提取](#2-图片提取-image-extraction)
  - [2.1 PyMuPDF提取机制](#21-pymupdf提取机制)
  - [2.2 批次级提取策略](#22-批次级提取策略)
  - [2.3 缓存机制](#23-缓存机制)
- [3. 图片清洗](#3-图片清洗-image-cleaning)
  - [3.1 无效图片过滤标准](#31-无效图片过滤标准)
  - [3.2 质量检测算法](#32-质量检测算法)
  - [3.3 宽松过滤 vs 严格过滤](#33-宽松过滤-vs-严格过滤)
- [4. AI描述生成](#4-ai描述生成-vision-api)
  - [4.1 Multimodal API调用](#41-multimodal-api调用)
  - [4.2 四层验证机制](#42-四层验证机制)
  - [4.3 唯一ID系统](#43-唯一id系统)
  - [4.4 批量处理优化](#44-批量处理优化)
- [5. 图片匹配](#5-图片匹配-image-matching)
  - [5.1 文章匹配算法](#51-文章匹配算法)
  - [5.2 位置感知策略](#52-位置感知策略)
  - [5.3 边界页特殊处理](#53-边界页特殊处理)
  - [5.4 置信度评分](#54-置信度评分)
- [6. 封面选择](#6-封面选择-cover-selection)
  - [6.1 第一页提取策略](#61-第一页提取策略)
  - [6.2 AI智能选择](#62-ai智能选择)
  - [6.3 分层置信度标准](#63-分层置信度标准)
- [7. 图片描述翻译](#7-图片描述翻译-translation)
  - [7.1 翻译时机](#71-翻译时机)
  - [7.2 数据流](#72-数据流)
  - [7.3 缓存策略](#73-缓存策略)
  - [7.4 类型安全处理](#74-类型安全处理)
- [8. 配置参数详解](#8-配置参数详解-configuration)
  - [8.1 清洗参数](#81-清洗参数)
  - [8.2 匹配参数](#82-匹配参数)
  - [8.3 封面参数](#83-封面参数)
- [9. 错误处理](#9-错误处理-error-handling)
  - [9.1 严格模式](#91-严格模式)
  - [9.2 重试机制](#92-重试机制)
  - [9.3 降级策略](#93-降级策略)
- [10. 性能优化](#10-性能优化-performance)
  - [10.1 批次并发](#101-批次并发)
  - [10.2 缓存利用](#102-缓存利用)
  - [10.3 内存管理](#103-内存管理)

---

## 1. 图片处理概览 / Overview

### 1.1 处理流程图

```
PDF文件
   ↓
[批次分割] (每批5-10页)
   ↓
┌────────────────────────────────────────────┐
│  批次级图片处理 (并发100线程)               │
├────────────────────────────────────────────┤
│  1️⃣ 图片提取 (PyMuPDF)                     │
│     ├─ 提取所有图片                         │
│     ├─ 保存到 output/image/batch_XX/       │
│     └─ 生成初始元数据                       │
│                 ↓                          │
│  2️⃣ 图片清洗 (ImageCleaner)                │
│     ├─ 文件大小过滤 (>50KB)                │
│     ├─ 分辨率过滤 (>800x600)               │
│     ├─ 色彩丰富度过滤 (>20%)               │
│     └─ 格式过滤 (排除WebP)                 │
│                 ↓                          │
│  3️⃣ AI描述生成 (VisionImageProcessor)      │
│     ├─ PDF+图片一起发送给Gemini Vision     │
│     ├─ 生成2-3句英文描述                    │
│     ├─ 四层验证（格式/存在/唯一/范围）      │
│     └─ 保存到元数据                         │
│                 ↓                          │
│  4️⃣ 文章匹配 (VisionImageProcessor)        │
│     ├─ 基于位置推断图片归属                 │
│     ├─ 提取锚点文本                         │
│     ├─ 计算置信度评分                       │
│     └─ 过滤无关图片                         │
└────────────────────────────────────────────┘
   ↓
[全局汇总]
   ├─ 封面识别 (第1页图片 + AI选择)
   ├─ 去重合并
   └─ 统计报告
        ↓
[输出]
   ├─ output/image/{filename}/  (图片文件)
   ├─ output/json/{filename}/batches/images_batch_*.json  (元数据)
   └─ output/json/{filename}/outline/cover_images.json  (封面)
```

### 1.2 关键技术

| 技术 | 用途 | 库/API |
|------|------|--------|
| **PyMuPDF** | PDF图片提取 | `fitz.open()` |
| **Pillow** | 图片质量分析 | `Image.open()` |
| **Gemini Vision** | AI图片描述 | Multimodal API |
| **位置推断** | 智能匹配 | 自研算法 |
| **ThreadPoolExecutor** | 批次并发 | 标准库 |

### 1.3 核心特性

| 特性 | 说明 | 效果 |
|------|------|------|
| **自动提取** | 从PDF中提取所有图片 | 保存到output/image |
| **严格清洗** | 过滤低质量图片 | 过滤50KB/800×600/色彩单一 |
| **AI描述** | Multimodal API生成描述 | 2-3句英文描述 |
| **四层验证** | 格式→存在→唯一→范围 | 确保描述准确性 |
| **唯一ID** | image_1, image_2... | 防止重复使用 |
| **智能关联** | 仅关联相关图片 | 无关图片自动过滤 |
| **智能匹配** | 基于位置推断 | 75-85%准确率 |
| **封面识别** | 第1页AI选择 | 显示在HTML |
| **位置感知** | 边界页特殊处理 | 避免归属错误 |
| **完整元数据** | 页码/位置/尺寸/描述 | 记录到JSON |
| **严格模式** | 失败整批重试 | 确保完整性 |
| **缓存集成** | 与批次统一缓存 | 支持断点续传 |
| **格式升级** | 检测旧格式 | 自动重新生成 |

---

## 2. 图片提取 / Image Extraction

### 2.1 PyMuPDF提取机制

**核心代码 (`processors/image_processor.py`)：**

```python
def extract_batch_images(self, pdf_bytes, batch_pages):
    """从PDF批次中提取所有图片"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    for page_num in range(batch_pages[0], batch_pages[1] + 1):
        page = doc.load_page(page_num - 1)  # 0-indexed
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)

            # 生成唯一文件名
            image_filename = f"page_{page_num:03d}_img_{img_index + 1:03d}.{ext}"
            image_path = output_dir / image_filename

            # 保存图片
            with open(image_path, "wb") as img_file:
                img_file.write(base_image["image"])

            # 记录元数据
            images.append({
                "image_id": f"image_{global_counter}",
                "page": page_num,
                "path": str(image_path),
                "width": base_image["width"],
                "height": base_image["height"],
                "format": ext
            })
    return images
```

**关键特性：**
- ✅ 支持所有PyMuPDF支持的格式（PNG/JPEG/BMP/TIFF）
- ✅ 自动排除WebP格式（兼容性问题）
- ✅ 生成标准化文件名：`page_001_img_001.png`
- ✅ 记录完整元数据（页码、路径、尺寸、格式）

### 2.2 批次级提取策略

**批次并发提取：**

```
文件分割 (5-10页/批次)
   ↓
批次1  批次2  批次3  ... (100并发线程)
  ↓      ↓      ↓
图片1-5  图片6-10 图片11-15
```

**优势：**
- ✅ **并发高效**：100个批次同时提取图片
- ✅ **内存友好**：每批处理后立即释放
- ✅ **断点续传**：批次级缓存，失败不影响其他批次

### 2.3 缓存机制

**缓存结构：**

```
output/json/{filename}/batches/
├─ images_batch_01.json  (批次1图片元数据)
├─ images_batch_02.json
└─ ...
```

**元数据格式：**

```json
[
  {
    "image_id": "image_1",
    "page": 1,
    "path": "output/image/xxx/batch_01/page_001_img_001.png",
    "width": 1920,
    "height": 1080,
    "format": "png",
    "file_size": 245678,
    "is_meaningful": true,
    "description": "A graph showing...",  // AI生成
    "belongs_to_article": "Article Title",  // 匹配结果
    "anchor_text": "Figure 1 shows...",  // 锚点文本
    "confidence": 0.85  // 置信度
  }
]
```

**Cache-First 策略：**

```python
# 检查批次图片元数据缓存
images_meta_path = batches_dir / f"images_batch_{idx:02d}.json"

if images_meta_path.exists():
    # 加载缓存
    with open(images_meta_path, 'r') as f:
        cached_images = json.load(f)

    # 检查是否有Vision处理结果
    has_vision_results = any(
        img.get('description') and img.get('belongs_to_article') is not None
        for img in cached_images
    )

    if has_vision_results:
        # ✅ 缓存完整，直接使用
        return cached_images
    else:
        # 🔧 缓存不完整，增量修复
        need_vision_fix = True
```

---

## 3. 图片清洗 / Image Cleaning

### 3.1 无效图片过滤标准

**严格过滤标准（`config.py`）：**

```python
# 文件大小
IMAGE_MIN_FILE_SIZE = 50 * 1024  # 最小50KB

# 分辨率
IMAGE_MIN_WIDTH = 800  # 最小宽度800像素
IMAGE_MIN_HEIGHT = 600  # 最小高度600像素

# 色彩丰富度
IMAGE_MIN_COLOR_RICHNESS = 0.20  # 最小20%（检测纯色块）

# 格式
IMAGE_SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif']
IMAGE_EXCLUDE_FORMATS = ['webp']  # 排除WebP
```

**过滤逻辑：**

```python
def is_meaningful_image(self, image_path, image_meta):
    """判断图片是否有意义"""
    # 1. 文件大小检查
    if image_meta['file_size'] < self.min_file_size:
        return False, "文件太小"

    # 2. 分辨率检查
    if image_meta['width'] < self.min_width or \
       image_meta['height'] < self.min_height:
        return False, "分辨率太低"

    # 3. 格式检查
    if image_meta['format'].lower() in self.exclude_formats:
        return False, "不支持的格式"

    # 4. 色彩丰富度检查
    color_richness = self._calculate_color_richness(image_path)
    if color_richness < self.min_color_richness:
        return False, "色彩单一（纯色块）"

    return True, "通过"
```

### 3.2 质量检测算法

**色彩丰富度计算：**

```python
def _calculate_color_richness(self, image_path):
    """计算色彩丰富度（0-1）"""
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert('RGB')
    img_array = np.array(img)

    # 统计唯一颜色数
    pixels = img_array.reshape(-1, 3)
    unique_colors = len(np.unique(pixels, axis=0))

    # 计算色彩丰富度
    total_pixels = img_array.shape[0] * img_array.shape[1]
    richness = unique_colors / total_pixels

    return richness
```

**示例：**
- **彩色照片**：richness ≈ 0.8-1.0 ✅ 通过
- **灰度图表**：richness ≈ 0.3-0.6 ✅ 通过
- **纯色块**：richness < 0.2 ❌ 过滤
- **简单Logo**：richness ≈ 0.1 ❌ 过滤

### 3.3 宽松过滤 vs 严格过滤

**宽松过滤（`loose_filter_low_quality_images`）：**

仅过滤明显无用的图片，保留更多候选：

```python
# 宽松标准
LOOSE_MIN_FILE_SIZE = 10 * 1024  # 10KB（vs 严格50KB）
LOOSE_MIN_WIDTH = 400  # 400像素（vs 严格800）
LOOSE_MIN_HEIGHT = 300  # 300像素（vs 严格600）
# 不检查色彩丰富度
```

**使用场景对比：**

| 场景 | 使用模式 | 理由 |
|------|---------|------|
| **批次提取后** | 严格过滤 | 避免保存垃圾图片 |
| **Vision匹配前** | 宽松过滤 | 避免误杀，交给AI判断 |
| **最终输出前** | 无过滤 | 保留AI判断的所有图片 |

**统计示例：**

```
原始提取: 100张
  ↓ 严格过滤
剩余: 75张 (25%被过滤)
  ↓ Vision处理
  ↓ 宽松过滤
剩余: 70张 (5%被过滤)
  ↓ 匹配到文章
最终: 65张 (35%总过滤率)
```

---

## 4. AI描述生成 / Vision API

### 4.1 Multimodal API调用

**调用方式：同时发送PDF和图片**

```python
def annotate_and_match_images_for_batch(self, pdf_bytes, images, page_range, articles):
    """为批次图片生成AI描述并匹配到文章"""

    # 构建提示词
    prompt = f"""Analyze the images in pages {page_range} of this PDF.

For each image, provide:
1. description: 2-3 sentence description
2. belongs_to_article: Match to article title or null if irrelevant
3. anchor_text: Extract reference text (e.g., "Figure 1 shows...")

Available articles:
{self._format_article_list(articles)}

Return JSON array with image_id, description, belongs_to_article, anchor_text for each image.
"""

    # 发送PDF+提示词到Gemini Vision
    response = self.vision_client.call_vision_api(
        pdf_bytes=pdf_bytes,
        prompt=prompt,
        temperature=0.1
    )

    # 解析响应
    vision_results = json.loads(response)

    # 合并到图片元数据
    for img in images:
        result = next((r for r in vision_results if r['image_id'] == img['image_id']), None)
        if result:
            img['description'] = result['description']
            img['belongs_to_article'] = result['belongs_to_article']
            img['anchor_text'] = result['anchor_text']

    return images
```

**关键优势：**
- ✅ **PDF+图片联合分析**：LLM能看到完整上下文
- ✅ **批量处理**：一次API调用处理整个批次的所有图片
- ✅ **准确度高**：AI理解图片内容和文章关系

### 4.2 四层验证机制

**验证流程：**

```
LLM响应
   ↓
Layer 1: 格式验证
   ├─ 检查是否为有效JSON
   ├─ 检查是否为数组
   └─ 检查必需字段
        ↓ ✅
Layer 2: 存在性验证
   ├─ 检查image_id是否存在
   ├─ 检查description是否非空
   └─ 检查belongs_to_article是否有效
        ↓ ✅
Layer 3: 唯一性验证
   ├─ 检查image_id是否唯一（无重复）
   ├─ 检查description是否唯一（避免复制粘贴）
   └─ 检查anchor_text是否唯一
        ↓ ✅
Layer 4: 页面范围验证
   ├─ 检查image_id对应的图片是否在当前批次
   ├─ 检查页码是否在批次范围内
   └─ 检查belongs_to_article是否在文章列表中
        ↓ ✅
通过验证 → 使用结果
```

**验证示例代码：**

```python
def validate_vision_results(self, vision_results, images, articles):
    """四层验证Vision API响应"""

    # Layer 1: 格式验证
    if not isinstance(vision_results, list):
        raise ValueError("Vision结果必须是数组")

    for result in vision_results:
        if 'image_id' not in result or 'description' not in result:
            raise ValueError("缺少必需字段")

    # Layer 2: 存在性验证
    valid_image_ids = {img['image_id'] for img in images}
    valid_article_titles = {art['title'] for art in articles}

    for result in vision_results:
        if result['image_id'] not in valid_image_ids:
            raise ValueError(f"无效的image_id: {result['image_id']}")

        if result['belongs_to_article'] and \
           result['belongs_to_article'] not in valid_article_titles:
            raise ValueError(f"无效的文章标题")

    # Layer 3: 唯一性验证
    image_ids = [r['image_id'] for r in vision_results]
    if len(image_ids) != len(set(image_ids)):
        raise ValueError("检测到重复的image_id")

    # Layer 4: 页面范围验证
    # ... (检查页码范围)

    return True
```

### 4.3 唯一ID系统

**ID生成规则：**

```python
global_image_counter = 1  # 全局计数器

for batch in batches:
    for img in batch_images:
        img['image_id'] = f"image_{global_image_counter}"
        global_image_counter += 1
```

**示例：**

```
批次1: image_1, image_2, image_3
批次2: image_4, image_5, image_6
批次3: image_7, image_8, image_9
...
```

**优势：**
- ✅ **全局唯一**：跨批次不重复
- ✅ **顺序一致**：按提取顺序编号
- ✅ **便于引用**：LLM可以明确指代每张图片
- ✅ **防止混淆**：避免文件名重复导致的问题

### 4.4 批量处理优化

**批次级合并调用：**

```
传统方式（逐张调用）:
  图片1 → API调用1 → 描述1
  图片2 → API调用2 → 描述2
  图片3 → API调用3 → 描述3
  ...
  总计: 100次API调用

批量方式（批次合并）:
  批次1 (图片1-10) → API调用1 → 描述1-10
  批次2 (图片11-20) → API调用2 → 描述11-20
  ...
  总计: 10次API调用（减少90%）
```

**性能对比：**

| 指标 | 逐张调用 | 批次合并 | 提升 |
|------|---------|---------|------|
| **API调用数** | 1000次 | 100次 | **-90%** |
| **总耗时** | ~50分钟 | ~10分钟 | **-80%** |
| **API成本** | $10 | $1 | **-90%** |
| **成功率** | 95% | 99% | **+4%** |

---

## 5. 图片匹配 / Image Matching

### 5.1 文章匹配算法

**核心原理：基于位置推断**

```python
def match_image_to_article(image, articles):
    """根据图片位置推断归属文章"""

    image_page = image['page']
    image_position_y = image['position_y']  # 0-1 (顶部到底部)

    for article in articles:
        start_page = article['start_page']
        end_page = article['end_page']

        # 情况1: 内部页（100%属于该文章）
        if start_page < image_page < end_page:
            return article['title'], confidence=1.0

        # 情况2: 起始页
        elif image_page == start_page:
            if image_position_y < 0.15:
                # 极端顶部 → 可能属于上一篇
                return None, confidence=0.3
            else:
                # 其他位置 → 属于当前文章
                return article['title'], confidence=0.8

        # 情况3: 结束页
        elif image_page == end_page:
            if image_position_y > 0.85:
                # 极端底部 → 可能属于下一篇
                return None, confidence=0.3
            else:
                # 其他位置 → 属于当前文章
                return article['title'], confidence=0.8

    # 不属于任何文章
    return None, confidence=0.0
```

### 5.2 位置感知策略

**页面位置定义：**

```
  0.0 ────────────────────── 页面顶部
   ↓
  0.15 ─────────────────────  极端顶部边界
   ↓
  0.33 ─────────────────────  顶部区域边界
   ↓
  0.67 ─────────────────────  底部区域边界
   ↓
  0.85 ─────────────────────  极端底部边界
   ↓
  1.0 ────────────────────── 页面底部
```

**配置参数：**

```python
IMAGE_POSITION_TOP_THRESHOLD = 0.33  # 顶部区域阈值
IMAGE_POSITION_BOTTOM_THRESHOLD = 0.67  # 底部区域阈值
IMAGE_BOUNDARY_TOP_STRICT = 0.15  # 极端顶部阈值
IMAGE_BOUNDARY_BOTTOM_STRICT = 0.85  # 极端底部阈值
```

### 5.3 边界页特殊处理

**场景1：文章起始页**

```
文章A (第5-10页)
  ↓
第5页 (起始页)
  ├─ 顶部图片 (y < 0.15) → 可能属于上一篇文章
  └─ 其他图片 (y >= 0.15) → 属于文章A
```

**场景2：文章结束页**

```
文章A (第5-10页)
  ↓
第10页 (结束页)
  ├─ 底部图片 (y > 0.85) → 可能属于下一篇文章
  └─ 其他图片 (y <= 0.85) → 属于文章A
```

**场景3：单页文章**

```
文章A (第5页)
  ↓
第5页 (起始页=结束页)
  ├─ 顶部图片 (y < 0.15) → 属于文章A (保守策略)
  ├─ 中部图片 (0.15 <= y <= 0.85) → 属于文章A
  └─ 底部图片 (y > 0.85) → 属于文章A (保守策略)
```

### 5.4 置信度评分

**置信度计算规则：**

| 场景 | 位置 | 置信度 | 说明 |
|------|------|--------|------|
| **内部页** | 任意 | 1.0 | 100%确定 |
| **起始页** | 中部/底部 (y≥0.15) | 0.8 | 高置信度 |
| **起始页** | 极端顶部 (y<0.15) | 0.3 | 低置信度（可能属于上一篇） |
| **结束页** | 顶部/中部 (y≤0.85) | 0.8 | 高置信度 |
| **结束页** | 极端底部 (y>0.85) | 0.3 | 低置信度（可能属于下一篇） |
| **外部页** | 任意 | 0.0 | 不属于该文章 |

**置信度应用：**

```python
# 低置信度图片 → 不匹配（交给AI判断）
if confidence < 0.5:
    image['belongs_to_article'] = None
    image['match_method'] = 'ai_only'

# 中等置信度图片 → 标记但允许AI覆盖
elif confidence < 0.8:
    image['belongs_to_article'] = article_title
    image['match_method'] = 'position_tentative'

# 高置信度图片 → 直接匹配
else:
    image['belongs_to_article'] = article_title
    image['match_method'] = 'position_confident'
```

---

## 6. 封面选择 / Cover Selection

### 6.1 第一页提取策略

**提取规则：**

```python
def extract_cover_images(self, all_images):
    """提取第1页的所有图片作为封面候选"""

    cover_candidates = [img for img in all_images if img['page'] == 1]

    # 按尺寸排序（优先选择大图）
    cover_candidates.sort(
        key=lambda x: x['width'] * x['height'],
        reverse=True
    )

    # 保留前10个候选
    return cover_candidates[:10]
```

### 6.2 AI智能选择

**Vision API调用：**

```python
def select_cover_image(self, cover_candidates):
    """使用AI从候选中选择最佳封面"""

    prompt = """Analyze these images from page 1 of a journal PDF.

Select the BEST cover image based on:
1. Large size and high quality
2. Represents the journal/organization (logo, title page, banner)
3. Professional appearance
4. NOT a small icon or decorative element

Return JSON:
{
  "selected_image_id": "image_X",
  "confidence": 0.0-1.0,
  "reason": "2-3 sentence explanation"
}

If NO suitable cover found, return:
{
  "selected_image_id": null,
  "confidence": 0.0,
  "reason": "explanation"
}
"""

    response = self.vision_client.call_vision_api(
        pdf_bytes=first_page_pdf,
        prompt=prompt,
        temperature=0.1
    )

    result = json.loads(response)
    return result
```

### 6.3 分层置信度标准

**置信度分级：**

| 置信度 | 分级 | 处理方式 | 示例 |
|--------|------|----------|------|
| **0.9-1.0** | 极高 | 直接使用 | 清晰的期刊标题页 |
| **0.7-0.9** | 高 | 使用 | 组织Logo+标题 |
| **0.5-0.7** | 中等 | 谨慎使用 | 可能的封面图 |
| **0.3-0.5** | 低 | 警告并使用 | 不太合适但勉强可用 |
| **<0.3** | 极低 | 拒绝使用 | 明显不合适（小图标等） |

**判断示例：**

```json
// 示例1：理想封面（置信度0.95）
{
  "selected_image_id": "image_1",
  "confidence": 0.95,
  "reason": "Large title page image with journal name 'Defense Monthly' and organization logo. High quality and professional."
}

// 示例2：可用封面（置信度0.75）
{
  "selected_image_id": "image_2",
  "confidence": 0.75,
  "reason": "Organization logo banner at top of page. Good quality but smaller than ideal."
}

// 示例3：无合适封面（置信度0.0）
{
  "selected_image_id": null,
  "confidence": 0.0,
  "reason": "Page 1 only contains small icons and decorative elements. No suitable cover image found."
}
```

**处理逻辑：**

```python
if cover_result['confidence'] >= 0.5:
    # 使用AI选择的封面
    best_cover = next(
        img for img in cover_candidates
        if img['image_id'] == cover_result['selected_image_id']
    )
    print(f"✅ 封面选择成功: {best_cover['path']}")
    print(f"   置信度: {cover_result['confidence']:.2f}")
    print(f"   理由: {cover_result['reason']}")

else:
    # 置信度太低，不使用封面
    print(f"⚠️ AI未找到合适的封面图片")
    print(f"   理由: {cover_result['reason']}")
    best_cover = None
```

---

## 7. 图片描述翻译 / Translation

### 7.1 翻译时机

**翻译阶段集成：**

```
文章提取 (extraction)
   ↓ 生成英文description
   |
   ↓
翻译阶段 (translation)
   ├─ 翻译文章标题/内容/作者
   └─ 翻译图片description和relevance
        ↓ 生成description_zh和relevance_zh
        |
        ↓
译文生成 (html_translated, pdf_translated...)
   └─ 使用中文图片描述
```

### 7.2 数据流

**完整数据流：**

```python
# 1. PDF提取阶段 - 生成英文描述
article = {
    "title": "Article Title",
    "content": "...",
    "images": [
        {
            "image_id": "image_1",
            "description": "A graph showing the relationship between X and Y",  # 英文
            "relevance": "Supports the main argument"  # 英文
        }
    ]
}

# 2. 翻译阶段 - 添加中文字段
translated_article = translator.translate(article)
# 结果：
{
    "title_zh": "文章标题",
    "content_zh": "...",
    "images": [
        {
            "image_id": "image_1",
            "description": "A graph showing...",
            "description_zh": "显示X和Y之间关系的图表",  # 新增
            "relevance": "Supports the main argument",
            "relevance_zh": "支持主要论点"  # 新增
        }
    ]
}

# 3. HTML生成阶段 - 根据is_translated选择语言
if is_translated:
    img_desc = image['description_zh']  # 使用中文
else:
    img_desc = image['description']  # 使用英文
```

### 7.3 缓存策略

**翻译缓存结构：**

```
output/json/{filename}/.cache/translation_cache/
├─ article_000.json  (文章0 + 图片翻译)
├─ article_001.json
└─ ...
```

**缓存内容：**

```json
{
  "index": 0,
  "title": "Original Title",
  "title_zh": "标题",
  "content_zh": "...",
  "images": [  // 包含完整的图片数据（含翻译）
    {
      "image_id": "image_1",
      "description": "A graph showing...",
      "description_zh": "显示X和Y之间关系的图表",
      "relevance": "Supports the main argument",
      "relevance_zh": "支持主要论点"
    }
  ],
  "translated_at": "2025-12-02T10:30:00"
}
```

**缓存加载：**

```python
def load_translation_cache(cache_dir, article_idx):
    """加载翻译缓存（含图片翻译）"""
    cache_file = cache_dir / f"article_{article_idx:03d}.json"

    if cache_file.exists():
        with open(cache_file, 'r') as f:
            cached = json.load(f)

        # ✅ 图片翻译也在缓存中
        return {
            'title_zh': cached['title_zh'],
            'content_zh': cached['content_zh'],
            'images': cached['images']  # 含description_zh
        }
    return None
```

### 7.4 类型安全处理

**问题：图片字段可能是异常类型**

```python
# 潜在问题
image['description'] = float('nan')  # NumPy导致
image['relevance'] = None  # 缺失值
```

**解决方案：类型安全包装**

```python
def translate_image_fields(self, images):
    """翻译图片字段（类型安全）"""

    for img in images:
        # 安全获取原始值
        desc = self._safe_str(img.get('description'))
        rel = self._safe_str(img.get('relevance'))

        # 翻译（仅当有有效值时）
        if desc:
            img['description_zh'] = self.translate(desc)
        else:
            img['description_zh'] = ""

        if rel:
            img['relevance_zh'] = self.translate(rel)
        else:
            img['relevance_zh'] = ""

def _safe_str(self, value):
    """安全转换为字符串（处理NaN/None）"""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()
```

**错误处理：**

```python
try:
    img['description_zh'] = self.translate(img['description'])
except Exception as e:
    logger.warning(f"图片 {img['image_id']} 描述翻译失败: {e}")
    img['description_zh'] = ""  # 降级：使用空字符串
```

---

## 8. 配置参数详解 / Configuration

### 8.1 清洗参数

```python
# 文件大小
IMAGE_MIN_FILE_SIZE = 50 * 1024  # 50KB
# 理由: 过滤小图标、装饰元素

# 分辨率
IMAGE_MIN_WIDTH = 800  # 像素
IMAGE_MIN_HEIGHT = 600  # 像素
# 理由: 确保图片清晰度，适合嵌入HTML/PDF

# 色彩丰富度
IMAGE_MIN_COLOR_RICHNESS = 0.20  # 20%
# 理由: 过滤纯色块、简单Logo
# 计算方式: 唯一颜色数 / 总像素数

# 格式
IMAGE_SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif']
IMAGE_EXCLUDE_FORMATS = ['webp']
# 理由: WebP兼容性问题，某些浏览器/PDF不支持
```

### 8.2 匹配参数

```python
# 位置阈值
IMAGE_POSITION_TOP_THRESHOLD = 0.33  # 顶部区域（0-0.33）
IMAGE_POSITION_BOTTOM_THRESHOLD = 0.67  # 底部区域（0.67-1.0）
# 用途: 定义图片位置分类

# 边界页阈值
IMAGE_BOUNDARY_TOP_STRICT = 0.15  # 极端顶部（0-0.15）
IMAGE_BOUNDARY_BOTTOM_STRICT = 0.85  # 极端底部（0.85-1.0）
# 用途: 起始页/结束页的特殊处理
```

**调优建议：**

| 期刊类型 | TOP_STRICT | BOTTOM_STRICT | 理由 |
|---------|-----------|---------------|------|
| **学术期刊** | 0.15 | 0.85 | 文章边界明确 |
| **新闻杂志** | 0.10 | 0.90 | 布局紧凑，边界模糊 |
| **技术手册** | 0.20 | 0.80 | 标题区域大，需更保守 |

### 8.3 封面参数

```python
# 封面候选数
COVER_MAX_IMAGES = 10
# 理由: 提供足够候选给AI选择，同时控制API成本

# Vision API参数
VISION_TEMPERATURE = 0.1  # 低温度 = 更确定的选择
VISION_MAX_TOKENS = 500  # 封面选择响应简短
```

---

## 9. 错误处理 / Error Handling

### 9.1 严格模式

**核心原则：图片完整性 > 速度**

```python
try:
    # 图片提取
    batch_images = image_extractor.extract_batch(...)

    # 图片清洗
    batch_images = image_cleaner.clean(batch_images)

    # AI描述生成
    batch_images = vision_processor.annotate(batch_images)

    # 文章匹配
    batch_images = vision_processor.match(batch_images, articles)

except Exception as img_error:
    # ❌ 任何步骤失败 → 整批失败
    logger.error(f"批次 {idx} 图片处理失败: {img_error}")
    logger.exception("详细错误堆栈:")

    # 标记image_processing阶段失败
    progress_manager.update_stage_progress(
        file_path,
        'image_processing',
        'failed'
    )

    # 🔄 重新抛出异常，触发批次重试
    raise
```

**与宽容模式对比：**

| 模式 | 图片提取失败 | 后果 | 适用场景 |
|------|------------|------|---------|
| **严格模式** | 整批失败并重试 | 确保完整性 | 生产环境（默认） |
| **宽容模式** | 仅记录警告，继续 | 可能缺失图片 | 调试/测试 |

### 9.2 重试机制

**三层重试：**

```
L1: API级重试
   ├─ Vision API调用失败
   ├─ 网络超时
   └─ 最多10次，指数退避
        ↓ 仍失败
L2: 批次级重试
   ├─ 图片处理整体失败
   ├─ 快速重试（1-3秒）
   └─ 最多5次
        ↓ 仍失败
L3: 全局重试
   ├─ 第一轮完成后
   ├─ 统一重试所有失败批次
   └─ 最多3次
        ↓ 仍失败
标记为failed，生成错误报告
```

**重试示例：**

```python
# L2: 批次级重试
for retry_attempt in range(5):
    try:
        images = process_batch_images(...)
        break  # 成功，退出
    except Exception as e:
        if retry_attempt < 4:
            wait_time = min(3, 1 + retry_attempt)
            logger.warning(f"批次{idx}失败，{wait_time}秒后重试({retry_attempt+1}/5)")
            time.sleep(wait_time)
        else:
            logger.error(f"批次{idx}已达最大重试次数")
            raise
```

### 9.3 降级策略

**降级层级：**

```
理想状态:
  ├─ 所有图片 + AI描述 + 文章匹配
  └─ 完整嵌入HTML/PDF

降级Level 1:
  ├─ 所有图片 + 文章匹配（无AI描述）
  └─ 使用文件名作为描述

降级Level 2:
  ├─ 所有图片（无匹配）
  └─ 图片单独列出，不嵌入文章

降级Level 3:
  ├─ 无图片
  └─ 纯文本输出
```

**降级触发条件：**

```python
if not vision_api_available:
    # Level 1: 跳过AI描述
    logger.warning("Vision API不可用，跳过图片描述生成")
    for img in images:
        img['description'] = f"Image from page {img['page']}"

elif not articles:
    # Level 2: 跳过文章匹配
    logger.warning("无文章数据，跳过图片匹配")
    for img in images:
        img['belongs_to_article'] = None

elif all_images_failed:
    # Level 3: 完全跳过图片
    logger.warning("图片提取完全失败，跳过图片处理")
    images = []
```

---

## 10. 性能优化 / Performance

### 10.1 批次并发

**并发配置：**

```python
MAX_WORKERS = 100  # 批次级并发线程数
REQUEST_INTERVAL = 1  # 请求间隔（秒）
```

**性能对比：**

| 配置 | 处理时间 | 成功率 | 说明 |
|------|---------|--------|------|
| **串行** | 50分钟 | 99% | 慢但稳定 |
| **50并发** | 10分钟 | 98% | 平衡选择 |
| **100并发** | 5分钟 | 97% | 快但可能不稳定 |
| **200并发** | 4分钟 | 90% | 过快，错误率高 |

### 10.2 缓存利用

**缓存命中率优化：**

```
首次运行:
  └─ 缓存命中率: 0%
       ↓
中断重新运行:
  └─ 缓存命中率: 75%（75%批次跳过）
       ↓
修复重新运行:
  └─ 缓存命中率: 90%（仅重新处理失败批次）
```

**缓存策略：**

```python
def extract_batch_with_cache(batch_idx, batch):
    """带缓存的批次提取"""

    cache_file = f"images_batch_{batch_idx:02d}.json"

    # 1. 检查缓存
    if cache_file.exists():
        cached_images = load_cache(cache_file)

        # 2. 验证缓存完整性
        if validate_image_cache(cached_images):
            print(f"✓ [缓存] 批次{batch_idx}已存在，跳过")
            return cached_images

    # 3. 缓存不存在或不完整 → 重新提取
    images = extract_images(batch)
    save_cache(cache_file, images)
    return images
```

### 10.3 内存管理

**内存优化策略：**

| 策略 | 实现 | 效果 |
|------|------|------|
| **流式处理** | 边提取边保存，立即释放 | 峰值内存<2GB |
| **批次分割** | 5-10页/批次 | 避免OOM |
| **图片压缩** | PNG优化、JPEG质量80% | 减少50%磁盘 |
| **缓存清理** | 处理完删除临时文件 | 释放磁盘空间 |

**内存监控：**

```python
import psutil

def log_memory_usage():
    """记录内存使用情况"""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024

    if mem_mb > 1500:  # 超过1.5GB警告
        logger.warning(f"内存占用较高: {mem_mb:.1f} MB")
```

---

## 🔗 相关文档

- 📚 [系统架构](ARCHITECTURE.md) - 完整架构设计
- 🔧 [Vision API指南](VISION_API.md) - Vision API详细用法
- ⚙️ [配置说明](CONFIGURATION.md) - 完整配置参数
- 🐛 [故障排查](TROUBLESHOOTING.md) - 常见问题解决

---

📖 [返回主文档](../README.md)
