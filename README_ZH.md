# 📚 期刊文章提取与翻译系统

**基于AI的智能期刊处理工具** - 自动提取、翻译、格式转换一站式解决方案

<div align="center">

[![Version](https://img.shields.io/badge/version-2.12.2-blue.svg)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

[English](README.md)

</div>

---

## 📑 目录

- [📖 文档导航](#-文档导航)
- [✨ 核心特点](#-核心特点)
- [🚀 快速开始](#-快速开始)
- [📁 使用流程](#-使用流程)
- [⚙️ 配置说明](#️-配置说明)
- [📊 性能指标](#-性能指标)

---

## 📖 文档导航

### 用户指南

- **[快速开始](#-快速开始)** - 5分钟上手指南（本文档）
- **[配置说明](docs/CONFIGURATION.md)** - 完整配置参数详解
- **[故障排查](docs/TROUBLESHOOTING.md)** - 常见问题与解决方案

### 技术文档

- **[系统架构](docs/ARCHITECTURE.md)** - 完整架构设计与执行流程
- **[开发指南](docs/DEVELOPER_GUIDE.md)** - 模块化开发最佳实践

### 专题指南

- **[图片处理](docs/IMAGE_PROCESSING.md)** - 图片提取、清洗、匹配详解
- **[Vision API](docs/VISION_API.md)** - Vision API集成与最佳实践
- **[更新日志](docs/CHANGELOG.md)** - 完整版本历史

---

## ✨ 核心特点

### 🚀 性能优化
- **100并发处理**：20个PDF同时处理，单文件30-45秒完成
- **80-120个PDF/小时**：稳健的生产环境配置
- **并行化处理**：Excel+HTML+翻译同时执行，提升20-30%性能

### 🎯 智能识别
- **双格式支持**：PDF分页处理 + DOCX整文件处理
- **论文vs杂志识别**：不会将论文小节误识别为独立文章
- **99%去重准确率**：混合相似度算法，解决标题重复问题

### 🖼️ 智能图片处理（v2.11+）
- **自动提取与清洗**：从PDF提取高质量图片（>10KB, >400×300px）
- **双模式支持（v2.12+）**：Vision API模式 / 规则模式（零成本，3-5倍速度）
- **AI图片描述**：Multimodal API生成2-3句专业描述（Vision模式）
- **规则匹配**：基于页面邻近度和位置的智能匹配（规则模式）
- **四层验证**：格式→存在性→唯一性→页面范围，确保准确性
- **智能匹配**：基于位置推断的图片-文章对齐（75-85%准确率）
- **封面识别**：AI智能选择或质量评分选择第1页最佳封面
- **完整元数据**：记录页码、位置、尺寸、AI描述等信息

### 🌐 专业翻译
- **术语库支持**：自动应用专业术语，确保译文用词一致
- **批量并发翻译**：100并发，稳定优先
- **质量验证**：检测译文与原文相同，自动重试
- **图片描述翻译**：自动翻译图片描述为中文

### 📄 多格式输出
- **HTML**：响应式界面，自动目录导航，内嵌封面和文章图片
- **PDF**：高质量渲染，自动书签，图片完整保留
- **DOCX**：可编辑格式，保持样式和图片
- **Excel**：原文译文对照表

### ⚡ Cache-First断点续传
- **Cache-First架构**：文件系统作为唯一真相来源
- **11阶段追踪**：extraction → image_processing → excel → html → pdf → docx（原文+译文）
- **定时自动保存**：每5分钟保存，线程安全保护
- **零损失保证**：所有API调用结果完全保留

### 🔒 全面错误处理
- **智能重试**：技术错误10次 + 指数退避，质量错误3次快速重试
- **降级处理**：失败后使用占位符，不中断流程
- **损坏图片自动跳过**（v2.11.4+）：PyMuPDF bandwriter错误不再导致批次失败
- **并发安全保障**（v2.11.4+）：UUID隔离临时目录，消除高并发文件冲突

---

## 🚀 快速开始

### 1️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

### 2️⃣ 配置API

编辑 `config.py`，推荐使用 Gemini 2.5 Flash（无速率限制）：

```python
# PDF提取
PDF_API_KEY = "your-gemini-api-key"
PDF_API_BASE_URL = "your-api-url"
PDF_API_MODEL = "gemini-2.5-flash"

# 翻译
TRANSLATION_API_KEY = "your-gemini-api-key"
TRANSLATION_API_BASE_URL = "your-api-url"
TRANSLATION_API_MODEL = "gemini-2.5-flash"

# HTML生成
HTML_API_KEY = "your-gemini-api-key"
HTML_API_BASE_URL = "your-api-url"
HTML_API_MODEL = "gemini-2.5-flash"
```

优势：无速率限制 | 支持500并发 | 成本低70% | 管理简单

### 3️⃣ 运行程序

```bash
python main.py
```

程序启动后会显示交互菜单，可以选择：
- 选择要处理的文件
- 配置翻译选项
- 选择术语库
- 选择输出格式

---

## 📁 使用流程

### 第一步：准备文件

**输入文件结构**：
```
input/
├── journal1.pdf          # PDF格式期刊
├── journal2.docx         # DOCX格式期刊
└── journal3.pdf          # 可以混合多个文件
```

**术语库**（可选，用于翻译）：
```
terminology/
└── 通用库术语-20241008.xlsx
    | 英文术语          | 中文术语   |
    |------------------|-----------|
    | cybersecurity    | 网络安全   |
    | SANDF            | 南非国防军 |
    | cloud computing  | 云计算     |
```

### 第二步：运行程序

```bash
python main.py
```

### 第三步：选择处理功能

1. **提取文章**（必选）- 从PDF/DOCX提取文章内容，自动生成期刊大纲，支持断点续传
2. **生成Excel** - 原文/译文Excel表格
3. **生成HTML** - 原文/译文HTML（带目录导航）
4. **生成PDF** - 原文/译文PDF（高质量渲染）
5. **生成DOCX** - 原文/译文DOCX（可编辑）
6. **AI翻译**（可选）- 英文→中文，应用术语库，敏感词过滤

---

## ⚙️ 配置说明

详细配置说明请参考 **[配置文档](docs/CONFIGURATION.md)**。

### 核心性能参数

```python
PARALLEL_MODE = True
MAX_CONCURRENT_PDF_FILES = 20  # 文件级并发
MAX_WORKERS = 100              # 批次级并发
PAGES_PER_BATCH = 6            # 每批6页
OVERLAP_PAGES = 1              # 重叠1页
MAX_RETRIES = 10               # 技术错误重试次数
PDF_BATCH_RETRIES = 5          # 质量错误重试次数
```

### 图片处理参数

```python
IMAGE_MIN_FILE_SIZE = 10 * 1024   # 10KB
IMAGE_MIN_WIDTH = 400             # 400像素
IMAGE_MIN_HEIGHT = 300            # 300像素
IMAGE_MIN_COLOR_RICHNESS = 0.20   # 20%色彩丰富度
VISION_API_MAX_WORKERS = 100
VISION_API_IMAGES_PER_GROUP = 1
```

### 项目结构

```
core/          # 日志、PDF工具
extractors/    # PDF/DOCX提取器
processors/    # 图片处理、翻译
generators/    # HTML/PDF/DOCX/Excel生成
pipeline/      # 流程编排、断点续传
engines/       # 替代引擎（mineru、babeldoc）
```

### 输出目录结构

```
output/
├── excel/              # Excel文件
├── html/               # HTML文件（包含封面和文章图片）
├── pdf/                # PDF文件
├── docx/               # DOCX文件
├── image/              # 提取的图片
│   └── <PDF名称>/
│       ├── batch_01/page_001_img_001.png
│       └── cover_images.json
└── json/               # 缓存的JSON数据
    └── <PDF名称>/
        ├── outline/    # 大纲相关
        ├── batches/    # 批次提取 + 图片元数据
        └── articles/   # 最终文章

logs/
├── llm_responses/      # LLM API响应日志（JSONL格式）
├── components/         # 组件运行日志
└── failed_files.jsonl  # 失败文件记录
```

---

## 📊 性能指标

| 配置 | 吞吐量 | 说明 |
|------|--------|------|
| 推荐配置 | 80-120 PDF/小时 | 文件级20并发 + 批次级100并发 |
| 激进配置 | 120-150 PDF/小时 | 文件级30并发 + 批次级150并发 |

- **整体成功率**：99.5%+
- **超时率**：<2%（从20%优化至2%）
- **图片位置获取成功率**：90%+
- **内存占用**：500MB-2GB（取决于并发数）
- **磁盘空间**：每个PDF约10-50MB（含缓存）

---

## 📞 技术支持

- **[系统架构](docs/ARCHITECTURE.md)** - 深入理解系统设计
- **[图片处理](docs/IMAGE_PROCESSING.md)** - 图片处理完整流程
- **[Vision API](docs/VISION_API.md)** - Vision API集成指南
- **[配置说明](docs/CONFIGURATION.md)** - 配置参数详解
- **[故障排查](docs/TROUBLESHOOTING.md)** - 常见问题解决
- **[更新日志](docs/CHANGELOG.md)** - 版本历史

### 常见问题

常见问题请参考 **[故障排查文档](docs/TROUBLESHOOTING.md)**：

- 程序启动后卡住 → 检查API配置和网络连接
- 翻译失败 → 检查API配额和术语库格式
- 输出文件不完整 → 检查磁盘空间和缓存文件

---

**当前版本**：v2.12.2 | **更新**：2025-12-17 | **License**：MIT
