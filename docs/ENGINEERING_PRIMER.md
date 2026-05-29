# 工程化改造详解

本文档面向 Python 初学者，解释本次 6 项改造的设计动机和实现原理。不假设你懂设计模式或高级语法。

---

## 目录

1. [前置概念：为什么字符串约定是坏味道](#1-前置概念为什么字符串约定是坏味道)
2. [P1 结构化错误模型](#p1-结构化错误模型)
3. [P2 配置校验](#p2-配置校验)
4. [P3 依赖注入与 Protocol](#p3-依赖注入与-protocol)
5. [P4 测试接缝 test-seam](#p4-测试接缝-test-seam)
6. [P5 指标收集 MetricsCollector](#p5-指标收集-metricscollector)
7. [P6 任务句柄 TranslationTask](#p6-任务句柄-translationtask)

---

## 1. 前置概念：为什么字符串约定是坏味道

### 旧代码长这样

```python
# translator.py — 返回时手动加前缀
return f"[翻译失败: {str(e)}]"

# file_processor.py — 判断时手动匹配前缀
if content_zh.startswith('[翻译失败:'):
    invalid_count += 1
```

### 问题在哪

这是两个人之间靠"约定"通信：一个人说"我会在失败时加 `[翻译失败]` 前缀"，另一个人说"我看到 `[翻译失败]` 就判断为失败"。

**约定有三个致命缺陷**：

1. **拼写错误不会报错**。你把 `[翻译失败]` 写成了 `[翻译失败:]`（多一个冒号），Python 不会告诉你。代码静默失效——本来该被识别为失败的译文变成了"成功"。
2. **改一处要改所有地方**。你想把前缀从 `[翻译失败]` 改成 `[ERROR]`，所有 `startswith('[翻译失败')` 的调用点都要改。漏改一个就出 bug。
3. **信息丢失**。`[翻译失败: timeout]` 是一个字符串。你没法问它"失败原因是什么？""能重试吗？"——除非再解析字符串。

### 解决方案的本质

把"约定"变成"结构"。不再靠字符串格式通信，而是靠**数据字段**通信：

```python
# 旧：字符串约定
"[翻译失败: timeout]"

# 新：结构化的数据
TranslationError(
    status=TranslationStatus.LLM_ERROR,
    category=ErrorCategory.TIMEOUT,
    message="timeout",
    original_text="原文...",
    detail="请求超时，重试3次后放弃"
)
```

现在你不需要记住前缀格式。你访问 `error.category`，IDE 会提示你有哪些可选值。

---

## 2. P1 结构化错误模型

### 涉及文件

- **新建** `core/translation_result.py`
- **修改** `processors/translator.py`
- **修改** `pipeline/file_processor.py`

### 核心设计

用了四个 Python 内置的数据结构：

#### a) Enum — 枚举，定义一组有限的取值

```python
from enum import Enum

class TranslationStatus(Enum):
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    IDENTICAL_TO_SOURCE = "identical_to_source"
    LLM_ERROR = "llm_error"
    EMPTY_INPUT = "empty_input"
```

**为什么用它**：原来用字符串 `"success"` 表示成功，没有任何限制——你可以写成 `"sucess"`（少一个 c）并不报错。Enum 限制了你只能从这 5 个值里选。写 `TranslationStatus.SUCESS` 会直接报 `AttributeError`，bug 在开发阶段就暴露。

#### b) dataclass — 数据类，减少样板代码

```python
from dataclasses import dataclass

@dataclass
class TranslationError:
    status: TranslationStatus
    category: ErrorCategory
    message: str
    original_text: str
    detail: Optional[str] = None
```

**为什么用它**：不用 `@dataclass` 的话，你需要手写：

```python
class TranslationError:
    def __init__(self, status, category, message, original_text, detail=None):
        self.status = status
        self.category = category
        self.message = message
        self.original_text = original_text
        self.detail = detail
```

`@dataclass` 自动生成 `__init__`、`__repr__`、`__eq__`，你只声明字段名和类型。一行装饰器省掉十几行模板代码。

#### c) to_legacy_string() — 向后兼容桥接

```python
def to_legacy_string(self) -> str:
    if self.status == TranslationStatus.SUCCESS:
        return self.translated_text
    if self.status == TranslationStatus.VALIDATION_FAILED:
        return f"[验证失败-原文] {self.error.original_text}"
    ...
```

**为什么需要这个**：你的系统里有很多下游代码期望译文是字符串。Excel 生成器、JSON 缓存、进度管理器都往 DataFrame 的 `content_zh` 列写字符串。如果突然改成 `TranslationResult` 对象，这些地方全炸。

`to_legacy_string()` 是一个过渡方案——内部用结构化的 `TranslationResult` 做判断，但序列化到文件时还原成旧格式。这样下游代码一行不动，内部判断全部安全。

#### d) 工厂函数 — 简化对象创建

```python
def success_result(text: str, latency_ms: float = 0.0, retry_count: int = 0) -> TranslationResult:
    return TranslationResult(
        status=TranslationStatus.SUCCESS,
        translated_text=text,
        latency_ms=latency_ms,
        retry_count=retry_count,
    )
```

**为什么用工厂函数**：让调用方少写代码。原来你需要：

```python
return TranslationResult(
    status=TranslationStatus.SUCCESS,
    translated_text=final_translation,
    error=None,
    latency_ms=elapsed * 1000,
    retry_count=attempt,
)
```

现在只需要：

```python
return success_result(final_translation, latency_ms=elapsed * 1000, retry_count=attempt)
```

### 调用方的变化

```python
# 旧代码：判断失败靠字符串前缀
if content_zh.startswith('[翻译失败:') or content_zh.startswith('[验证失败'):

# 新代码：判断失败靠对象成员 —— 但过渡期仍用 startswith
# 因为 to_legacy_string() 保证序列化输出不变
# 等下游代码也迁移后，可以改成：
# if result.status != TranslationStatus.SUCCESS:
```

---

## 3. P2 配置校验

### 涉及文件

- **新建** `core/config_validator.py`
- **修改** `config.py`
- **修改** `main.py`

### 问题

`UserConfig` 类有 50+ 配置项：

```python
class UserConfig:
    PDF_API_KEY = "sk-..."
    MAX_WORKERS = 8
    PAGES_PER_BATCH = 6
    OVERLAP_PAGES = 2
    # ... 50 多个
```

没有任何机制保证配置合法。如果 `MAX_WORKERS` 被误设为 0，程序不会在启动时报错，而是跑到翻译阶段才炸——此时可能已经浪费了几十分钟。

### 设计

`ConfigValidator` 是一个**静态类**（不需要实例化），包含一组独立的检查函数：

```python
class ConfigValidator:
    @staticmethod
    def validate(user_config) -> List[ConfigViolation]:
        violations = []
        _check_api_key(violations, user_config, 'PDF_API_KEY')
        _check_positive_int(violations, user_config, 'MAX_WORKERS', min_val=1)
        # ...
        return violations
```

每个 `_check_xxx` 函数做一件事：取配置值 → 判断是否合法 → 不合法就追加一条 `ConfigViolation`。

**为什么用独立函数而不是一个巨大的 if-else**：每个检查函数可以独立测试、独立修改。加一个新配置项只加一行调用，不影响已有逻辑。

### 启动时调用

```python
# main.py — confirm_and_execute() 第一行
violations = UserConfig.validate()
errors = [v for v in violations if v.severity == "error"]
if errors:
    print("[配置错误] ...")
    return False  # 终止，不进入任何处理流程
```

这叫 **fail-fast**（快速失败）——在代价最低的时间点（启动 0.1 秒时）阻止错误，而不是跑到一半（启动 30 分钟后）才炸。

---

## 4. P3 依赖注入与 Protocol

### 涉及文件

- **新建** `core/llm_client.py`
- **修改** `processors/translator.py`

### 问题

旧代码中 `ArticleTranslator` 直接创建 HTTP 客户端：

```python
class ArticleTranslator:
    def __init__(self, api_key, ...):
        self.session = requests.Session()  # 硬编码：只能用 requests 库
```

这导致：
- 想换 `httpx` 库 → 改源码
- 想做单元测试 → 必须 mock `requests` 模块
- 想换 API 格式 → 改 `_call_llm`

### 核心概念：Protocol

Python 3.8 引入了 `Protocol`，它定义"一个东西必须会什么"，不关心"它是怎么做到的"。

```python
from typing import Protocol

class LLMClient(Protocol):
    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 65536,
        timeout: tuple = (30, 600),
    ) -> dict:
        ...
```

翻译一下：**任何有 `chat_completion` 方法（接收这些参数、返回 dict）的对象，都可以当 LLMClient 用。**

它不指定这个方法是发 HTTP 请求、读本地文件、还是返回硬编码数据。这是实现者的事。

### 生产实现

```python
class HttpLLMClient:
    def __init__(self, api_key, api_base_url):
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def chat_completion(self, messages, model, ...):
        response = self._session.post(endpoint, json={...})
        return {'content': ..., 'finish_reason': ..., 'usage': ..., 'raw_response': ...}
```

`HttpLLMClient` 满足 `LLMClient` Protocol（因为它有 `chat_completion` 方法）。但它不是 `LLMClient` 的子类——Protocol 是隐式的，不需要显式继承。

### 注入到 Translator

```python
class ArticleTranslator:
    def __init__(
        self,
        api_key: str,
        llm_client: Optional[LLMClient] = None,  # 新的注入点
        ...
    ):
        if llm_client is not None:
            self._llm = llm_client         # 用注入的
        else:
            self._llm = HttpLLMClient(...)  # 用默认的（向后兼容）
```

**为什么这么做**：现有调用方不需要改任何代码——不传 `llm_client` 时，行为跟原来一模一样。但如果你需要测试或切换 API，可以注入自己的实现。

这叫做 **依赖注入**（Dependency Injection）：类不自己创建依赖，而是由外部"注入"。类比：你不自己造螺丝，而是从供应商进货——供应商换了，你的生产线不动。

### HTTP 调用被委托出去

```python
# _call_llm 中原来的代码：
response = self.session.post(url, headers=headers, json=payload)
result = response.json()

# 改为：
response_data = self._llm.chat_completion(messages=messages, ...)
result = response_data['raw_response']
```

重试、日志、验证这些逻辑全留在 `_call_llm` 不动。只有原始的 HTTP POST 被委托出去。

---

## 5. P4 测试接缝 test-seam

### 涉及文件

- **修改** `processors/translator.py`

### 问题

`translate_text` 内部调用 `self._call_llm(prompt)`，而 `_call_llm` 会发网络请求。测试 `translate_text` 的术语替换、prompt 构建、结果清洗、验证逻辑——这些都不应该花钱调 API。

但原来的代码结构没有让你跳过网络调用的地方。

### 实现

一个以 `_` 开头、默认值为 `None` 的参数：

```python
def __init__(
    self,
    ...
    _llm_override: Optional[Callable[[str], str]] = None,  # ← 就这一行
):
    self._llm_override = _llm_override
```

`translate_text` 中加一个提前返回的分支：

```python
def translate_text(self, text, field_name, article_idx=None) -> TranslationResult:
    ...
    if self._llm_override is not None:
        # 不走网络，直接调用 mock 函数
        try:
            result_text = self._llm_override(text)
            return success_result(result_text, ...)
        except Exception as e:
            return error_result(...)
    # 否则走正常 API 路径
    ...
```

### 为什么 `_` 开头

Python 的命名约定：单下划线前缀表示"这是内部用的，别在正常代码里传"。

测试时可以这样用：

```python
translator = ArticleTranslator(
    api_key="dummy",
    _llm_override=lambda text: f"MOCKED[{text[:20]}...]"
)
# translate_text 不会联网，直接返回模拟结果
result = translator.translate_text("Hello world", "标题")
assert result.is_success
```

### 这叫 "seam"

Michael Feathers 在《修改代码的艺术》中提出的概念：在不改生产行为的前提下，给代码留一条"缝"，只在测试时撑开。代价只有一行参数声明和几行提前返回，换回的是可以不花钱、不联网、不等 LLM 响应就验证 `translate_text` 的全部逻辑。

---

## 6. P5 指标收集 MetricsCollector

### 涉及文件

- **新建** `core/metrics.py`
- **修改** `processors/translator.py`
- **修改** `pipeline/file_processor.py`

### 问题

旧代码有 `self.failure_stats` 字典，记录各类错误次数。但它回答不了这些问题：

- "今天 API 平均延迟多少？"
- "P99 延迟是多少？"（99% 的请求在多少秒内完成）
- "哪种错误占比最高？"
- "翻译一个字平均花多少钱？"

### 设计

```python
class MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()      # 线程安全
        self._total = 0                    # 总请求数
        self._success = 0                  # 成功数
        self._failure = 0                  # 失败数
        self._latencies_ms = []            # 每次调用的延迟
        self._error_by_category = defaultdict(int)  # 按错误类型分类

    def record(self, result: TranslationResult):
        with self._lock:
            self._total += 1
            if result.is_success:
                self._success += 1
            else:
                self._failure += 1
                if result.error:
                    self._error_by_category[result.error.category.value] += 1
            if result.latency_ms > 0:
                self._latencies_ms.append(result.latency_ms)

    def snapshot(self) -> MetricsSnapshot:
        """返回一个不可变的快照，包含统计摘要"""
        latencies = sorted(self._latencies_ms)
        return MetricsSnapshot(
            total_requests=self._total,
            success_count=self._success,
            average_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
            p99_latency_ms=...,  # 第 99 百分位数
        )
```

关键设计点：

**线程安全**：`translate_text` 可能在多个线程中被并发调用。`self._lock` 确保一次只有一个线程修改计数器，不会出现竞态条件（两个线程同时 `self._total += 1` 导致只加了一次）。

**快照 snapshot**：`snapshot()` 方法返回一份不变的 `MetricsSnapshot`，而不是让你直接读内部数据。这样你拿到快照后，即使后台还在继续翻译，快照数据也不会变。

**百分位数**：P95 = 95% 的请求在这个时间以下完成。举例：100 次请求，排好序，取第 95 个的延迟 = P95 延迟。这比平均值有用——平均值会被少数极慢的请求拉高，P95 反映的是"大多数请求"的体验。

### 埋点

在 `translate_text` 的每个返回点之前：

```python
start_ts = time.perf_counter()
# ... 翻译逻辑 ...
elapsed_ms = (time.perf_counter() - start_ts) * 1000
result = success_result(text, latency_ms=elapsed_ms)
self.metrics.record(result)  # ← 就这一行
return result
```

每个翻译结果都被记录。运行结束后，`snapshot()` 给出全景统计。

---

## 7. P6 任务句柄 TranslationTask

### 涉及文件

- **新建** `core/translation_task.py`

### 问题

现在的调用方式：

```python
# 调用方卡住，直到所有文章翻译完
df_result = translator.translate_dataframe(df, ...)
# 可能 10 分钟后才执行到这里
```

调用方没有任何控制权：不能查进度、不能取消、不能并发。

### 核心思想：把"下单"和"取货"拆成两步

```python
# 第一步：下单 → 立刻拿回小票（句柄）
task = TranslationTask(translator, df, ...)
task.start()  # 后台线程跑

# 第二步：你需要的时候再取货
print(task.state)    # "running" → 不卡
task.wait()          # 阻塞等完成
df_result = task.result  # 拿结果
```

### 如何实现

核心是 `threading.Thread`。标准库自带，不需要安装：

```python
import threading

class TranslationTask:
    def __init__(self, translator, df, ...):
        self._state = TaskState.PENDING  # 初始状态
        self._result = None              # 结果（完成后才填）
        self._error = None               # 异常（失败后才有）
        self._lock = threading.Lock()    # 线程安全锁

    def start(self):
        self._state = TaskState.RUNNING
        self._thread = threading.Thread(
            target=self._run,   # 要跑的函数
            daemon=True,         # 守护线程：主程序退出时自动清理
        )
        self._thread.start()
        return self  # 链式调用

    def _run(self):
        try:
            # 跑原来的同步方法
            self._result = self._translator.translate_dataframe(self._df, ...)
            self._state = TaskState.COMPLETED
        except Exception as e:
            self._error = e
            self._state = TaskState.FAILED

    def wait(self, timeout=None):
        self._thread.join(timeout)  # 等待线程结束
        return self                 # 链式调用
```

### 为什么 daemon=True

守护线程的特点是：主程序退出时，守护线程会被自动终止。如果你的翻译脚本被 Ctrl+C 了，后台翻译线程不会阻止进程退出。

### 为什么 return self

让调用方可以链式调用：

```python
task = TranslationTask(...).start().wait()
df = task.result
```

### 状态机

```
PENDING → RUNNING → COMPLETED
                → FAILED
                → CANCELLED (由外部调 cancel())
```

### 现有代码不动

`translate_dataframe()` 方法本身没改。`TranslationTask` 只是在外面包了一层线程管理。需要非阻塞时用 `TranslationTask`，不需要时照旧——两条路径共存。

---

## 总结：六个改造的共性

所有这些改动都遵循同一个原则：**把隐式约定变成显式结构**。

| 原来的约定 | 改后的结构 | 技术 |
|-----------|----------|------|
| 字符串前缀 `[翻译失败]` | `TranslationError` dataclass | Enum + dataclass |
| 配置值随意改 | `ConfigViolation` + 启动校验 | 静态方法 + fail-fast |
| 类内部 `requests.Session()` | `LLMClient` Protocol + `HttpLLMClient` | Protocol + 依赖注入 |
| 无法跳过网络测试 | `_llm_override` 参数 | seam 模式 |
| `failure_stats` 字典 | `MetricsCollector` + `MetricsSnapshot` | 线程安全 + 百分位数 |
| 同步阻塞返回 DataFrame | `TranslationTask` 句柄 | threading.Thread + 状态机 |

不引入任何新依赖，全部基于 Python 标准库。
