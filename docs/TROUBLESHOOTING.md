# 故障排查指南 / Troubleshooting Guide

📖 [返回主文档](../README.md) | 📚 [系统架构](ARCHITECTURE.md) | ⚙️ [配置说明](CONFIGURATION.md)

---

## 📑 目录

- [1. 常见问题](#1-常见问题-common-issues)
  - [1.1 程序启动相关](#11-程序启动相关)
  - [1.2 API调用相关](#12-api调用相关)
  - [1.3 文件处理相关](#13-文件处理相关)
  - [1.4 翻译相关](#14-翻译相关)
  - [1.5 输出生成相关](#15-输出生成相关)
  - [1.6 断点续传相关](#16-断点续传相关)
  - [1.7 图片处理相关](#17-图片处理相关)
- [2. 日志文件](#2-日志文件-log-files)
  - [2.1 日志目录结构](#21-日志目录结构)
  - [2.2 日志文件说明](#22-日志文件说明)
  - [2.3 日志级别](#23-日志级别)
- [3. 错误代码快速参考](#3-错误代码快速参考-error-codes)
  - [3.1 API错误](#31-api错误)
  - [3.2 文件系统错误](#32-文件系统错误)
  - [3.3 数据验证错误](#33-数据验证错误)
- [4. 恢复工具](#4-恢复工具-recovery-tools)
  - [4.1 进度恢复](#41-进度恢复)
  - [4.2 占位符泄漏修复](#42-占位符泄漏修复)
  - [4.3 缓存清理](#43-缓存清理)
- [5. 性能诊断](#5-性能诊断-performance-diagnostics)
  - [5.1 慢速处理](#51-慢速处理)
  - [5.2 高内存占用](#52-高内存占用)
  - [5.3 API超时](#53-api超时)
- [6. 已知问题和限制](#6-已知问题和限制-known-issues)
- [7. v2.12.3 修复的已知 Bug](#7-v2123-修复的已知-bug)

---

## 1. 常见问题 / Common Issues

### 1.1 程序启动相关

#### Q: 程序启动后卡住或无响应

**可能原因**：
- API配置错误
- 网络连接问题
- 缺少必要的Python包
- 日志文件权限问题

**解决方案**：
1. 检查API配置是否正确（`config.py`）：
   ```python
   PDF_API_KEY = "your-api-key"  # 确保有效
   PDF_API_BASE_URL = "https://..."  # 确保可访问
   PDF_API_MODEL = "gemini-2.5-flash"  # 确保模型名称正确
   ```

2. 测试网络连接：
   ```bash
   # 测试API连接
   curl -X POST https://your-api-url/v1/chat/completions \
     -H "Authorization: Bearer your-api-key"
   ```

3. 检查Python包安装：
   ```bash
   pip install -r requirements.txt
   ```

4. 查看启动日志：
   ```bash
   cat logs/main_YYYYMMDD.log
   ```

#### Q: ImportError 或 ModuleNotFoundError

**可能原因**：
- Python版本不匹配（需要Python 3.13+）
- 缺少依赖包
- 虚拟环境未激活

**解决方案**：
1. 检查Python版本：
   ```bash
   python --version  # 应该是 3.13 或更高
   ```

2. 重新安装依赖：
   ```bash
   pip install -r requirements.txt --force-reinstall
   ```

3. 检查是否在虚拟环境中：
   ```bash
   which python  # 应该指向虚拟环境
   ```

### 1.2 API调用相关

#### Q: API调用失败（401 Unauthorized）

**可能原因**：
- API密钥无效或过期
- API密钥格式错误
- 权限不足

**解决方案**：
1. 验证API密钥：
   - 登录API提供商控制台
   - 检查密钥是否有效
   - 检查是否有足够的配额

2. 检查密钥格式：
   ```python
   # config.py
   PDF_API_KEY = "sk-..."  # OpenAI格式
   # 或
   PDF_API_KEY = "AIza..."  # Google格式
   ```

3. 检查权限设置：
   - 确保API密钥有访问所需模型的权限

#### Q: API调用超时（503 Service Unavailable）

**可能原因**：
- API服务暂时不可用
- 网络延迟过高
- 请求过大导致超时

**解决方案**：
1. 等待并重试（系统会自动重试10次）
2. 增加超时时间：
   ```python
   # config.py
   PDF_API_TIMEOUT = 3600  # 从1800秒增加到3600秒
   ```

3. 减少批次大小：
   ```python
   # config.py
   PAGES_PER_BATCH = 4  # 从6减少到4
   ```

4. 检查网络状况：
   ```bash
   ping api.openai.com  # 或你的API提供商域名
   ```

#### Q: API速率限制（429 Too Many Requests）

**可能原因**：
- 请求速率超过API限制
- 并发数过高
- 短时间内发送过多请求

**解决方案**：
1. 降低并发数：
   ```python
   # config.py
   MAX_WORKERS = 50  # 从100降低到50
   TRANSLATION_MAX_WORKERS = 50
   HTML_CONCURRENT_REQUESTS = 50
   ```

2. 增加请求间隔：
   ```python
   # config.py
   REQUEST_INTERVAL = 0.5  # 从0.1增加到0.5秒
   ```

3. 等待速率限制窗口结束（通常1分钟）

### 1.3 文件处理相关

#### Q: 输出文件不完整或损坏

**可能原因**：
- 磁盘空间不足
- 文件权限问题
- 处理中断（如进程被杀）
- 缓存数据损坏

**解决方案**：
1. 检查磁盘空间：
   ```bash
   df -h  # Linux/macOS
   # 或
   dir  # Windows
   ```

2. 检查文件权限：
   ```bash
   ls -la output/  # 确保有写权限
   ```

3. 查看缓存文件：
   ```bash
   # 检查JSON缓存
   ls -lh output/json/<filename>/
   ```

4. 使用恢复工具：
   ```bash
   python recover_progress_from_json.py
   ```

#### Q: PDF提取结果为空

**可能原因**：
- PDF文件损坏或加密
- PDF格式不支持
- API返回空内容
- 验证失败导致结果被丢弃

**解决方案**：
1. 检查PDF文件：
   ```bash
   # 使用PyMuPDF检查
   python -c "import fitz; doc=fitz.open('file.pdf'); print(len(doc))"
   ```

2. 查看LLM响应日志：
   ```bash
   cat output/json/<filename>/batches/llm_response_batch_*.json
   ```

3. 检查是否有验证错误：
   ```bash
   grep "验证失败" logs/pdf_extractor_*.log
   ```

4. 尝试减小批次大小：
   ```python
   PAGES_PER_BATCH = 3  # 减少到3页
   ```

### 1.4 翻译相关

#### Q: 翻译失败或返回空白

**可能原因**：
- API配额不足
- 术语库格式错误
- 敏感词被过滤
- API返回格式错误

**解决方案**：
1. 检查API配额：
   - 登录API控制台查看剩余额度
   - 检查是否超出速率限制

2. 检查术语库格式：
   ```python
   # 术语库应为 .xlsx 文件，包含两列：英文术语 | 中文术语
   # 检查是否有空行或格式错误
   ```

3. 查看敏感词过滤日志：
   ```bash
   grep "敏感词" logs/translator_*.log
   ```

4. 检查翻译缓存：
   ```bash
   ls output/json/<filename>/.cache/translation_cache/
   ```

5. 清除缓存并重试：
   ```bash
   rm -rf output/json/<filename>/.cache/translation_cache/
   ```

#### Q: 翻译结果质量差

**可能原因**：
- 术语库未生效
- Temperature参数设置不当
- 上下文不足

**解决方案**：
1. 确认术语库已加载：
   ```bash
   grep "术语库" logs/translator_*.log
   ```

2. 调整Temperature参数：
   ```python
   # config.py
   TRANSLATION_TEMPERATURE = 0.1  # 降低温度，提高确定性
   ```

3. 增加上下文窗口（如果支持）

### 1.5 输出生成相关

#### Q: HTML生成失败

**可能原因**：
- 文章内容格式错误
- 图片路径问题
- 缓存损坏

**解决方案**：
1. 检查文章JSON格式：
   ```bash
   cat output/json/<filename>/articles/final_articles_*.json | jq .
   ```

2. 检查图片是否存在：
   ```bash
   ls output/image/<filename>/
   ```

3. 清除HTML缓存：
   ```bash
   rm -rf output/json/<filename>/.cache/html_fragments/
   ```

4. 查看HTML生成日志：
   ```bash
   cat logs/components/html_generator_*.log
   ```

#### Q: PDF/DOCX生成失败

**可能原因**：
- WeasyPrint依赖缺失
- 字体问题
- HTML格式错误

**解决方案**：
1. 检查WeasyPrint依赖：
   ```bash
   pip list | grep -i weasy
   ```

2. 安装系统依赖（如果需要）：
   ```bash
   # Ubuntu/Debian
   sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0

   # macOS
   brew install pango
   ```

3. 检查字体配置：
   - 确保系统有中文字体

4. 查看生成日志：
   ```bash
   cat logs/components/pdf_generator_*.log
   ```

### 1.6 断点续传相关

#### Q: 选择"重新处理"时仍然使用了缓存

**说明**：这是Cache-First架构的设计行为，不是bug。

**原理**：
- 缓存是文件系统级别的，独立于session状态
- 只要PDF内容未变，缓存就有效

**优点**：
- 即使"新任务"，也可以复用之前的提取结果
- 节省大量API调用和处理时间

**缺点**：
- 如果想完全重新处理，需要手动清理缓存

**解决方法**：
```bash
# 方法1：删除特定文件的缓存
rm -rf output/json/<pdf-name>/

# 方法2：删除所有缓存（慎用）
rm -rf output/

# 方法3：只删除特定阶段的缓存
rm -rf output/json/<pdf-name>/batches/  # 删除批次缓存
rm -rf output/json/<pdf-name>/.cache/translation_cache/  # 删除翻译缓存
```

#### Q: 断点续传后进度不准确

**可能原因**：
- 进度文件损坏
- 缓存与进度不一致
- 11阶段状态未正确更新

**解决方案**：
1. 使用验证功能（自动执行）：
   - 程序会在恢复会话时自动验证缓存一致性
   - 查看验证输出：`[验证] 检查进度数据一致性...`

2. 如果验证失败，使用恢复工具：
   ```bash
   python recover_progress_from_json.py
   ```

3. 查看进度文件：
   ```bash
   cat progress/session_*.json | jq .file_progress
   ```

### 1.7 图片处理相关

#### Q: 看到很多"无法获取图片bbox信息"的警告

**版本说明**：v2.10.1已修复此bug

**旧版本（v2.10.0及之前）**：
- 图片位置获取成功率：0%（全部失败）
- 原因：`page.get_image_bbox(xref)` 参数错误（应该传字符串名称，实际传了整数xref）

**新版本（v2.10.1+）**：
- 图片位置获取成功率：90%+（正常）
- 修复：使用正确的API参数 `page.get_image_bbox(img_name)`

**剩余警告说明**：
- 部分PDF图片（如背景图、内联图片、水印）确实没有位置信息
- 这属于正常现象，系统会使用默认中心位置（0.5, 0.5）

**解决方案**：
1. 升级到v2.10.1+版本
2. 如果仍有少量警告（<10%），属于正常现象，无需处理

#### Q: AI图片描述为空或不准确

**可能原因**：
- LLM未遵循图片描述指令（模型限制）
- 图片质量过低
- 图片与文章关联性弱

**诊断方法**：
1. 查看调试日志：
   ```
   🔍 [Debug] 使用Multimodal模式：PDF + X 张图片
   🔍 [Debug] 已分配图片ID: image_1, image_2, ...
   🔍 [Debug] 开始验证 X 张图片的AI描述...
   ```

2. 检查LLM返回：
   ```
   # 正常情况
   ✅ [Debug] LLM总共返回了 3 个图片描述

   # 异常情况
   ⚠️ [Debug] LLM返回的所有文章的images数组都是空的！
   ```

**解决方案**：
1. 如果LLM未生成描述（模型限制）：
   - 尝试其他模型：`PDF_API_MODEL = "gemini-2.5-pro"`
   - 或暂时接受无AI描述的图片展示

#### Q: 图片提取失败："Invalid bandwriter header dimensions/setup"

**错误示例**：
```
页码 16, 图片索引 3: 提取失败 - code=4: Invalid bandwriter header dimensions/setup
页码 16, 图片索引 4: 提取失败 - code=4: Invalid bandwriter header dimensions/setup
```

**原因**：
- PDF中包含损坏或格式异常的嵌入图片
- PyMuPDF无法解码这类图片的二进制数据
- 这是PDF文件本身的问题，不是程序bug

**版本说明**：
- **v2.11.4之前**：单个损坏图片导致整个批次提取失败
- **v2.11.4+（修复）**：损坏图片会被自动跳过，不影响其他图片提取

**当前行为**（v2.11.4+）：
```
✅ 损坏图片：跳过并记录警告
✅ 其他图片：正常提取
✅ 批次处理：继续执行
```

**日志示例**：
```
⚠️ 页码 16, 图片索引 3: 图片数据损坏，跳过 - code=4: Invalid bandwriter header...
批次提取完成: 共 5 张图片（跳过 2 张损坏）
```

**解决方案**：
1. **推荐**：升级到v2.11.4+版本，损坏图片会自动跳过
2. 如果想修复原PDF：使用PDF编辑工具重新保存PDF（可能修复损坏图片）
3. 如果损坏图片很重要：尝试用其他PDF阅读器导出该图片

**无需操作**：
- 损坏图片已自动跳过，不影响整体处理流程
- 只要批次中有其他正常图片，处理就会继续

#### Q: 高并发下出现文件冲突错误

**错误示例**：
```
[WinError 183] 当文件已存在时，无法创建该文件: 'temp_page_images/page_1.png'
PermissionError: [WinError 32] 另一个程序正在使用此文件: 'temp_page_images'
Directory not empty: 'temp_page_images'
```

**原因**：
- 多个VisionImageProcessor实例同时写入相同的临时目录
- 高并发场景（20文件×100批次）导致文件名冲突
- Windows文件锁机制导致删除失败

**版本说明**：
- **v2.11.4之前**：所有实例共享 `temp_page_images/` 目录 → 频繁冲突
- **v2.11.4+（修复）**：每个实例使用唯一目录 `temp_page_images_{uuid}/` → 零冲突

**修复机制**：
```python
# 旧版本（共享目录）
temp_page_images/
  ├─ page_1.png  ← 实例A写入
  ├─ page_1.png  ← 实例B也写入（冲突！）

# 新版本（隔离目录）
temp_page_images_a1b2c3d4/
  └─ page_1.png  ← 实例A独立空间
temp_page_images_e5f6g7h8/
  └─ page_1.png  ← 实例B独立空间
```

**解决方案**：
1. **推荐**：升级到v2.11.4+版本
2. 验证是否已修复：
   ```bash
   # 处理过程中检查临时目录
   ls -la | grep temp_page_images

   # 应该看到多个带UUID后缀的目录
   temp_page_images_a1b2c3d4/
   temp_page_images_e5f6g7h8/
   ...
   ```

3. 如果仍有问题（极少见）：
   ```bash
   # 清理残留的临时目录
   rm -rf temp_page_images*

   # 重新运行程序
   python main.py
   ```

**自动清理**：
- 程序正常退出时自动删除所有临时目录
- 支持3次重试机制，处理Windows文件锁问题
- 清理失败时使用强制删除（`ignore_errors=True`）

2. 如果描述不准确：
   - 调整图片筛选标准（减少噪音图片）
   - 增加Vision API温度：`VISION_API_TEMPERATURE = 0.3`

#### Q: 图片重复或缺失

**可能原因**：
- 批次重叠导致重复提取
- 去重机制失效
- 图片提取失败

**解决方案**：
1. 检查去重日志：
   ```
   批次 1: 添加 5 张（跳过 0 张重复）
   批次 2: 添加 3 张（跳过 2 张重复）
   ```

2. 查看图片元数据：
   ```bash
   cat output/json/<filename>/batches/images_batch_*.json | jq .
   ```

3. 检查图片文件：
   ```bash
   ls -lh output/image/<filename>/batch_*/
   ```

---

## 2. 日志文件 / Log Files

### 2.1 日志目录结构

```
logs/
├── components/                    # 组件日志目录
│   ├── pdf_extractor_YYYYMMDD.log
│   ├── translator_YYYYMMDD.log
│   ├── html_generator_YYYYMMDD.log
│   ├── excel_generator_YYYYMMDD.log
│   ├── pdf_generator_YYYYMMDD.log
│   ├── docx_generator_YYYYMMDD.log
│   ├── image_extractor_YYYYMMDD.log
│   ├── image_cleaner_YYYYMMDD.log
│   └── batch_processor_YYYYMMDD.log
├── sessions/                      # 会话日志目录
│   └── session_YYYYMMDD_HHMMSS.log
└── main_YYYYMMDD.log             # 主程序日志
```

### 2.2 日志文件说明

| 日志文件 | 说明 | 用途 |
|---------|------|------|
| **main_YYYYMMDD.log** | 主程序日志 | 启动、会话创建、总体进度 |
| **session_*.log** | 会话详细日志 | 完整的执行记录，包括每个文件的11阶段状态变化 |
| **pdf_extractor_*.log** | PDF提取日志 | 批次处理、文章提取、LLM调用详情 |
| **translator_*.log** | 翻译日志 | 翻译任务、术语库匹配、失败重试 |
| **html_generator_*.log** | HTML生成日志 | HTML生成、图片嵌入、缓存使用 |
| **excel_generator_*.log** | Excel生成日志 | Excel文件生成状态 |
| **pdf_generator_*.log** | PDF生成日志 | PDF文件生成、WeasyPrint调用 |
| **image_extractor_*.log** | 图片提取日志 | 图片提取、清洗、元数据保存 |
| **batch_processor_*.log** | 批处理日志 | 文件级并发、格式生成并发 |

### 2.3 日志级别

| 级别 | 说明 | 示例场景 |
|------|------|----------|
| **DEBUG** | 详细调试信息 | API请求参数、JSON结构、验证细节 |
| **INFO** | 一般信息 | 处理进度、阶段完成、缓存命中 |
| **WARNING** | 警告信息 | 缓存验证失败、中等置信度选择、重试提示 |
| **ERROR** | 错误信息 | API调用失败、文件读写错误、验证失败 |
| **CRITICAL** | 严重错误 | 系统崩溃、致命异常 |

**调整日志级别**：

```python
# config.py
LOG_LEVEL = "DEBUG"  # 开发/调试时使用
# LOG_LEVEL = "INFO"  # 生产环境推荐
# LOG_LEVEL = "WARNING"  # 静默运行
```

---

## 3. 错误代码快速参考 / Error Codes

### 3.1 API错误

| 错误代码 | 说明 | 可重试 | 解决方案 |
|---------|------|--------|----------|
| **401** | Unauthorized（认证失败） | ❌ | 检查API密钥是否正确和有效 |
| **403** | Forbidden（权限不足） | ❌ | 检查API密钥权限和配额 |
| **404** | Not Found（资源不存在） | ❌ | 检查API端点URL是否正确 |
| **429** | Too Many Requests（速率限制） | ✅ | 降低并发数或增加请求间隔 |
| **500** | Internal Server Error（服务器错误） | ✅ | 等待并重试，检查API状态 |
| **502** | Bad Gateway（网关错误） | ✅ | 等待并重试 |
| **503** | Service Unavailable（服务不可用） | ✅ | 等待并重试（可能是服务维护） |
| **504** | Gateway Timeout（网关超时） | ✅ | 增加超时时间或减少请求大小 |

**重试策略**：
- **技术错误**（500, 502, 503, 504, 网络错误）：10次重试 + 指数退避
- **质量错误**（返回空、格式错误、验证失败）：3次快速重试
- **客户端错误**（401, 403, 404）：不重试，直接报错

### 3.2 文件系统错误

| 错误类型 | 说明 | 解决方案 |
|---------|------|----------|
| **FileNotFoundError** | 文件不存在 | 检查文件路径是否正确；恢复缓存 |
| **PermissionError** | 权限不足 | 检查文件/目录权限；关闭占用文件的程序 |
| **IOError** | I/O错误 | 检查磁盘空间；检查文件是否被锁定 |
| **JSONDecodeError** | JSON格式错误 | 使用备份恢复；清除损坏的缓存 |
| **OSError: [Errno 28]** | 磁盘空间不足 | 清理磁盘空间；删除旧缓存 |

### 3.3 数据验证错误

| 错误类型 | 说明 | 原因 | 解决方案 |
|---------|------|------|----------|
| **格式验证失败** | JSON结构不符合预期 | LLM返回格式错误 | 自动重试（JSONParser会要求LLM修复） |
| **存在性验证失败** | 引用的ID不存在 | LLM生成了不存在的ID | 自动丢弃无效条目 |
| **唯一性验证失败** | 检测到重复ID | LLM重复使用ID | 自动去重 |
| **页面范围验证失败** | 页码超出批次范围 | LLM返回了错误的页码 | 放宽验证阈值（±3页） |

---

## 4. 恢复工具 / Recovery Tools

### 4.1 进度恢复

**工具**：`recover_progress_from_json.py`

**用途**：从JSON缓存恢复进度，修复进度与文件不一致

**使用方法**：
```bash
python recover_progress_from_json.py
```

**功能**：
- 扫描所有输出文件
- 重建11阶段进度状态
- 修复不一致的进度标记

**适用场景**：
- 进度文件损坏
- 手动删除了部分输出文件
- 进度与实际文件不一致

### 4.2 占位符泄漏修复

**工具**：`check_and_fix_leaked_placeholders.py`

**用途**：检查并修复占位符泄漏到最终输出的问题

**使用方法**：
```bash
# 检查占位符泄漏
python check_and_fix_leaked_placeholders.py --check

# 自动修复
python check_and_fix_leaked_placeholders.py --fix
```

**功能**：
- 扫描所有输出文件
- 检测占位符（如 `{{PLACEHOLDER_001}}`）
- 替换为实际内容

**适用场景**：
- 发现HTML/PDF中有占位符
- 翻译质量异常（包含占位符）

### 4.3 缓存清理

**手动清理**：

```bash
# 清理特定文件的所有缓存
rm -rf output/json/<filename>/

# 清理特定阶段的缓存
rm -rf output/json/<filename>/batches/  # 批次缓存
rm -rf output/json/<filename>/.cache/translation_cache/  # 翻译缓存
rm -rf output/json/<filename>/.cache/html_fragments/  # HTML缓存

# 清理所有输出（慎用！）
rm -rf output/
```

**清理指南**：

| 缓存类型 | 位置 | 清理后果 | 建议清理场景 |
|---------|------|----------|-------------|
| **批次文章** | `batches/batch_*.json` | 重新提取文章 | PDF内容变更 |
| **图片元数据** | `batches/images_batch_*.json` | 重新处理图片 | 图片描述错误 |
| **翻译缓存** | `.cache/translation_cache/` | 重新翻译 | 翻译质量差 |
| **HTML缓存** | `.cache/html_fragments/` | 重新生成HTML | HTML格式错误 |
| **大纲缓存** | `outline/journal_outline.json` | 重新生成大纲 | 大纲错误 |

---

## 5. 性能诊断 / Performance Diagnostics

### 5.1 慢速处理

**症状**：
- 处理单个PDF需要1小时以上
- 大部分时间在等待API响应

**诊断方法**：
1. 检查日志中的API响应时间：
   ```bash
   grep "耗时" logs/components/pdf_extractor_*.log
   ```

2. 检查并发配置：
   ```python
   # config.py
   print(f"MAX_WORKERS: {MAX_WORKERS}")
   print(f"TRANSLATION_MAX_WORKERS: {TRANSLATION_MAX_WORKERS}")
   ```

3. 检查网络延迟：
   ```bash
   ping api.openai.com  # 或你的API域名
   ```

**优化方案**：
1. 增加并发数（如果API允许）：
   ```python
   MAX_WORKERS = 150  # 从100增加到150
   ```

2. 减少批次大小（提高并行度）：
   ```python
   PAGES_PER_BATCH = 4  # 从6减少到4
   ```

3. 使用更快的API端点或模型

### 5.2 高内存占用

**症状**：
- 内存占用超过4GB
- 系统变慢或OOM

**诊断方法**：
```python
import psutil
process = psutil.Process()
mem_mb = process.memory_info().rss / 1024 / 1024
print(f"内存占用: {mem_mb:.1f} MB")
```

**优化方案**：
1. 减少批次大小：
   ```python
   PAGES_PER_BATCH = 4  # 减少到4页
   ```

2. 降低文件级并发：
   ```python
   MAX_CONCURRENT_PDF_FILES = 10  # 从20减少到10
   ```

3. 及时释放资源：
   - 程序已实现自动内存管理
   - 如果仍有问题，重启程序继续处理（断点续传）

### 5.3 API超时

**症状**：
- 频繁出现"API调用超时"错误
- 超时率超过5%

**诊断方法**：
1. 查看超时日志：
   ```bash
   grep "超时" logs/components/pdf_extractor_*.log | wc -l
   ```

2. 检查超时配置：
   ```python
   print(f"PDF_API_TIMEOUT: {PDF_API_TIMEOUT}")
   print(f"TRANSLATION_TIMEOUT: {TRANSLATION_TIMEOUT}")
   ```

**解决方案**：
1. 增加超时时间：
   ```python
   # config.py
   PDF_API_TIMEOUT = 3600  # 从1800秒增加到3600秒（1小时）
   TRANSLATION_TIMEOUT = 600  # 从300秒增加到600秒（10分钟）
   ```

2. 减少批次大小（减少单次请求数据量）：
   ```python
   PAGES_PER_BATCH = 3  # 减少到3页
   ```

3. 检查网络状况：
   ```bash
   ping api.openai.com
   traceroute api.openai.com
   ```

---

## 6. 已知问题和限制 / Known Issues

### 6.1 平台相关

| 问题 | 影响平台 | 说明 | 解决方案 |
|------|---------|------|----------|
| **文件路径分隔符** | Windows | 路径使用 `\` vs `/` 不一致 | 程序已自动标准化为 `/` |
| **PermissionError** | Windows | 文件被占用导致删除失败 | 关闭编辑器/查看器；等待后重试 |
| **WeasyPrint依赖** | macOS | 缺少Pango依赖 | `brew install pango` |
| **字体缺失** | Linux | 缺少中文字体 | 安装中文字体包 |

### 6.2 API限制

| 问题 | 说明 | 解决方案 |
|------|------|----------|
| **Token限制** | Gemini 2.5 Flash: 65536 tokens | 减少批次大小；使用pro模型 |
| **速率限制** | OpenAI: 60 req/min | 降低并发数；使用专用端点 |
| **响应超时** | 某些API不稳定 | 增加重试次数；增加超时时间 |
| **格式不一致** | LLM有时不遵循指令 | 使用JSONParser自动修复 |

### 6.3 功能限制

| 功能 | 限制 | 说明 |
|------|------|------|
| **PDF提取** | 仅支持文本PDF | 扫描版PDF需要OCR预处理 |
| **图片描述** | 依赖LLM能力 | 部分模型可能不生成描述 |
| **术语库** | 仅支持完整单词匹配 | 不支持模糊匹配或词形变化 |
| **敏感词过滤** | 完全匹配，不使用正则 | 避免误判；支持长词优先 |

### 6.4 已修复的历史Bug

这些bug已在最新版本修复，列出供参考：

| Bug | 版本 | 说明 | 修复版本 |
|-----|------|------|---------|
| **图片bbox获取失败** | ≤v2.10.0 | API参数错误，成功率0% | v2.10.1 |
| **HTML标题显示文件名** | ≤v2.8.5 | Prompt引入了文件名 | v2.8.5 |
| **占位符泄漏** | ≤v2.8.4 | 翻译时占位符混入输出 | v2.8.4 |
| **进度数据不一致** | ≤v2.10.0 | 依赖列表而非文件系统 | v2.10.0 |

---

## 7. v2.12.3 修复的已知 Bug

### 7.1 运行时崩溃类（CRITICAL）

#### Q: 生成 PDF/DOCX 时报 `AttributeError: 'PDFGenerator' object has no attribute '_is_file_locked'`

**原因**：`pdf_generator.py` 和 `docx_generator.py` 中调用了 `_is_file_locked()` 和 `_remove_file_with_retry()` 方法，但这两个方法从未被定义。当输出目录已存在同名文件时必然触发。

**修复版本**：v2.12.3 — 已添加两个方法的完整实现。

---

#### Q: `docx_generator.py` 报 `AttributeError: 'DOCXGenerator' object has no attribute '_set_formal_fonts'`

**原因**：`_generate_docx()` 末尾调用了 `_set_formal_fonts()` 但该方法未定义。

**修复版本**：v2.12.3 — 已添加实现，`python-docx` 未安装时降级为警告而非崩溃。

---

#### Q: 程序处理大批量文件时卡死不动，CPU 占用 100%

**原因**：`core/pdf_utils.py` 的 `split_to_batches()` 中，若 `overlap_pages >= pages_per_batch`，步长 `step` 为 0 或负数，导致 `while start_page < total_pages` 无限循环。

**修复版本**：v2.12.3 — 添加 guard，`step <= 0` 时立即抛出 `ValueError` 并给出明确提示。

---

#### Q: Sequential 模式下处理一段时间后所有任务卡住，无任何输出

**原因**：`pipeline/file_processor.py` 的信号量释放逻辑有缺陷：当 `used_file_slot=True` 但 `file_id=None` 时，两个信号量都不会被释放，导致后续所有任务永久阻塞（死锁）。

**修复版本**：v2.12.3 — 修复 finally 块，确保任何情况下都能释放恰好一个信号量。

---

### 7.2 稳定性类（HIGH）

#### Q: Batch 模式下某个文件卡住后整个程序不退出

**原因**：`pipeline/file_processor.py` 的 `future.result()` 没有设置超时，任务卡死时主线程永久等待。

**修复版本**：v2.12.3 — 改为 `future.result(timeout=600)`，超时后跳过该文件并继续。

---

#### Q: 余额不足时程序仍然重试 10 次，浪费大量时间

**原因**：`core/logger.py` 的 `is_retryable_error()` 对所有错误默认返回 `True`（重试），包括余额不足和代码 bug 类错误。

**修复版本**：v2.12.3 — 余额不足、`TypeError`、`AttributeError`、`ValueError` 改为不重试，立即失败。

---

### 7.3 正确性类（MEDIUM）

#### Q: 图片清洗时所有图片都被过滤掉

**原因**：`processors/image_processor.py` 中当图片 `height=0` 时，`aspect_ratio` 被设为 `0`，而 `0 < min_ratio` 恒为真，导致所有图片被错误过滤。

**修复版本**：v2.12.3 — `height=0` 时直接过滤（无效图片），不再计算宽高比。

---

## 🔗 相关文档

- 📚 [系统架构](ARCHITECTURE.md) - 理解系统设计和数据流
- ⚙️ [配置说明](CONFIGURATION.md) - 调优参数和性能优化
- 🖼️ [图片处理](IMAGE_PROCESSING.md) - 图片处理详细流程
- 🔧 [Vision API](VISION_API.md) - Vision API集成和最佳实践

---

📖 [返回主文档](../README.md)
