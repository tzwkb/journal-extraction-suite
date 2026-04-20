# 单文件顺序处理模式使用指南 / Sequential Processing Guide

📖 [返回主文档](../README.md) | 📚 [系统架构](ARCHITECTURE.md) | 🔧 [配置说明](CONFIGURATION.md)

---

## 📑 目录

- [1. 概述](#1-概述-overview)
  - [1.1 什么是单文件顺序模式](#11-什么是单文件顺序模式)
  - [1.2 为什么需要单文件顺序模式](#12-为什么需要单文件顺序模式)
  - [1.3 适用场景](#13-适用场景)
- [2. 快速开始](#2-快速开始-quick-start)
  - [2.1 交互式选择（推荐）](#21-交互式选择推荐)
  - [2.2 预设配置说明](#22-预设配置说明)
- [3. 核心特性](#3-核心特性-core-features)
  - [3.1 有界队列（防内存爆炸）](#31-有界队列防内存爆炸)
  - [3.2 全局 API 限流](#32-全局-api-限流)
  - [3.3 防饿死保障](#33-防饿死保障)
  - [3.4 看门狗监控](#34-看门狗监控)
- [4. 配置详解](#4-配置详解-configuration-details)
  - [4.1 基础配置参数](#41-基础配置参数)
  - [4.2 高级配置](#42-高级配置)
  - [4.3 自定义配置示例](#43-自定义配置示例)
- [5. 性能对比与调优](#5-性能对比与调优-performance-tuning)
  - [5.1 批量并发 vs 单文件顺序](#51-批量并发-vs-单文件顺序)
  - [5.2 预设选择建议](#52-预设选择建议)
  - [5.3 参数调优指南](#53-参数调优指南)
- [6. 故障排查](#6-故障排查-troubleshooting)
  - [6.1 常见问题](#61-常见问题)
  - [6.2 监控和日志](#62-监控和日志)
- [7. 最佳实践](#7-最佳实践-best-practices)
  - [7.1 文件数量规划](#71-文件数量规划)
  - [7.2 系统资源配置](#72-系统资源配置)
  - [7.3 长时间运行建议](#73-长时间运行建议)

---

## 1. 概述 / Overview

### 1.1 什么是单文件顺序模式

**单文件顺序模式（Sequential Processing Mode）** 是一种专为大批量文件处理设计的执行器架构。与传统的批量并发模式不同，它通过多层资源限制和智能调度，实现稳定、可控的文件处理。

**核心理念：**
- 🎯 **可控并发**：限制同时处理的文件数量（2-8个）
- 🔒 **全局限流**：跨所有文件和模块统一控制 API 并发（50-100）
- 🛡️ **资源保护**：有界队列防止内存溢出，看门狗检测死锁
- ⚖️ **公平调度**：防饿死机制确保每个文件都能获得资源

### 1.2 为什么需要单文件顺序模式

**批量并发模式的问题（处理大量文件时）：**

| 问题 | 说明 | 影响 |
|------|------|------|
| **内存爆炸** | 20文件 × 100批次 = 2000+ 任务同时在内存 | OOM崩溃 |
| **资源竞争** | 无限制API并发可能触发限流 | 429错误，处理失败 |
| **难以控制** | 无法精确控制资源使用 | 不可预测的行为 |
| **进度不透明** | 大量并发任务导致进度难以追踪 | 用户体验差 |

**单文件顺序模式的解决方案：**

```python
# 批量并发模式（无限制）
20 文件 × 100 worker = 2000 理论并发
↓ 内存占用高，可能 OOM

# 单文件顺序模式（受控）
4 文件 × 28 worker = 112 理论并发
→ 全局限制在 75 实际并发
→ 队列上限 500 任务
→ 内存占用可控 (~4GB)
```

### 1.3 适用场景

#### ✅ 适合使用单文件顺序模式

| 场景 | 推荐预设 | 原因 |
|------|---------|------|
| **1000+ 文件批量处理** | Conservative | 极致稳定，长时间运行 |
| **100-500 文件** | Balanced | 平衡速度与稳定性 |
| **API 有严格限流** | Conservative/Balanced | 避免触发 429 错误 |
| **系统资源受限（8-16GB RAM）** | Conservative | 低内存占用 |
| **需要精确进度追踪** | 任意预设 | 可控并发，进度清晰 |

#### ❌ 不适合使用单文件顺序模式

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| **< 50 文件** | Batch Concurrent | 速度更快，资源爆炸风险低 |
| **系统资源充足（32GB+ RAM）** | Batch Concurrent | 可以充分利用并发 |
| **API 无限流限制** | Batch Concurrent | 无需限流，最大化速度 |
| **追求极致速度** | Batch Concurrent / Aggressive | 牺牲稳定性换速度 |

---

## 2. 快速开始 / Quick Start

### 2.1 交互式选择（推荐）

这是最简单的使用方式，系统会引导你完成配置。

**步骤：**

1. **运行主程序**
   ```bash
   python main.py
   ```

2. **完成前4个配置步骤**
   - 步骤1：选择输入文件
   - 步骤2：配置AI翻译
   - 步骤3：选择术语库（可选）
   - 步骤4：高级设置

3. **步骤5：选择处理模式**
   ```
   [执行器] 步骤5: 选择处理模式
   --------------------------------------------------------------------------------

   ▸ 处理模式:
     1. 批量并发模式 (推荐用于少量文件)
        - 多文件并发处理，速度快
        - 适合: < 50 个文件
        - 资源占用: 高

     2. 单文件顺序模式 (推荐用于大批量文件)
        - 文件级别控制，稳定可靠
        - 适合: 50+ 文件，尤其是 1000+ 文件
        - 资源占用: 可控（防止内存爆炸）
        - 特性: 全局 API 限流、防饿死保障、看门狗监控

   请选择处理模式 (1/2, 默认1): 2
   ```

4. **选择预设配置**
   ```
   ▸ 顺序模式预设:
     1. Conservative (保守) - 1000+ 文件
        - 文件并发: 2, API 并发: 50
        - 最稳定，适合超大批量

     2. Balanced (均衡) - 100-500 文件 [默认]
        - 文件并发: 4, API 并发: 75
        - 平衡速度与稳定性

     3. Aggressive (激进) - < 100 文件
        - 文件并发: 8, API 并发: 100
        - 最快速度，需要充足资源

   请选择预设 (1/2/3, 默认2): 2
   ```

5. **确认并开始处理**
   ```
   [OK] 已选择: 单文件顺序模式 (balanced)
   ```

### 2.2 预设配置说明

#### Conservative (保守) - 1000+ 文件

**特点：** 极致稳定，适合超大批量和长时间运行

**配置：**
```python
{
    'max_concurrent_files': 2,          # 同时处理2个文件
    'global_api_concurrency': 50,       # 全局50个API并发
    'per_file_max_workers': 35,         # 每文件35个worker
    'global_task_queue_size': 200,      # 队列上限200
    'watchdog_timeout': 600,            # 看门狗10分钟
}
```

**性能预估：**
- 吞吐量: 20-30 文件/小时
- 内存占用: ~3GB
- CPU占用: 20-30%
- 风险等级: 极低

**使用场景：**
- 处理 1000+ 文件
- 系统资源有限（8GB RAM）
- 需要长时间稳定运行（>24小时）
- API 限流严格

#### Balanced (均衡) - 100-500 文件 [推荐]

**特点：** 平衡速度与稳定性，适合大多数场景

**配置：**
```python
{
    'max_concurrent_files': 4,          # 同时处理4个文件
    'global_api_concurrency': 75,       # 全局75个API并发
    'per_file_max_workers': 28,         # 每文件28个worker
    'global_task_queue_size': 500,      # 队列上限500
    'watchdog_timeout': 300,            # 看门狗5分钟
}
```

**性能预估：**
- 吞吐量: 40-60 文件/小时
- 内存占用: ~4GB
- CPU占用: 30-50%
- 风险等级: 低

**使用场景：**
- 处理 100-500 文件
- 系统资源中等（12-16GB RAM）
- 需要平衡速度和稳定性
- 大多数生产环境

#### Aggressive (激进) - < 100 文件

**特点：** 最大化速度，需要充足资源

**配置：**
```python
{
    'max_concurrent_files': 8,          # 同时处理8个文件
    'global_api_concurrency': 100,      # 全局100个API并发
    'per_file_max_workers': 18,         # 每文件18个worker
    'global_task_queue_size': 1000,     # 队列上限1000
    'watchdog_timeout': 180,            # 看门狗3分钟
}
```

**性能预估：**
- 吞吐量: 60-80 文件/小时
- 内存占用: ~6GB
- CPU占用: 50-70%
- 风险等级: 中

**使用场景：**
- 处理 < 100 文件
- 系统资源充足（16GB+ RAM）
- 追求较快速度但又需要一定控制
- API 限流相对宽松

---

## 3. 核心特性 / Core Features

### 3.1 有界队列（防内存爆炸）

**问题：** 无限制的任务队列会导致内存溢出（OOM）

**解决方案：** 使用有界队列限制内存中的任务数量

```python
# BoundedThreadPoolExecutor 实现
class BoundedThreadPoolExecutor:
    def __init__(self, max_workers, max_queue_size):
        self._semaphore = Semaphore(max_workers + max_queue_size)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, **kwargs):
        # 队列满时会阻塞，直到有空位（backpressure）
        self._semaphore.acquire()
        future = self._executor.submit(...)
        return future
```

**效果：**
- ✅ 内存占用可控（队列大小 × 任务平均内存）
- ✅ 自动 backpressure（提交速度自适应处理速度）
- ✅ 避免 OOM 崩溃

**配置：**
```python
# Balanced 预设：队列上限 500
'global_task_queue_size': 500

# 内存估算：
# 假设每个任务占用 1MB
# 500 任务 × 1MB = ~500MB 队列内存
```

### 3.2 全局 API 限流

**问题：** 多个文件和模块同时调用 API，可能触发限流（429错误）

**解决方案：** 使用全局信号量统一管理 API 并发

```python
# GlobalResourceManager 实现
class GlobalResourceManager:
    def __init__(self, config):
        # 全局 API 信号量（跨所有文件和模块）
        self.api_semaphore = Semaphore(config['global_api_concurrency'])

    @contextmanager
    def acquire_api_slot(self, file_id=None):
        # 获取 API 槽位
        self.api_semaphore.acquire()
        try:
            yield  # 执行 API 调用
        finally:
            # 释放槽位
            self.api_semaphore.release()

# 在各模块中使用
class PDFArticleExtractor:
    def _call_llm_with_pdf_bytes(self, ...):
        if self.api_semaphore:
            with self.api_semaphore:  # 获取全局槽位
                response = requests.post(...)
        else:
            response = requests.post(...)
```

**效果：**
- ✅ 精确控制 API 并发（例如：全局限制在 75）
- ✅ 避免 429 限流错误
- ✅ 跨文件/模块统一管理

**配置：**
```python
# Balanced 预设：全局 75 API 并发
'global_api_concurrency': 75

# 实际效果：
# 4 文件 × 28 worker = 112 理论并发
# → 全局信号量限制在 75 实际并发
# → API 永远不会超过 75 个同时请求
```

### 3.3 防饿死保障

**问题：** 某些文件可能长时间无法获取 API 资源（饿死）

**解决方案：** 为每个文件预留最少的 API 槽位

```python
# GlobalResourceManager 防饿死机制
class GlobalResourceManager:
    def register_file(self, file_id, guarantee):
        # 为文件预留专属 API 槽位
        self.file_semaphores[file_id] = Semaphore(guarantee)

    @contextmanager
    def acquire_api_slot(self, file_id):
        # 策略1：优先使用文件专属槽位（非阻塞）
        used_file_slot = False
        if file_id and self.file_semaphores.get(file_id):
            used_file_slot = self.file_semaphores[file_id].acquire(blocking=False)

        # 策略2：如果没有专属槽位，从全局池获取（可能阻塞）
        if not used_file_slot:
            self.api_semaphore.acquire()

        try:
            yield
        finally:
            # 释放对应的槽位
            if used_file_slot:
                self.file_semaphores[file_id].release()
            else:
                self.api_semaphore.release()
```

**效果：**
- ✅ 每个文件至少保证 10 个 API 槽位
- ✅ 防止某些文件被"饿死"
- ✅ 公平调度，所有文件都能进展

**配置：**
```python
# 每个文件最少保证 10 个 API 槽位
'file_min_api_guarantee': 10

# 资源分配示例（Balanced 预设）：
# 4 文件 × 10 保障 = 40 保留槽位
# 75 全局并发 - 40 保留 = 35 共享槽位
# 每个文件可用：10（专属） + 35/4（共享） ≈ 19 个槽位
```

### 3.4 看门狗监控

**问题：** 死锁或卡顿导致处理停滞，用户无法及时发现

**解决方案：** 看门狗定时检查进展，超时则告警

```python
# WatchdogTimer 实现
class WatchdogTimer:
    def __init__(self, timeout, callback):
        self.timeout = timeout
        self.callback = callback
        self._last_feed_time = time.time()

    def feed(self, message=None):
        # "喂狗"：通知有进展
        self._last_feed_time = time.time()
        if message:
            logger.debug(f"[Watchdog] Feed: {message}")

    def _check_timeout(self):
        elapsed = time.time() - self._last_feed_time
        if elapsed > self.timeout:
            # 超时：触发回调（通常是记录警告）
            self.callback(f"No progress for {elapsed:.1f}s")

# ExecutorMonitor 集成
class ExecutorMonitor:
    def __init__(self, processor, config):
        self._watchdog = WatchdogTimer(
            timeout=config['watchdog_timeout'],
            callback=self._on_watchdog_timeout
        )

    def _on_watchdog_timeout(self, message):
        logger.warning(f"⚠️ [Watchdog] {message} - Possible deadlock!")
```

**效果：**
- ✅ 自动检测死锁和卡顿
- ✅ 超时告警（日志中记录）
- ✅ 帮助快速定位问题

**配置：**
```python
# Balanced 预设：5分钟无进展则告警
'enable_watchdog': True
'watchdog_timeout': 300  # 秒

# 告警示例：
# [WARNING] ⚠️ [Watchdog] No progress for 305.2s - Possible deadlock!
```

---

## 4. 配置详解 / Configuration Details

### 4.1 基础配置参数

完整的配置结构位于 `config.py` 中：

```python
# config.py
class UserConfig:
    SEQUENTIAL_EXECUTOR_CONFIG = {
        # 1. 文件级并发控制
        'max_concurrent_files': 4,

        # 2. 全局 API 并发限制
        'global_api_concurrency': 75,

        # 3. 每文件 worker 数
        'per_file_max_workers': 28,

        # 4. 防饿死保障
        'file_min_api_guarantee': 10,

        # 5. 队列大小控制
        'global_task_queue_size': 500,

        # 6. 溢出策略
        'queue_overflow_strategy': 'delay',

        # 7. 监控配置
        'enable_watchdog': True,
        'watchdog_timeout': 300,

        # 8. 统计日志
        'log_executor_stats': True,
        'stats_interval': 30,
    }
```

**参数说明：**

| 参数 | 说明 | 推荐值 | 影响 |
|------|------|--------|------|
| `max_concurrent_files` | 同时处理的文件数 | 2-8 | 值越大速度越快，但内存越高 |
| `global_api_concurrency` | 全局API并发上限 | 50-100 | 根据API限流调整 |
| `per_file_max_workers` | 每文件worker数 | 自动计算 | 通常无需手动设置 |
| `file_min_api_guarantee` | 每文件最少API槽位 | 10 | 防止饿死 |
| `global_task_queue_size` | 任务队列上限 | 200-1000 | 防止内存爆炸 |
| `queue_overflow_strategy` | 队列满时策略 | `'delay'` | delay=阻塞, reject=拒绝 |
| `enable_watchdog` | 启用看门狗 | True | 检测死锁 |
| `watchdog_timeout` | 看门狗超时（秒） | 180-600 | 根据文件大小调整 |
| `log_executor_stats` | 启用统计日志 | True | 实时监控 |
| `stats_interval` | 统计日志间隔（秒） | 15-60 | 日志频率 |

### 4.2 高级配置

#### 自动计算 per_file_max_workers

系统会根据以下公式自动计算每文件的 worker 数：

```python
per_file_max_workers = max(
    10,  # 最小值
    int(global_api_concurrency * 1.5 / max_concurrent_files)
)

# 示例：
# Balanced 预设
# = max(10, int(75 * 1.5 / 4))
# = max(10, int(112.5 / 4))
# = max(10, 28)
# = 28
```

**为什么是 1.5 倍？**
- 考虑到并非所有 worker 都在同时执行 API 调用
- 有些 worker 在等待响应、处理数据、写入文件
- 1.5 倍的 oversubscription 确保 API 槽位充分利用

#### 队列大小计算

推荐队列大小 = 并发数 × 缓冲系数

```python
# Conservative: 2 × 35 × 3 = 210 ≈ 200
# Balanced: 4 × 28 × 4.5 = 504 ≈ 500
# Aggressive: 8 × 18 × 7 = 1008 ≈ 1000
```

**缓冲系数选择：**
- 保守：3-4（最低内存）
- 均衡：4-5（平衡）
- 激进：7-10（最高吞吐）

### 4.3 自定义配置示例

#### 示例 1：针对 OpenAI API（60 req/min）

```python
custom_config = {
    'max_concurrent_files': 3,          # 减少文件并发
    'global_api_concurrency': 50,       # 低于 60 限制
    'per_file_max_workers': 25,         # 3 × 25 = 75 理论
    'file_min_api_guarantee': 8,        # 3 × 8 = 24 保留
    'global_task_queue_size': 300,      # 较小队列
    'watchdog_timeout': 400,            # 较长超时
}
```

#### 示例 2：内存受限（8GB RAM）

```python
low_memory_config = {
    'max_concurrent_files': 2,          # 最少文件并发
    'global_api_concurrency': 40,       # 较低API并发
    'per_file_max_workers': 30,         # 2 × 30 = 60 理论
    'file_min_api_guarantee': 10,
    'global_task_queue_size': 150,      # 最小队列
    'watchdog_timeout': 600,
}
```

#### 示例 3：追求速度（32GB RAM）

```python
high_performance_config = {
    'max_concurrent_files': 10,         # 高文件并发
    'global_api_concurrency': 120,      # 高API并发
    'per_file_max_workers': 18,         # 10 × 18 = 180 理论
    'file_min_api_guarantee': 8,
    'global_task_queue_size': 1500,     # 大队列
    'watchdog_timeout': 180,            # 短超时
}
```

---

## 5. 性能对比与调优 / Performance Tuning

### 5.1 批量并发 vs 单文件顺序

#### 性能对比表

| 指标 | 批量并发 | 单文件顺序（Conservative） | 单文件顺序（Balanced） | 单文件顺序（Aggressive） |
|------|---------|------------------------|---------------------|----------------------|
| **文件并发** | 20 | 2 | 4 | 8 |
| **API并发** | 无限制 | 50 | 75 | 100 |
| **理论任务数** | 2000+ | 70 | 112 | 144 |
| **内存占用** | 8-12GB | 3GB | 4GB | 6GB |
| **吞吐量** | 120 文件/小时 | 20-30 | 40-60 | 60-80 |
| **适用文件数** | < 50 | 1000+ | 100-500 | < 100 |
| **稳定性** | 中 | 极高 | 高 | 中高 |
| **OOM风险** | 高 | 极低 | 低 | 中 |
| **429风险** | 高 | 极低 | 低 | 中 |

#### 何时选择批量并发

✅ **推荐场景：**
- 文件数量 < 50
- 系统 RAM ≥ 16GB
- API 无严格限流
- 追求最快速度
- 短时间任务（< 2小时）

#### 何时选择单文件顺序

✅ **推荐场景：**
- 文件数量 ≥ 50（尤其是 1000+）
- 系统 RAM 8-16GB
- API 有限流（如 OpenAI 60 req/min）
- 需要长时间稳定运行
- 需要精确进度追踪

### 5.2 预设选择建议

#### 决策树

```
开始：你有多少个文件要处理？

├─ < 50 文件
│  └─ 使用批量并发模式（最快）
│
├─ 50-100 文件
│  ├─ 系统资源充足 → Aggressive 预设
│  └─ 系统资源有限 → Balanced 预设
│
├─ 100-500 文件
│  └─ Balanced 预设（推荐）
│
└─ 500+ 文件
   ├─ 500-1000 → Balanced 预设
   └─ 1000+ → Conservative 预设
```

#### API 限流考虑

| API 提供商 | 限流 | 推荐配置 |
|-----------|------|---------|
| **Google Gemini** | 500 req/min | Balanced/Aggressive (global_api_concurrency: 75-100) |
| **OpenAI GPT-4** | 60 req/min | Conservative (global_api_concurrency: 50) |
| **自建 API** | 自定义 | 根据实际限流调整 |

### 5.3 参数调优指南

#### 步骤 1：确定瓶颈

观察日志和系统指标：

```bash
# 检查 CPU 占用
# - < 30%: 提高并发度
# - > 80%: 降低并发度

# 检查内存占用
# - < 50%: 可以提高 max_concurrent_files
# - > 80%: 降低 max_concurrent_files 或 global_task_queue_size

# 检查 API 错误率
# - 大量 429 错误: 降低 global_api_concurrency
# - 很少 429: 可以提高 global_api_concurrency
```

#### 步骤 2：调整参数

**场景 A：速度太慢**

```python
# 调整方向：提高并发
'max_concurrent_files': 6,          # ↑ 从 4
'global_api_concurrency': 90,       # ↑ 从 75
'global_task_queue_size': 700,      # ↑ 从 500
```

**场景 B：内存占用过高**

```python
# 调整方向：降低并发和队列
'max_concurrent_files': 3,          # ↓ 从 4
'global_task_queue_size': 300,      # ↓ 从 500
```

**场景 C：大量 429 错误**

```python
# 调整方向：降低 API 并发
'global_api_concurrency': 60,       # ↓ 从 75
```

#### 步骤 3：监控和迭代

```bash
# 1. 运行一小批测试文件（10-20个）
python main.py

# 2. 观察日志中的统计信息
#    [ExecutorMonitor] Stats:
#      - Active files: 4/4
#      - API slots used: 68/75
#      - Queue size: 245/500

# 3. 根据统计调整参数
#    - API slots used < 50% → 可以降低 global_api_concurrency
#    - Queue size > 80% → 可能需要增加 global_task_queue_size
#    - Active files < max → 可能是 API 瓶颈，考虑增加 global_api_concurrency

# 4. 重新测试，直到满意
```

---

## 6. 故障排查 / Troubleshooting

### 6.1 常见问题

#### 问题 1：看门狗超时告警

**症状：**
```
[WARNING] ⚠️ [Watchdog] No progress for 305.2s - Possible deadlock!
```

**可能原因：**
1. 文件过大，单个批次处理时间超过 watchdog_timeout
2. API 响应慢
3. 真的死锁了

**解决方案：**
```python
# 方案1：增加超时时间
'watchdog_timeout': 600,  # 从 300 增加到 600

# 方案2：检查 API 响应时间
# 查看日志：logs/pdf_extractor.log
# 搜索关键字：[API] Response time

# 方案3：检查是否真的死锁
# 查看进程状态：htop 或任务管理器
# 如果 CPU 占用为 0，可能是死锁
```

#### 问题 2：内存占用持续增长

**症状：**
- 系统内存占用持续上升
- 最终可能 OOM 崩溃

**可能原因：**
1. `global_task_queue_size` 设置过大
2. 任务内存泄漏

**解决方案：**
```python
# 方案1：减小队列大小
'global_task_queue_size': 200,  # 从 500 减小到 200

# 方案2：减少并发数
'max_concurrent_files': 2,  # 从 4 减小到 2
```

#### 问题 3：大量 429 错误

**症状：**
```
[ERROR] API Error: 429 - Rate limit exceeded
```

**可能原因：**
- `global_api_concurrency` 设置过高，超过 API 限流

**解决方案：**
```python
# 减小全局 API 并发
'global_api_concurrency': 50,  # 从 75 减小到 50
```

#### 问题 4：进度缓慢

**症状：**
- 任务完成时间远超预期
- CPU 占用很低（< 30%）

**可能原因：**
1. 并发度设置过低
2. API 限流导致等待

**解决方案：**
```python
# 方案1：提高并发度
'max_concurrent_files': 6,  # 从 4 提高到 6
'global_api_concurrency': 90,  # 从 75 提高到 90

# 方案2：检查 API 限流
# 查看日志中 429 错误的数量
# 如果没有 429，说明可以安全提高并发
```

### 6.2 监控和日志

#### 执行器统计日志

启用 `log_executor_stats` 后，会定期输出统计信息：

```
[ExecutorMonitor] Stats (30s interval):
  • Active files: 4/4 (100%)
  • API slots used: 68/75 (91%)
  • Task queue size: 245/500 (49%)
  • Completed files: 12
  • Pending files: 88
  • Watchdog: OK (last feed: 5s ago)
```

**指标说明：**

| 指标 | 说明 | 健康值 |
|------|------|--------|
| **Active files** | 当前处理中的文件数 | = max_concurrent_files |
| **API slots used** | 当前使用的 API 槽位 | 70-90% |
| **Task queue size** | 当前队列中的任务数 | < 80% |
| **Watchdog** | 看门狗状态 | OK |

**异常模式：**

```
# 模式1：API 瓶颈
API slots used: 74/75 (99%)  # 接近上限
Task queue size: 450/500 (90%)  # 队列积压
→ 增加 global_api_concurrency

# 模式2：文件瓶颈
Active files: 2/4 (50%)  # 未充分利用
API slots used: 35/75 (47%)  # 低利用率
→ 可能是文件准备慢，检查 I/O

# 模式3：内存压力
Task queue size: 495/500 (99%)  # 队列几乎满
→ 减小 max_concurrent_files 或增加 global_task_queue_size
```

#### 日志文件位置

```
logs/
├── sessions/
│   └── session_20251204_143052.log  # 会话总日志
├── sequential_executor.log           # 执行器日志
├── pdf_extractor.log                # PDF 提取日志
├── translator.log                   # 翻译日志
└── html_generator.log               # HTML 生成日志
```

---

## 7. 最佳实践 / Best Practices

### 7.1 文件数量规划

#### 分批处理建议

对于超大批量文件（5000+），建议分批处理：

```python
# 方式1：手动分批（推荐）
# 将文件分成多个批次目录
input/
├── batch1/  # 1-1000
├── batch2/  # 1001-2000
├── batch3/  # 2001-3000
└── ...

# 每次处理一个批次
python main.py
# 选择 batch1 目录
```

**优势：**
- ✅ 每批处理完成后可以验证结果
- ✅ 降低单次任务失败风险
- ✅ 方便中途调整参数

#### 测试和验证流程

```
1. 小规模测试（10-20文件）
   ├─ 验证配置正确性
   ├─ 估算处理时间
   └─ 检查资源占用

2. 中等规模验证（100-200文件）
   ├─ 验证长时间稳定性
   ├─ 监控内存趋势
   └─ 优化参数

3. 全量处理
   └─ 使用验证过的配置
```

### 7.2 系统资源配置

#### 硬件推荐配置

| 文件数量 | 推荐配置 | 预设 |
|---------|---------|------|
| **< 100** | 16GB RAM, 4核 | Balanced/Aggressive |
| **100-500** | 16GB RAM, 8核 | Balanced |
| **500-1000** | 12GB RAM, 4核 | Conservative/Balanced |
| **1000+** | 8GB RAM, 4核 | Conservative |

#### 操作系统优化

**Windows：**
```bash
# 提高最大打开文件数（注册表）
# HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\SubSystems
# 修改 Windows 值中的 /HEAP 参数
```

**Linux/Mac：**
```bash
# 提高文件描述符限制
ulimit -n 10000

# 永久设置（添加到 ~/.bashrc）
echo "ulimit -n 10000" >> ~/.bashrc
```

### 7.3 长时间运行建议

#### 使用 screen/tmux（Linux/Mac）

```bash
# 安装 screen
sudo apt install screen  # Ubuntu
brew install screen      # Mac

# 启动 screen 会话
screen -S journal_processing

# 运行任务
python main.py

# 分离会话：Ctrl+A, D
# 重新连接：screen -r journal_processing
```

#### 使用任务计划（Windows）

```bash
# 创建批处理文件：run_processing.bat
@echo off
cd C:\path\to\Journal-Articles-Extraction-Workflow-main
python main.py

# 使用任务计划程序定时运行
# 控制面板 → 管理工具 → 任务计划程序
```

#### 错误恢复策略

```python
# 启用断点续传（系统自动支持）
# 如果任务中断，重新运行 main.py

python main.py

# 系统会自动检测未完成的会话
# 提示是否恢复：
# 发现未完成的处理会话
# 会话时间: 2025-12-04 14:30:52
#   - 总文件: 1000
#   - 已完成: 456
#   - 失败: 12
#   - 未处理: 532
#
# 是否恢复此会话? (y/N): y
```

**自动化恢复脚本：**

```bash
# auto_resume.sh (Linux/Mac)
#!/bin/bash
while true; do
    python main.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "Processing completed successfully"
        break
    else
        echo "Process crashed, restarting in 10s..."
        sleep 10
    fi
done
```

---

## 📊 性能基准

**测试环境：**
- CPU: Intel i7-12700K (12核24线程)
- RAM: 16GB DDR4
- API: Google Gemini 2.5 Flash
- 文件: 100页 PDF × 500 个

**测试结果：**

| 预设 | 总时间 | 平均速度 | 内存峰值 | CPU平均 | 成功率 |
|------|--------|---------|---------|---------|--------|
| **Conservative** | 18小时 | 28 文件/小时 | 2.8GB | 25% | 99.8% |
| **Balanced** | 10小时 | 50 文件/小时 | 3.9GB | 42% | 99.5% |
| **Aggressive** | 7小时 | 71 文件/小时 | 5.5GB | 65% | 98.9% |
| **Batch Concurrent** | 4小时 | 125 文件/小时 | 9.2GB | 78% | 97.5% |

**结论：**
- Conservative: 最适合超长时间运行，稳定性最高
- Balanced: 最佳性价比，推荐用于生产环境
- Aggressive: 接近批量并发的速度，但更可控
- Batch Concurrent: 最快，但适合小批量

---

## 🔗 相关文档

- 📚 [系统架构](ARCHITECTURE.md) - 完整架构设计
- 🔧 [配置说明](CONFIGURATION.md) - 所有配置参数
- 🔄 [工作流程](WORKFLOW.md) - 11 阶段处理流程
- 📝 [更新日志](CHANGELOG.md) - v2.12.0 新特性
- 🐛 [故障排查](TROUBLESHOOTING.md) - 常见问题解决

---

📖 [返回主文档](../README.md)
