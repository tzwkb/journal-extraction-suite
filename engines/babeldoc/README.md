# BabelDOC 翻译工作流

> 一个完整的 PDF 翻译自动化工具，基于 BabelDOC，支持单文件和批量处理

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![BabelDOC](https://img.shields.io/badge/BabelDOC-0.5.22-green.svg)](https://github.com/opendatalab/BabelDOC)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📑 目录

- [快速开始](#快速开始)
- [项目架构](#项目架构)
- [详细说明](#详细说明)
  - [核心类详解](#核心类详解)
  - [执行流程](#执行流程)
- [配置文件](#配置文件)
- [使用示例](#使用示例)
- [常见问题](#常见问题)

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.11+（已安装 Conda 环境：`babeldoc`）
- BabelDOC 0.5.22（已安装在 Conda 环境中）
- 依赖包：`pyyaml`, `openpyxl`

### 2. 使用方法

```bash
# 批量处理（处理 input/ 目录所有 PDF）
python babeldoc_workflow.py

# 单文件处理
python babeldoc_workflow.py input/paper.pdf

# 查看帮助
python babeldoc_workflow.py --help
```

### 3. 目录结构

```
babeldoc_workflow/
├── babeldoc_workflow.py    # 主程序（整合所有功能）
├── config.yaml             # 配置文件
├── input/                  # PDF 输入目录
├── output/                 # 翻译结果输出目录
├── terminology/            # 术语库目录（Excel 格式）
└── README.md              # 本文档
```

---

## 🏗️ 项目架构

### 架构图

```
用户命令
    ↓
main() 入口函数
    ↓
┌─────────────┬──────────────┐
│  单文件模式  │   批量模式    │
└──────┬──────┴──────┬───────┘
       ↓             ↓
  PDFProcessor   BatchProcessor
       │             │
       │    ┌────────┴────────┐
       │    │   扫描文件       │
       │    │   断点续传检查   │
       │    └────────┬────────┘
       │             │
       ├─────────────┤
       ↓             ↓
   处理单个 PDF 文件
       │
       ├─→ GlossaryManager    (加载术语库)
       │
       ├─→ BabelDOCCommandBuilder  (构建命令)
       │
       └─→ subprocess.run()    (执行 BabelDOC)
              ↓
          翻译结果输出
```

### 模块划分

| 模块 | 职责 | 行数 |
|------|------|------|
| **Config** | 配置管理，加载 config.yaml | 35-95 |
| **GlossaryManager** | 术语库加载与导出 | 98-152 |
| **BabelDOCCommandBuilder** | 命令行参数构建 | 155-216 |
| **PDFProcessor** | 单文件处理核心逻辑 | 219-295 |
| **BatchProcessor** | 批量处理与并发控制 | 298-414 |
| **CLI** | 命令行界面 | 417-481 |

---

## 📚 详细说明

### 核心类详解

#### 1. Config 类（配置管理）

**作用**：封装所有配置项，提供统一的访问接口。

```python
class Config:
    def __init__(self, config_path="config.yaml"):
        """加载 YAML 配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.data = yaml.safe_load(f)
```

**关键属性**：

| 属性 | 说明 | 数据来源 |
|------|------|----------|
| `api_key` | API 密钥 | `config.yaml` → `api.translation_api_key` |
| `api_base_url` | API 基础 URL | `config.yaml` → `api.translation_api_base_url` |
| `api_model` | 翻译模型名称 | `config.yaml` → `api.translation_api_model` |
| `input_dir` | 输入目录 | `config.yaml` → `paths.input_base` |
| `output_dir` | 输出目录 | `config.yaml` → `paths.output_base` |
| `qps` | 并发数 | `config.yaml` → `babeldoc.qps` |

**设计优势**：
- 使用 `@property` 装饰器，提供清晰的访问接口
- 集中管理配置，便于维护
- 类型安全，返回 `Path` 对象而非字符串

---

#### 2. GlossaryManager 类（术语库管理）

**作用**：加载 Excel 术语库，转换为 BabelDOC 可用的 CSV 格式。

```python
class GlossaryManager:
    def load_from_excel(self):
        """从 Excel 加载术语"""
        # 扫描 terminology/ 目录
        # 读取所有 .xlsx/.xls 文件
        # 提取第一列（英文）和第二列（中文）
        # 返回 {英文: 中文} 字典
```

**处理流程**：

```
1. 扫描 terminology/*.xlsx 文件
       ↓
2. 使用 openpyxl 读取每个工作表
       ↓
3. 跳过第一行（标题行）
       ↓
4. 提取每行的前两列
   - row[0]: 英文术语
   - row[1]: 中文翻译
       ↓
5. 存储到字典 glossary
       ↓
6. 导出为 CSV（BabelDOC 格式）
   格式: source,target,tgt_lng
         machine learning,机器学习,zh-CN
```

**关键方法**：

```python
def export_to_csv(self, glossary, output_path):
    """
    导出 CSV 格式术语库

    CSV 格式要求:
    - 列名: source, target, tgt_lng
    - source: 英文原文
    - target: 中文翻译
    - tgt_lng: 目标语言代码 (zh-CN)
    """
```

---

#### 3. BabelDOCCommandBuilder 类（命令构建器）

**作用**：根据配置生成 BabelDOC 完整的命令行参数。

```python
class BabelDOCCommandBuilder:
    BABELDOC_EXE = r"C:\ProgramData\anaconda3\envs\babeldoc\Scripts\babeldoc.exe"

    def build(self, pdf_path, glossary_csv=None):
        """构建命令"""
```

**生成的命令示例**：

```bash
C:\ProgramData\anaconda3\envs\babeldoc\Scripts\babeldoc.exe \
    --files input/paper.pdf \
    --output output/ \
    --openai \
    --openai-model gemini-2.5-flash-lite \
    --openai-base-url https://liangjiewis.com/v1 \
    --openai-api-key sk-xxx \
    --qps 50 \
    --skip-scanned-detection \
    --glossary-files output/glossary.csv \
    --dual-translate-first \
    --no-watermark
```

**参数逻辑**：

| 配置项 | 生成的参数 | 说明 |
|--------|-----------|------|
| `pdf_modes: [translated_only]` | `--no-dual` | 不生成双语 PDF |
| `pdf_modes: [bilingual]` | `--no-mono` | 不生成纯译文 PDF |
| `translated_first: true` | `--dual-translate-first` | 双语 PDF 中译文在左 |
| `alternating_pages: true` | `--use-alternating-pages-dual` | 使用交替页面模式 |
| `watermark: false` | `--no-watermark` | 不添加水印 |

---

#### 4. PDFProcessor 类（PDF 处理器）

**作用**：处理单个 PDF 文件的完整翻译流程。

```python
class PDFProcessor:
    def __init__(self, config):
        self.config = config
        self.glossary_manager = GlossaryManager(config.terminology_dir)
        self.command_builder = BabelDOCCommandBuilder(config)
```

**处理流程**：

```
1. 加载术语库
   └─→ GlossaryManager.load_from_excel()
   └─→ GlossaryManager.export_to_csv()

2. 构建 BabelDOC 命令
   └─→ BabelDOCCommandBuilder.build()

3. 执行命令
   └─→ subprocess.run(cmd, timeout=3600)
        ├─ 实时显示输出（不使用 capture_output）
        ├─ 1 小时超时限制
        └─ 异常处理

4. 返回处理结果
   ├─ True: 成功
   └─ False: 失败/超时/异常
```

**关键代码段**：

```python
def process(self, pdf_path):
    # 1. 加载术语库
    glossary = self.glossary_manager.load_from_excel()
    glossary_csv = self.glossary_manager.export_to_csv(...)

    # 2. 构建命令
    cmd = self.command_builder.build(pdf_path, glossary_csv)

    # 3. 执行（实时输出）
    subprocess.run(cmd, check=True, timeout=3600, text=True)
```

---

#### 5. BatchProcessor 类（批量处理器）

**作用**：批量处理多个 PDF，支持并发和断点续传。

```python
class BatchProcessor:
    def __init__(self, config):
        self.config = config
        self.pdf_processor = PDFProcessor(config)
```

**处理流程**：

```
1. 扫描 PDF 文件
   └─→ scan_pdf_files()
        ├─ 递归扫描 input/**/*.pdf
        └─ 过滤临时文件 (_compressed, _part, temp_splits)

2. 断点续传检查
   └─→ is_completed(pdf_path)
        ├─ 检查 output/{name}_translated.pdf 是否存在
        ├─ 检查 output/{name}_dual.pdf 是否存在
        └─ 全部存在 → 跳过

3. 用户确认
   └─→ 显示待处理文件列表
   └─→ 等待用户输入 y/N

4. 并发处理
   └─→ ThreadPoolExecutor(max_workers=5)
        ├─ 提交所有任务到线程池
        ├─ as_completed() 等待任务完成
        └─ 实时显示进度

5. 统计结果
   └─→ 成功/失败/总计
```

**并发机制**：

```python
with ThreadPoolExecutor(max_workers=5) as executor:
    # 提交所有任务
    future_to_pdf = {
        executor.submit(self.pdf_processor.process, pdf): pdf
        for pdf in pdf_files
    }

    # 等待完成
    for future in as_completed(future_to_pdf):
        success = future.result()  # 获取处理结果
```

**设计特点**：
- 使用线程池实现并发（`ThreadPoolExecutor`）
- `max_workers` 可配置（默认 5）
- 实时显示进度，不等全部完成
- 异常隔离：单个文件失败不影响其他文件

---

### 执行流程

#### 单文件模式

```
用户: python babeldoc_workflow.py input/paper.pdf
    ↓
main()
    ├─ 解析命令行参数: sys.argv[1] = "input/paper.pdf"
    ├─ 加载配置: Config()
    └─ 创建处理器: PDFProcessor(config)
        ↓
PDFProcessor.process("input/paper.pdf")
    ├─ GlossaryManager.load_from_excel()
    │   └─→ 返回 {'machine learning': '机器学习', ...}
    ├─ GlossaryManager.export_to_csv()
    │   └─→ 生成 output/glossary.csv
    ├─ BabelDOCCommandBuilder.build()
    │   └─→ 生成命令列表
    └─ subprocess.run(cmd)
        └─→ 调用 BabelDOC 翻译
            ├─ 解析 PDF
            ├─ 翻译文本（调用 API）
            ├─ 应用术语库
            └─ 生成 PDF
                ├─ output/paper_translated.pdf
                └─ output/paper_dual.pdf
```

#### 批量模式

```
用户: python babeldoc_workflow.py
    ↓
main()
    ├─ 无命令行参数 → 批量模式
    └─ 创建处理器: BatchProcessor(config)
        ↓
BatchProcessor.process()
    ├─ scan_pdf_files()
    │   └─→ [input/a.pdf, input/b.pdf, input/c.pdf]
    ├─ 断点续传检查
    │   ├─ is_completed(a.pdf) → True (跳过)
    │   ├─ is_completed(b.pdf) → False
    │   └─ is_completed(c.pdf) → False
    │       └─→ 待处理: [b.pdf, c.pdf]
    ├─ 用户确认 (y/N)
    └─ ThreadPoolExecutor
        ├─ Thread 1: PDFProcessor.process(b.pdf)
        └─ Thread 2: PDFProcessor.process(c.pdf)
            ├─ 并发执行
            └─ 实时显示进度
                ↓
        统计结果
        ├─ 成功: 2
        ├─ 失败: 0
        └─ 总计: 2
```

---

## ⚙️ 配置文件

`config.yaml` 结构说明：

```yaml
# API 配置
api:
  translation_api_key: "sk-xxx"              # API 密钥
  translation_api_base_url: "https://..."   # API 地址
  translation_api_model: "gemini-2.5-flash-lite"  # 模型名称

# 路径配置
paths:
  input_base: "input/"                       # PDF 输入目录
  output_base: "output/"                     # 翻译输出目录
  terminology_folder: "terminology/"         # 术语库目录

# BabelDOC 配置
babeldoc:
  pdf_modes:                                 # PDF 输出模式
    - translated_only                        # 生成纯译文 PDF
    - bilingual                              # 生成双语对照 PDF

  bilingual_settings:                        # 双语 PDF 配置
    translated_first: true                   # 译文在左/上
    alternating_pages: false                 # 并排显示
    watermark: false                         # 不添加水印

  qps: 50                                    # 翻译并发数
  skip_scanned_detection: true               # 跳过扫描检测

# 批处理配置
batch:
  max_concurrent_files: 5                    # 同时处理文件数
  resume_enabled: true                       # 启用断点续传
```

---

## 📖 使用示例

### 示例 1：批量翻译论文

```bash
# 1. 将 PDF 放入 input/
cp ~/Downloads/*.pdf input/

# 2. （可选）添加术语库
# 在 terminology/ 创建 terms.xlsx
# 格式：第一列英文，第二列中文

# 3. 运行批量处理
python babeldoc_workflow.py

# 输出:
# 找到 10 个PDF文件
# 待处理: 10 个文件
#   1. paper1.pdf
#   2. paper2.pdf
#   ...
# 确认开始批量处理？[y/N]: y
#
# 开始处理（并发数: 5）...
# ✓ 完成: paper1.pdf
# ✓ 完成: paper2.pdf
# ...
```

### 示例 2：单文件翻译

```bash
python babeldoc_workflow.py input/important_paper.pdf

# 输出:
# ============================================================
# 处理文件: input/important_paper.pdf
# ============================================================
#
# 加载术语库...
# ✓ 加载了 50 条术语
#
# 开始翻译...
# [BabelDOC 实时输出...]
# ✓ 翻译完成！
```

### 示例 3：修改配置

```bash
# 只生成双语 PDF
vim config.yaml
# 修改:
#   pdf_modes:
#     - bilingual

# 降低并发数（节省资源）
# 修改:
#   qps: 10
#   max_concurrent_files: 2
```

---

## ❓ 常见问题

### Q1: 如何查看翻译进度？

**A**: 新版本会实时显示 BabelDOC 的输出，包括：
- PDF 解析进度
- 翻译页面数
- 当前处理状态

### Q2: 翻译卡住了怎么办？

**A**:
1. 检查网络连接（需要访问 API）
2. 查看 API 密钥是否正确
3. 降低 `qps` 值（可能被限流）
4. 按 `Ctrl+C` 中断，重新运行（支持断点续传）

### Q3: 如何添加自定义术语？

**A**:
1. 在 `terminology/` 目录创建 Excel 文件
2. 格式：
   - 第一行：标题（会被跳过）
   - 第二列开始：英文 | 中文
3. 示例：

   | English | 中文 |
   |---------|------|
   | machine learning | 机器学习 |
   | deep learning | 深度学习 |

### Q4: 输出的 PDF 在哪里？

**A**: `output/` 目录，文件名格式：
- `{原文件名}_translated.pdf` - 纯译文
- `{原文件名}_dual.pdf` - 双语对照

### Q5: 如何修改双语 PDF 排版？

**A**: 编辑 `config.yaml`:
```yaml
bilingual_settings:
  translated_first: true      # false 则原文在左
  alternating_pages: true     # true 则交替页面显示
  watermark: true             # 添加水印
```

### Q6: 内存不足怎么办？

**A**: 降低并发数：
```yaml
batch:
  max_concurrent_files: 2     # 默认 5，改为 2 或 1
```

### Q7: 如何禁用断点续传？

**A**:
```yaml
batch:
  resume_enabled: false
```

---

## 🔧 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.11 | 主语言 |
| BabelDOC 0.5.22 | PDF 翻译引擎 |
| PyYAML | 配置文件解析 |
| openpyxl | Excel 术语库读取 |
| ThreadPoolExecutor | 并发处理 |
| subprocess | 调用 BabelDOC |

---

## 📄 许可

本项目使用 MIT 许可证。

BabelDOC 是第三方工具，请遵守其许可协议：
https://github.com/opendatalab/BabelDOC

---

## 🙏 致谢

- [BabelDOC](https://github.com/opendatalab/BabelDOC) - 强大的 PDF 翻译工具
- [OpenDataLab](https://opendatalab.com/) - BabelDOC 开发团队

---

**现在可以开始使用了！**

```bash
python babeldoc_workflow.py
```
