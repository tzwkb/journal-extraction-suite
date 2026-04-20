# 模块化开发指南 / Modular Development Guide

📖 [返回主文档](../README.md) | 📚 [系统架构](ARCHITECTURE.md) | 🔄 [工作流程](WORKFLOW.md)

---

> **Version**: 1.0
> **Last Updated**: 2025-01
> **Purpose**: 确保代码一致性、可维护性和可扩展性的架构指南

---

## 📚 目录 / Table of Contents

1. [架构概览 / Architecture Overview](#架构概览--architecture-overview)
2. [模块分类 / Module Categories](#模块分类--module-categories)
3. [设计原则 / Design Principles](#设计原则--design-principles)
4. [核心工具参考 / Core Utilities Reference](#核心工具参考--core-utilities-reference)
5. [添加新功能指南 / Adding New Features](#添加新功能指南--adding-new-features)
6. [错误处理模式 / Error Handling Patterns](#错误处理模式--error-handling-patterns)
7. [进度监控模式 / Progress Monitoring](#进度监控模式--progress-monitoring)
8. [最佳实践 / Best Practices](#最佳实践--best-practices)
9. [代码示例 / Code Examples](#代码示例--code-examples)

---

## 架构概览 / Architecture Overview

### 系统分层架构 / System Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     工作流层 / Workflow Layer                │
│  (extractors/pdf_extractor.py, generators/html_generator.py, etc.) │
│  - 主流程编排 / Main process orchestration                   │
│  - 用户交互 / User interaction                              │
│  - 进度监控 / Progress monitoring (HeartbeatMonitor)        │
└──────────────────────┬──────────────────────────────────────┘
                       │ calls / 调用
┌──────────────────────▼──────────────────────────────────────┐
│                   功能模块层 / Functional Module Layer        │
│  (processors/image_processor.py, processors/vision_processor.py, etc.) │
│  - 特定领域功能 / Domain-specific functionality             │
│  - 可复用组件 / Reusable components                         │
│  - 无业务流程 / No business flow                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ uses / 使用
┌──────────────────────▼──────────────────────────────────────┐
│                    核心工具层 / Core Utility Layer           │
│  (core/pdf_utils.py, core/logger.py, logger.py)         │
│  - 通用工具函数 / Generic utility functions                 │
│  - 跨模块共享 / Cross-module shared resources               │
│  - 零业务逻辑 / Zero business logic                         │
└─────────────────────────────────────────────────────────────┘
```

### 关键设计理念 / Key Design Philosophy

1. **职责分离 (Separation of Concerns)**:
   - 工作流脚本 = 流程编排 (Workflow scripts = Orchestration)
   - 功能模块 = 可复用能力 (Functional modules = Reusable capabilities)
   - 核心工具 = 通用基础设施 (Core utilities = Generic infrastructure)

2. **DRY 原则 (Don't Repeat Yourself)**:
   - 重复代码必须提取到共享模块
   - 优先使用现有工具而非重新实现

3. **一致性优先 (Consistency First)**:
   - 所有模块使用统一的错误处理 (`NetworkErrorHandler`)
   - 所有长时间操作使用统一的进度监控 (`HeartbeatMonitor`)
   - 所有JSON解析使用统一的重试机制 (`JSONParser`)

---

## 模块分类 / Module Categories

### 🔄 工作流脚本 / Workflow Scripts

**特征 / Characteristics**:
- 包含主要业务流程 (Contains main business flow)
- 直接与用户交互 (Direct user interaction)
- 协调多个功能模块 (Coordinates multiple functional modules)
- 拥有 `HeartbeatMonitor` (Has `HeartbeatMonitor` for long-running tasks)

**文件列表 / Files**:
| 文件 / File | 职责 / Responsibility |
|-------------|---------------------|
| `extractors/pdf_extractor.py` | PDF文章提取主流程 / Main PDF extraction workflow |
| `generators/html_generator.py` | HTML生成主流程 / Main HTML generation workflow |
| `processors/translator.py` | 文章翻译主流程 / Main translation workflow |
| `extractors/docx_extractor.py` | DOCX文章提取主流程 / Main DOCX extraction workflow |

**开发规范 / Development Rules**:
- ✅ **应该 (Should)**: 编排流程、处理用户输入、显示进度、保存检查点
- ❌ **不应该 (Should NOT)**: 实现底层算法、重复实现工具函数

---

### 🧩 功能模块 / Functional Modules

**特征 / Characteristics**:
- 封装特定领域功能 (Encapsulates domain-specific functionality)
- 被工作流脚本调用 (Called by workflow scripts)
- 可独立测试 (Independently testable)
- 无用户交互逻辑 (No user interaction logic)

**文件列表 / Files**:
| 文件 / File | 职责 / Responsibility |
|-------------|---------------------|
| `processors/vision_processor.py` | Vision AI图像分析 / Vision AI image analysis |
| `processors/image_processor.py` | PDF图片提取 / PDF image extraction |
| `processors/image_processor.py` | 图片质量过滤 / Image quality filtering |
| `core/pdf_utils.py` | PDF预处理 / PDF preprocessing |
| `core/pdf_utils.py` | PDF批次管理 / PDF batch management |

**开发规范 / Development Rules**:
- ✅ **应该 (Should)**: 实现可复用功能、返回结构化数据、处理内部错误
- ❌ **不应该 (Should NOT)**: 添加 `HeartbeatMonitor`、直接打印进度、访问全局状态

---

### 🛠️ 核心工具 / Core Utilities

**特征 / Characteristics**:
- 提供通用基础设施 (Provides generic infrastructure)
- 零业务逻辑 (Zero business logic)
- 跨所有模块使用 (Used across all modules)
- 高度稳定 (Highly stable)

**文件列表 / Files**:
| 文件 / File | 职责 / Responsibility |
|-------------|---------------------|
| `core/pdf_utils.py` | JSON解析和清理 / JSON parsing and cleaning |
| `core/logger.py` | 响应验证和错误分类 / Response validation and error classification |
| `core/logger.py` | 日志记录和心跳监控 / Logging and heartbeat monitoring |
| `config.py` | 配置管理 / Configuration management |

**开发规范 / Development Rules**:
- ✅ **应该 (Should)**: 高度通用、完全无状态、全面的文档和测试
- ❌ **不应该 (Should NOT)**: 依赖特定业务逻辑、包含硬编码路径、修改全局状态

---

## 设计原则 / Design Principles

### 1. 代码复用优先 / Code Reuse First

**❌ 错误示范 / Bad Example**:
```python
# 在 processors/vision_processor.py 中重复实现JSON重试
def _parse_json_with_retry(self, response: str):
    for attempt in range(10):
        try:
            return json.loads(response)
        except:
            # 重试逻辑...
```

**✅ 正确示范 / Good Example**:
```python
# 使用现有的统一工具
from core.pdf_utils import JSONParser

result = JSONParser.parse_with_llm_retry(
    initial_response=response,
    llm_fix_callback=self._fix_callback,
    pdf_bytes=None,
    expected_type='object',
    max_retries=10
)
```

**规则 / Rule**: 在实现新功能前，先检查 `core/pdf_utils.py`、`core/logger.py` 是否已有相关工具。

---

### 2. 错误处理一致性 / Error Handling Consistency

**所有 API 调用必须使用 `NetworkErrorHandler` / All API calls must use `NetworkErrorHandler`**:

**✅ 标准模式 / Standard Pattern**:
```python
from core.logger import NetworkErrorHandler
import time

last_error = None
for attempt in range(max_retries):
    try:
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    except Exception as e:
        last_error = e

        # 统一错误分类 / Unified error classification
        should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

        if should_retry and attempt < max_retries - 1:
            wait_time = retry_delay * (2 ** attempt)  # 指数退避 / Exponential backoff
            logger.warning(f"{error_type}, 重试中... ({attempt+1}/{max_retries})")
            time.sleep(wait_time)
            continue
        else:
            logger.error(f"{error_type} (不可重试)")
            break

raise Exception(f"API调用失败: {last_error}")
```

**优势 / Benefits**:
- ✅ 统一的错误分类 (Unified error classification)
- ✅ 一致的日志格式 (Consistent log format)
- ✅ 智能重试策略 (Intelligent retry strategy)

---

### 3. 进度监控规范 / Progress Monitoring Standards

**仅在工作流脚本使用 `HeartbeatMonitor` / Only use `HeartbeatMonitor` in workflow scripts**:

**✅ 正确位置 / Correct Usage** (in `extractors/pdf_extractor.py`):
```python
from core.logger import HeartbeatMonitor

# 启动心跳监控 / Start heartbeat monitor
heartbeat_monitor = HeartbeatMonitor(
    task_name="PDF提取",
    total=total_batches,
    interval_seconds=30
)
heartbeat_monitor.start()

# 处理批次 / Process batches
for batch in batches:
    # ... 处理逻辑 ...
    heartbeat_monitor.update(completed_count)

# 停止心跳 / Stop heartbeat
heartbeat_monitor.stop()
```

**❌ 错误位置 / Wrong Usage** (in utility modules like `image_extractor.py`):
```python
# ❌ 不要在功能模块中添加 HeartbeatMonitor
# 功能模块不知道全局上下文（总数、任务名）
def extract_images(self, pdf_path):
    monitor = HeartbeatMonitor(...)  # ❌ 错误！
```

**规则 / Rule**:
- ✅ 工作流脚本 = 有 `HeartbeatMonitor`
- ❌ 功能模块/核心工具 = 无 `HeartbeatMonitor`

---

## 核心工具参考 / Core Utilities Reference

### 1. `core/pdf_utils.py` - JSON 解析工具

#### `JSONParser.parse_with_llm_retry()`

**用途 / Purpose**: 解析 LLM 响应的 JSON，失败时自动请求 LLM 修复

**签名 / Signature**:
```python
@staticmethod
def parse_with_llm_retry(
    initial_response: str,
    llm_fix_callback: Callable[[bytes, str], str],
    pdf_bytes: bytes,
    expected_type: str = 'array',
    max_retries: int = 10,
    retry_on_callback_error: bool = False
) -> Union[Dict, List]
```

**参数说明 / Parameters**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `initial_response` | `str` | LLM的初始响应 |
| `llm_fix_callback` | `Callable` | 修复回调函数，签名: `(pdf_bytes, fix_prompt) -> str` |
| `pdf_bytes` | `bytes` | PDF字节流 (如果不需要可传 `None`) |
| `expected_type` | `str` | `'array'` 或 `'object'` |
| `max_retries` | `int` | 最大修复重试次数 |
| `retry_on_callback_error` | `bool` | **新增**: 回调失败时是否等待5秒后重试（用于网络不稳定场景） |

**使用场景 / Use Cases**:
1. **PDF 提取** (`extractors/pdf_extractor.py`):
   - `retry_on_callback_error=False` (默认)
   - 回调失败直接报错

2. **Vision API** (`processors/vision_processor.py`):
   - `retry_on_callback_error=True`
   - 回调失败等待5秒后重试（网络波动）

**代码示例 / Example**:
```python
from core.pdf_utils import JSONParser

def my_fix_callback(pdf_bytes, fix_prompt):
    # 调用LLM修复JSON
    return llm_client.call(fix_prompt)

result = JSONParser.parse_with_llm_retry(
    initial_response=llm_response,
    llm_fix_callback=my_fix_callback,
    pdf_bytes=pdf_data,
    expected_type='array',
    max_retries=10,
    retry_on_callback_error=True  # Vision API等网络敏感场景
)
```

---

### 2. `core/logger.py` - 响应验证和错误分类

#### `NetworkErrorHandler.is_retryable_error()`

**用途 / Purpose**: 统一分类网络错误，决定是否应该重试

**签名 / Signature**:
```python
@staticmethod
def is_retryable_error(error: Exception) -> Tuple[bool, str]
```

**返回值 / Returns**:
- `Tuple[bool, str]`: `(是否可重试, 错误类型描述)`

**错误分类 / Error Classification**:
| 错误类型 | 可重试 | 描述 |
|---------|-------|------|
| **429 Rate Limit** | ✅ 是 | API速率限制 |
| **500/502/503/504** | ✅ 是 | 服务器错误 |
| **Timeout** | ✅ 是 | 请求超时 |
| **ConnectionError** | ✅ 是 | 网络连接失败 |
| **401/403** | ❌ 否 | 认证/权限错误 |
| **400/404** | ❌ 否 | 客户端错误 |
| **JSON Decode** | ❌ 否 | JSON解析错误 |

**代码示例 / Example**:
```python
from core.logger import NetworkErrorHandler

try:
    response = requests.post(api_url, json=payload)
    response.raise_for_status()
except Exception as e:
    should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

    if should_retry:
        logger.warning(f"{error_type}, 将重试...")
    else:
        logger.error(f"{error_type} (不可重试)")
        raise
```

---

### 3. `logger.py` - 日志和心跳监控

#### `HeartbeatMonitor`

**用途 / Purpose**: 为长时间运行的任务提供定期进度输出（防止用户以为程序卡死）

**签名 / Signature**:
```python
class HeartbeatMonitor:
    def __init__(
        self,
        task_name: str,
        total: int,
        interval_seconds: int = 30
    )

    def start(self)
    def update(self, completed: int)
    def stop(self)
```

**使用时机 / When to Use**:
- ✅ 任务预计耗时 > 1分钟
- ✅ 有明确的总数和完成数
- ✅ 在工作流脚本中（非功能模块）

**代码示例 / Example**:
```python
from core.logger import HeartbeatMonitor

monitor = HeartbeatMonitor(
    task_name="PDF批次提取",
    total=50,
    interval_seconds=30  # 每30秒输出一次
)

monitor.start()  # 启动后台线程

for i, batch in enumerate(batches, 1):
    process_batch(batch)
    monitor.update(i)  # 更新完成数

monitor.stop()  # 停止后台线程
```

**输出示例 / Output Example**:
```
[2025-01-15 14:30:00] ❤️ PDF批次提取 进度: 15/50 (30.0%)
[2025-01-15 14:30:30] ❤️ PDF批次提取 进度: 28/50 (56.0%)
```

---

## 添加新功能指南 / Adding New Features

### 场景1: 添加新的 API 客户端

**步骤 / Steps**:

1. **确定模块位置 / Determine Module Location**:
   - API客户端应该在对应的功能模块中（如 `processors/vision_processor.py`）
   - 不要放在工作流脚本中

2. **实现客户端类 / Implement Client Class**:
```python
# 在 my_new_module.py 中
from core.logger import NetworkErrorHandler
import requests
import time

class MyAPIClient:
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url

    def call_api(
        self,
        payload: dict,
        max_retries: int = 3,
        retry_delay: int = 5
    ) -> dict:
        """调用API with unified error handling"""
        last_error = None

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()
                return response.json()

            except Exception as e:
                last_error = e

                # 使用统一的错误处理器
                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

                if should_retry and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(f"{error_type}, {wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    break

        raise Exception(f"API调用失败: {last_error}")
```

3. **在工作流中使用 / Use in Workflow**:
```python
# 在 my_workflow.py 中
from my_new_module import MyAPIClient
from core.logger import HeartbeatMonitor

client = MyAPIClient(api_key, api_url)

# 启动心跳监控
monitor = HeartbeatMonitor("新功能处理", total=len(items), interval_seconds=30)
monitor.start()

for i, item in enumerate(items, 1):
    result = client.call_api(payload)  # API客户端已有错误处理
    # 处理结果...
    monitor.update(i)

monitor.stop()
```

---

### 场景2: 添加新的 JSON 解析功能

**错误做法 / Wrong Approach** ❌:
```python
# 在功能模块中重新实现JSON重试
def my_parse_json(response):
    for i in range(10):
        try:
            return json.loads(response)
        except:
            # 重试...
```

**正确做法 / Correct Approach** ✅:
```python
from core.pdf_utils import JSONParser

def my_parse_function(llm_response: str):
    # 定义修复回调
    def fix_callback(pdf_bytes, fix_prompt):
        return my_llm_client.call(fix_prompt)

    # 使用统一的JSON解析器
    result = JSONParser.parse_with_llm_retry(
        initial_response=llm_response,
        llm_fix_callback=fix_callback,
        pdf_bytes=None,  # 如果不需要PDF上下文
        expected_type='object',
        max_retries=10,
        retry_on_callback_error=True  # 如果网络敏感
    )

    return result
```

---

### 场景3: 添加长时间运行的批处理任务

**完整示例 / Complete Example**:
```python
# 在 my_batch_processor.py (工作流脚本)
from core.logger import HeartbeatMonitor, get_logger
from my_utility_module import process_item

logger = get_logger(__name__)

def process_batch(items: list):
    total = len(items)

    # 启动心跳监控
    monitor = HeartbeatMonitor(
        task_name="批量处理",
        total=total,
        interval_seconds=30
    )
    monitor.start()

    results = []
    for i, item in enumerate(items, 1):
        try:
            # 调用功能模块处理单个项目
            result = process_item(item)
            results.append(result)

        except Exception as e:
            logger.error(f"处理失败: {e}")
            results.append(None)

        # 更新进度
        monitor.update(i)
        logger.info(f"完成 {i}/{total}")

    # 停止心跳
    monitor.stop()

    return results
```

---

## 错误处理模式 / Error Handling Patterns

### 模式1: API调用重试 / API Call Retry

```python
from core.logger import NetworkErrorHandler
import time

def call_api_with_retry(url, payload, max_retries=3):
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            last_error = e
            should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

            if should_retry and attempt < max_retries - 1:
                wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s
                logger.warning(f"{error_type}, {wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"{error_type} (不可重试)")
                break

    raise Exception(f"API调用失败: {last_error}")
```

### 模式2: JSON解析重试 / JSON Parsing Retry

```python
from core.pdf_utils import JSONParser

def parse_llm_response(llm_response, llm_client, pdf_bytes=None):
    def fix_callback(pdf_bytes, fix_prompt):
        return llm_client.call(fix_prompt)

    return JSONParser.parse_with_llm_retry(
        initial_response=llm_response,
        llm_fix_callback=fix_callback,
        pdf_bytes=pdf_bytes,
        expected_type='array',  # or 'object'
        max_retries=10,
        retry_on_callback_error=False  # 根据场景调整
    )
```

### 模式3: 分类错误统计 / Error Classification Statistics

```python
class MyProcessor:
    def __init__(self):
        self.failure_stats = {
            'network_error': 0,
            'json_error': 0,
            'rate_limit': 0,
            'server_error': 0,
            'other': 0
        }

    def process_with_stats(self, item):
        try:
            return self._process(item)
        except Exception as e:
            should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

            # 统计错误类型
            if '429' in error_type:
                self.failure_stats['rate_limit'] += 1
            elif 'timeout' in error_type.lower():
                self.failure_stats['network_error'] += 1
            # ...

            raise

    def print_failure_stats(self):
        total = sum(self.failure_stats.values())
        if total == 0:
            return

        print(f"\n失败统计: 共 {total} 次")
        for reason, count in self.failure_stats.items():
            if count > 0:
                print(f"  {reason}: {count} ({count/total*100:.1f}%)")
```

---

## 进度监控模式 / Progress Monitoring

### 何时使用 HeartbeatMonitor / When to Use HeartbeatMonitor

| 场景 | 使用HeartbeatMonitor | 原因 |
|------|---------------------|------|
| 处理50个PDF批次 | ✅ 是 | 长时间运行(>5分钟) |
| 生成100篇HTML文章 | ✅ 是 | 长时间运行(>2分钟) |
| 翻译50篇文章 | ✅ 是 | 长时间运行(>10分钟) |
| 单个图片匹配 | ❌ 否 | 短时间操作(<5秒) |
| JSON解析 | ❌ 否 | 瞬时操作(<1秒) |
| 功能模块内部 | ❌ 否 | 无全局上下文 |

### 标准模式 / Standard Pattern

```python
from core.logger import HeartbeatMonitor
from concurrent.futures import ThreadPoolExecutor, as_completed

def batch_process(items):
    total = len(items)

    # 启动心跳监控
    monitor = HeartbeatMonitor(
        task_name="批量处理",
        total=total,
        interval_seconds=30
    )
    monitor.start()

    completed = 0

    # 并发处理
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_item, item): i for i, item in enumerate(items)}

        for future in as_completed(futures):
            try:
                result = future.result()
                # 处理结果...
            except Exception as e:
                logger.error(f"处理失败: {e}")

            completed += 1
            monitor.update(completed)  # 更新进度

    # 停止心跳
    monitor.stop()
```

---

## 最佳实践 / Best Practices

### ✅ DO - 应该做的

1. **使用现有工具**:
   - JSON解析 → `JSONParser.parse_with_llm_retry()`
   - 错误分类 → `NetworkErrorHandler.is_retryable_error()`
   - 进度监控 → `HeartbeatMonitor`

2. **保持模块职责单一**:
   - 工作流脚本 = 流程编排
   - 功能模块 = 可复用能力
   - 核心工具 = 通用基础设施

3. **添加详细日志**:
   ```python
   logger.info("开始处理...")
   logger.warning("检测到问题...")
   logger.error("处理失败...")
   logger.debug("详细调试信息...")
   ```

4. **使用类型提示**:
   ```python
   def process_item(item: Dict[str, Any]) -> Optional[List[str]]:
       pass
   ```

5. **编写文档字符串**:
   ```python
   def my_function(param1: str, param2: int) -> bool:
       """
       简短描述功能

       Args:
           param1: 参数1的说明
           param2: 参数2的说明

       Returns:
           返回值说明
       """
       pass
   ```

---

### ❌ DON'T - 不应该做的

1. **在功能模块中添加HeartbeatMonitor**:
   ```python
   # ❌ 错误 - 功能模块不应该有HeartbeatMonitor
   class ImageExtractor:
       def extract_images(self, pdf_path):
           monitor = HeartbeatMonitor(...)  # ❌
   ```

2. **重复实现现有工具**:
   ```python
   # ❌ 错误 - core/pdf_utils.py已有此功能
   def my_parse_json_with_retry(response):
       for i in range(10):
           try:
               return json.loads(response)
           except:
               pass  # ❌
   ```

3. **硬编码配置值**:
   ```python
   # ❌ 错误
   timeout = 120  # ❌ 应该从config.py读取

   # ✅ 正确
   from config import UserConfig
   timeout = UserConfig.API_TIMEOUT
   ```

4. **忽略错误处理**:
   ```python
   # ❌ 错误
   try:
       response = requests.post(url)
   except:
       pass  # ❌ 不要静默失败

   # ✅ 正确
   try:
       response = requests.post(url)
   except Exception as e:
       logger.error(f"请求失败: {e}")
       raise
   ```

5. **在utility模块中添加业务逻辑**:
   ```python
   # ❌ 错误 - core/pdf_utils.py不应该知道PDF业务
   def parse_article_json(response):
       data = json.loads(response)
       # 验证文章字段... ❌ 这是业务逻辑
   ```

---

## 代码示例 / Code Examples

### 完整示例: 添加新的API集成

```python
# ============================================================
# 文件: my_new_api_client.py (功能模块)
# ============================================================
import requests
import time
from typing import Dict, Any
from core.logger import NetworkErrorHandler
from core.logger import get_logger

logger = get_logger(__name__)

class MyNewAPIClient:
    """新API客户端 - 统一错误处理"""

    def __init__(self, api_key: str, api_url: str, max_retries: int = 3):
        self.api_key = api_key
        self.api_url = api_url
        self.max_retries = max_retries

    def call_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用API with unified error handling and retry

        Args:
            payload: API请求负载

        Returns:
            API响应数据

        Raises:
            Exception: API调用失败
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()

                result = response.json()
                return result

            except Exception as e:
                last_error = e

                # 使用统一的错误处理器
                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)
                error_detail = str(e)[:200]

                # 重试逻辑
                if should_retry and attempt < self.max_retries - 1:
                    wait_time = 5 * (2 ** attempt)  # 指数退避: 5s, 10s, 20s
                    logger.warning(
                        f"API调用失败 ({error_type}), {wait_time}秒后重试 "
                        f"(第{attempt+1}/{self.max_retries}次)"
                    )
                    logger.debug(f"详情: {error_detail}")
                    time.sleep(wait_time)
                    continue
                else:
                    if not should_retry:
                        logger.error(f"API调用失败 ({error_type}, 不可重试): {error_detail}")
                    break

        # 所有重试都失败
        raise Exception(f"API调用失败: {str(last_error)}")


# ============================================================
# 文件: my_new_workflow.py (工作流脚本)
# ============================================================
from pathlib import Path
from typing import List, Dict
from core.logger import HeartbeatMonitor, get_logger
from core.pdf_utils import JSONParser
from my_new_api_client import MyNewAPIClient

logger = get_logger(__name__)

class MyNewWorkflow:
    """新工作流 - 展示HeartbeatMonitor和JSONParser使用"""

    def __init__(self, api_key: str, api_url: str):
        self.client = MyNewAPIClient(api_key, api_url)

    def process_items(self, items: List[Dict]) -> List[Dict]:
        """
        批量处理项目 with progress monitoring

        Args:
            items: 待处理项目列表

        Returns:
            处理结果列表
        """
        total = len(items)
        logger.info(f"开始处理 {total} 个项目...")

        # 启动心跳监控
        monitor = HeartbeatMonitor(
            task_name="新工作流处理",
            total=total,
            interval_seconds=30
        )
        monitor.start()

        results = []

        for i, item in enumerate(items, 1):
            try:
                # 调用API
                api_response = self.client.call_api(payload=item)

                # 使用统一的JSON解析器
                def fix_callback(_, fix_prompt):
                    # 如果JSON解析失败，请求API修复
                    return self.client.call_api({"fix_prompt": fix_prompt})

                parsed_data = JSONParser.parse_with_llm_retry(
                    initial_response=api_response.get('data', '{}'),
                    llm_fix_callback=fix_callback,
                    pdf_bytes=None,
                    expected_type='object',
                    max_retries=5,
                    retry_on_callback_error=True  # 网络敏感场景
                )

                results.append(parsed_data)
                logger.info(f"✅ 项目 {i}/{total} 处理成功")

            except Exception as e:
                logger.error(f"❌ 项目 {i}/{total} 处理失败: {str(e)[:100]}")
                results.append(None)

            # 更新进度
            monitor.update(i)

        # 停止心跳监控
        monitor.stop()

        success_count = sum(1 for r in results if r is not None)
        logger.info(f"完成: {success_count}/{total} 个项目成功")

        return results


# ============================================================
# 使用示例 / Usage Example
# ============================================================
if __name__ == "__main__":
    workflow = MyNewWorkflow(
        api_key="your-api-key",
        api_url="https://api.example.com"
    )

    items = [{"id": i, "data": f"item-{i}"} for i in range(50)]
    results = workflow.process_items(items)
```

---

## 总结 / Summary

### 核心原则 Core Principles

1. **DRY (Don't Repeat Yourself)**: 优先使用现有工具，避免重复实现
2. **SoC (Separation of Concerns)**: 工作流、功能、工具三层分离
3. **Consistency First**: 统一的错误处理、进度监控、JSON解析

### 快速检查清单 Quick Checklist

在提交代码前，检查以下项目:

- [ ] 是否使用了 `NetworkErrorHandler` 处理API错误？
- [ ] 是否使用了 `JSONParser.parse_with_llm_retry()` 解析JSON？
- [ ] 长时间任务是否添加了 `HeartbeatMonitor`？
- [ ] 功能模块是否避免了添加 `HeartbeatMonitor`？
- [ ] 是否有重复的代码可以提取到工具模块？
- [ ] 是否添加了详细的日志输出？
- [ ] 是否添加了类型提示和文档字符串？

---

## 🔗 相关文档 / Related Documentation

- 📖 [返回主文档 / Back to README](../README.md)
- 📚 [系统架构 / Architecture](ARCHITECTURE.md) - 完整架构设计
- 🔄 [工作流程 / Workflow](WORKFLOW.md) - 工作流程与调用关系
- 🖼️ [图片处理 / Image Processing](IMAGE_PROCESSING.md) - 图片处理流程
- 🔧 [Vision API](VISION_API.md) - Vision API集成指南
- ⚙️ [配置说明 / Configuration](CONFIGURATION.md) - 配置参数详解
- 🐛 [故障排查 / Troubleshooting](TROUBLESHOOTING.md) - 常见问题解决
- 📝 [更新日志 / Changelog](CHANGELOG.md) - 版本历史

---

**维护者 / Maintainer**: Claude Code Team
**最后更新 / Last Updated**: 2025-01
**版本 / Version**: 1.0
