"""
文章翻译引擎（精简版）
只保留核心翻译功能，但保留完整的术语库逻辑
"""

import re
import requests
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as URLLibRetry
from retry_utils import APIRetryHandler, RetryConfig


class RateLimiter:
    """自适应速率限制器"""

    def __init__(self, initial_workers: int, max_workers: int, min_workers: int,
                 backoff: float, increase: float, success_threshold: float, increase_interval: int):
        self.current_workers = initial_workers
        self.max_workers = max_workers
        self.min_workers = min_workers
        self.backoff = backoff
        self.increase = increase
        self.success_threshold = success_threshold
        self.increase_interval = increase_interval

        self.success_count = 0
        self.total_count = 0
        self.last_increase_time = time.time()
        self.lock = Lock()

    def on_rate_limit_error(self):
        """遇到429错误，降低并发"""
        with self.lock:
            old_workers = self.current_workers
            self.current_workers = max(self.min_workers, int(self.current_workers * self.backoff))
            print(f"⚠️ 遇到速率限制，降低并发: {old_workers} -> {self.current_workers}")

    def on_success(self):
        """成功请求，统计成功率"""
        with self.lock:
            self.success_count += 1
            self.total_count += 1

            # 计算成功率
            if self.total_count >= 20:  # 至少20个样本
                success_rate = self.success_count / self.total_count
                current_time = time.time()

                # 如果成功率高且距离上次增加已过一段时间
                if (success_rate >= self.success_threshold and
                        current_time - self.last_increase_time >= self.increase_interval and
                        self.current_workers < self.max_workers):
                    old_workers = self.current_workers
                    self.current_workers = min(self.max_workers, int(self.current_workers * self.increase))
                    self.last_increase_time = current_time
                    print(f"✓ 提升并发: {old_workers} -> {self.current_workers}")

                    # 重置计数器
                    self.success_count = 0
                    self.total_count = 0

    def on_failure(self):
        """请求失败（非429错误）"""
        with self.lock:
            self.total_count += 1

    def get_current_workers(self) -> int:
        """获取当前并发数"""
        with self.lock:
            return self.current_workers


class ArticleTranslator:
    """文章翻译引擎"""

    def __init__(
        self,
        api_key: str,
        api_url: str,
        model: str,
        glossary: Optional[Dict[str, str]] = None,
        case_sensitive: bool = False,
        whole_word_only: bool = True,
        config: Optional[Dict] = None
    ):
        """
        初始化翻译器

        Args:
            api_key: API密钥
            api_url: API基础URL
            model: 模型名称
            glossary: 术语表字典 {"English": "中文"}
            case_sensitive: 术语替换是否区分大小写（默认False）
            whole_word_only: 是否只匹配完整单词（默认True）
            config: 配置字典（用于读取API参数和并发配置）
        """
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.model = model
        self.chat_endpoint = f"{self.api_url}/chat/completions"
        self.glossary = glossary or {}
        self.case_sensitive = case_sensitive
        self.whole_word_only = whole_word_only

        # 从config读取参数（如果提供）
        self.config = config or {}
        self.timeout = self.config.get('api', {}).get('timeout', 120)
        self.temperature = self.config.get('api', {}).get('temperature', 0.3)
        self.max_tokens = self.config.get('api', {}).get('max_tokens', 65536)

        # ===== 新增：创建共享的 Session 对象进行连接复用 =====
        self.session = requests.Session()

        # 配置连接池：池大小 = 最大并发数 * 2
        max_workers = self.config.get('concurrency', {}).get('max_translation_workers', 100)
        pool_size = min(max_workers * 2, 200)  # 限制最大200

        # 配置 HTTPAdapter（连接复用和连接池管理）
        adapter = HTTPAdapter(
            pool_connections=pool_size,      # 连接池数量
            pool_maxsize=pool_size,          # 连接池最大大小
            max_retries=0,                   # 禁用urllib3自动重试（我们用自己的重试逻辑）
            pool_block=True                  # 连接池满时阻塞等待（避免创建过多连接）
        )

        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # 设置默认请求头
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Connection": "keep-alive"       # 保持连接
        })

        # 强制禁用代理（多种方式确保生效）
        self.session.proxies = {}
        self.session.trust_env = False  # 忽略环境变量中的代理设置
        # ===== 连接复用配置结束 =====

        # 初始化速率限制器
        concurrency_config = self.config.get('concurrency', {})
        self.rate_limiter = RateLimiter(
            initial_workers=concurrency_config.get('initial_translation_workers', 20),
            max_workers=concurrency_config.get('max_translation_workers', 100),
            min_workers=concurrency_config.get('min_translation_workers', 1),
            backoff=concurrency_config.get('rate_limit_backoff', 0.5),
            increase=concurrency_config.get('rate_limit_increase', 1.2),
            success_threshold=concurrency_config.get('success_threshold', 0.95),
            increase_interval=concurrency_config.get('increase_interval', 30)
        )

        # 初始化重试处理器
        retry_config = self.config.get('retry', {})
        self.retry_handler = APIRetryHandler(
            config=RetryConfig(
                max_retries=retry_config.get('translation_max_retries', 3),
                initial_delay=retry_config.get('translation_initial_delay', 1.0),
                max_delay=retry_config.get('translation_max_delay', 30.0),
                exponential_base=retry_config.get('translation_exponential_base', 2.0),
                retry_on_dns_error=retry_config.get('retry_on_dns_error', True),
                retry_on_connection_error=retry_config.get('retry_on_connection_error', True),
                retry_on_timeout=retry_config.get('retry_on_timeout', True),
                retry_on_5xx=retry_config.get('retry_on_5xx', True),
                retry_on_429=retry_config.get('retry_on_429_translation', False)  # 429由rate_limiter处理
            ),
            logger=None,  # 翻译器通常没有logger，使用print
            context_provider=lambda: f"[文件: {self.current_file}]"  # 提供文件上下文
        )

        # 术语替换统计
        self.total_replacements = 0
        self.total_terms_used = 0
        self._replacement_lock = Lock()

        # 日志相关（每个子进程有独立实例，不需要锁）
        self.log_dir = Path("logs/translation")
        self.current_file = "unknown"
        self.request_counter = 0

        # 失败文本记录
        self.failed_texts_log = Path("logs/total_issue_files.jsonl")
        self.failed_texts_log.parent.mkdir(parents=True, exist_ok=True)

        # 备用模型配置（用于质量问题时切换）- 从config读取
        self.fallback_model = self.config.get('api', {}).get('fallback_translation_model', 'gemini-2.0-flash-exp')
        self.original_model = self.model  # 保存原始模型

    def translate(self, text: str, context: Optional[Dict] = None, text_id: Optional[str] = None) -> str:
        """
        翻译文本

        Args:
            text: 待翻译文本
            context: 上下文信息 {
                'chapter_title': '章节标题',
                'chapter_summary': '章节摘要',
                'keywords': ['关键词1', '关键词2']
            }
            text_id: 文本唯一标识（用于失败追踪）

        Returns:
            翻译后的文本
        """
        if not text or not text.strip():
            return ""

        # 检查文本长度（防止超长请求）
        text_length = len(text)
        if text_length > 50000:  # 超过5万字符
            print(f"[WARNING] Text too long: {text_length} chars, will split")
            # 分段翻译
            return self._translate_long_text(text, context)

        # 正常翻译流程

        # 1. 应用术语表（不显示详细日志）
        text_with_glossary, replacement_count = self.apply_glossary(text, show_log=False)

        # 累计术语替换统计（线程安全）
        if replacement_count > 0:
            with self._replacement_lock:
                self.total_replacements += replacement_count

        # 2. 构建提示词
        prompt = self._build_prompt(text_with_glossary, context)

        # 获取请求ID（子进程独立，不需要锁）
        self.request_counter += 1
        request_id = self.request_counter

        # 3. 调用API（带质量检查的重试机制）
        start_time = time.time()

        payload = None
        response_json = None
        final_error = None

        # 从配置读取最大重试次数（包括质量检查失败的重试）
        max_quality_retries = self.config.get('retry', {}).get('translation_max_retries', 30)

        # 跟踪连续"完全未翻译"的次数
        consecutive_untranslated = 0
        max_consecutive_untranslated = 3  # 连续3次完全未翻译就放弃

        # 标记是否已经切换到fallback模型
        switched_to_fallback = False

        for attempt in range(max_quality_retries):
            attempt_start = time.time()
            try:
                # 添加小延迟（减轻服务器压力，避免连接被强制关闭）
                if attempt > 0:
                    time.sleep(0.1 * attempt)

                # 如果第一次尝试失败且还未切换，则临时切换到fallback模型
                if attempt == 1 and not switched_to_fallback and self.fallback_model:
                    print(f"  → 切换到更好的模型: {self.fallback_model}")
                    self.model = self.fallback_model
                    switched_to_fallback = True

                payload, response_json, translation = self._call_llm(prompt, request_id)

                # 清理翻译结果
                translation = self._clean_output(translation)

                # ===== 新增：翻译质量检查 =====
                quality_check_passed, issue_reason = self._check_translation_quality(
                    original_text=text,
                    translated_text=translation
                )

                if not quality_check_passed:
                    # 检查是否是"完全未翻译"
                    is_untranslated = "完全未翻译" in issue_reason

                    if is_untranslated:
                        consecutive_untranslated += 1
                    else:
                        consecutive_untranslated = 0  # 重置计数

                    # 质量检查失败，记录并重试
                    print(f"[WARNING] [文件: {self.current_file}] 翻译质量异常: {issue_reason}")
                    print(f"  原文长度: {len(text)}, 译文长度: {len(translation)}")

                    # 如果连续多次完全未翻译，提前放弃
                    if consecutive_untranslated >= max_consecutive_untranslated:
                        print(f"  ✗ 连续{consecutive_untranslated}次完全未翻译，可能是OCR错误或API无法识别的文本")
                        print(f"  → 停止重试，返回原文")
                        self._log_quality_issue(
                            request_id=request_id,
                            original_text=text,
                            translated_text=translation,
                            issue_reason=f"{issue_reason} (连续{consecutive_untranslated}次，停止重试)",
                            attempt=attempt + 1,
                            used_fallback_model=switched_to_fallback
                        )
                        # 恢复原始模型
                        if switched_to_fallback:
                            self.model = self.original_model
                        return text

                    if attempt < max_quality_retries - 1:
                        print(f"  → 正在重新翻译 (第{attempt + 2}次尝试)...")
                        # 记录质量问题
                        self._log_quality_issue(
                            request_id=request_id,
                            original_text=text,
                            translated_text=translation,
                            issue_reason=issue_reason,
                            attempt=attempt + 1,
                            used_fallback_model=switched_to_fallback
                        )
                        continue  # 重新尝试
                    else:
                        # 已达最大重试次数，返回原文
                        print(f"  ✗ 已达最大重试次数({max_quality_retries})，返回原文")
                        self._log_quality_issue(
                            request_id=request_id,
                            original_text=text,
                            translated_text=translation,
                            issue_reason=f"{issue_reason} (已达最大重试次数，返回原文)",
                            attempt=attempt + 1,
                            used_fallback_model=switched_to_fallback
                        )
                        # 恢复原始模型
                        if switched_to_fallback:
                            self.model = self.original_model
                        # 直接返回原文，不使用有问题的译文
                        return text

                # 质量检查通过，重置计数器
                consecutive_untranslated = 0

                # 记录成功的请求和响应
                self._log_translation(
                    request_id=request_id,
                    payload=payload,
                    response=response_json,
                    error=None,
                    attempts=attempt + 1
                )

                # 恢复原始模型（成功翻译后）
                if switched_to_fallback:
                    self.model = self.original_model

                return translation

            except Exception as e:
                final_error = str(e)

                # 打印错误信息（更详细）
                error_preview = final_error[:200] if len(final_error) > 200 else final_error
                print(f"[WARNING] [文件: {self.current_file}] 翻译请求失败 (第{attempt + 1}/{max_quality_retries}次): {error_preview}")

                if attempt < max_quality_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  → {wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    # 最后一次失败，记录错误
                    print(f"  ✗ 已达最大重试次数({max_quality_retries})，返回原文")

                    # 记录失败文本
                    self._log_failed_text(
                        text_id=text_id,
                        original_text=text,
                        error=final_error,
                        attempts=max_quality_retries,
                        context=context
                    )

                    self._log_translation(
                        request_id=request_id,
                        payload=payload,
                        response=None,
                        error=final_error,
                        attempts=attempt + 1
                    )
                    # 恢复原始模型（失败时）
                    if switched_to_fallback:
                        self.model = self.original_model
                    # 返回原文（不会影响整个文件）
                    return text

    def _call_llm(self, prompt: str, request_id: int) -> str:
        """
        调用LLM API（使用 Session 进行连接复用）

        Args:
            prompt: 提示词
            request_id: 请求ID（用于日志记录）

        Returns:
            (payload, response_json, translated_text) 元组
        """
        messages = [
            {
                "role": "system",
                "content": "你是专业的学术文档翻译助手。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False
        }

        # 用于收集重试事件
        retry_events = []
        result = None
        final_error = None

        # 重试回调函数
        def on_retry(attempt: int, error_type: str, error_detail: str):
            retry_events.append({
                "attempt": attempt,
                "error_type": error_type,
                "error_detail": error_detail,
                "timestamp": datetime.now().isoformat()
            })

        # 使用重试处理器包装API调用
        def _make_api_call():
            # 使用共享的 Session 对象（自动复用连接）
            response = self.session.post(
                self.chat_endpoint,
                json=payload,
                timeout=self.timeout,
                verify=True
            )

            # 处理429错误
            if response.status_code == 429:
                self.rate_limiter.on_rate_limit_error()
                response.raise_for_status()

            response.raise_for_status()

            # 尝试解析JSON，失败时显示原始响应
            try:
                return response.json()
            except json.JSONDecodeError as e:
                # JSON解析失败，记录原始响应
                raw_text = response.text[:1000]  # 只取前1000字符
                error_msg = f"JSON解析失败: {str(e)}\n原始响应: {raw_text}"
                raise Exception(error_msg)

        try:
            # 执行带重试的API调用
            result = self.retry_handler.execute_with_retry(_make_api_call, on_retry_callback=on_retry)

            # 记录成功
            self.rate_limiter.on_success()

            # 安全地提取翻译文本，处理可能的结构错误
            try:
                translated_text = result['choices'][0]['message']['content'].strip()
            except (KeyError, IndexError, TypeError) as e:
                # API返回结构不符合预期
                error_msg = f"API返回结构错误: {str(e)}\n返回内容: {str(result)[:500]}"
                raise Exception(error_msg)

            return payload, result, translated_text

        except Exception as e:
            # 记录失败信息
            final_error = str(e)
            raise

        finally:
            # 无论成功还是失败，都记录重试事件（如果有）
            if retry_events:
                self._log_retry_events(
                    request_id=request_id,
                    payload=payload,
                    response=result,
                    retry_events=retry_events,
                    final_error=final_error
                )

    def apply_glossary(self, text: str, show_log: bool = False) -> Tuple[str, int]:
        """
        应用术语库进行预翻译替换（完整版逻辑）

        Args:
            text: 原始文本
            show_log: 是否显示替换日志

        Returns:
            (替换后的文本, 替换次数)
        """
        if not self.glossary or not text:
            return text, 0

        # URL保护
        modified_text, url_placeholders = self._protect_urls(text)

        # 术语替换
        replacement_count = 0
        replaced_terms = []

        # 按术语长度排序（长的先替换）
        sorted_terms = sorted(self.glossary.items(), key=lambda x: len(x[0]), reverse=True)

        for source_term, target_term in sorted_terms:
            if not source_term or not target_term:
                continue

            # 构建正则表达式
            pattern = r'\b' + re.escape(source_term) + r'\b' if self.whole_word_only else re.escape(source_term)
            flags = 0 if self.case_sensitive else re.IGNORECASE

            # 查找匹配
            matches = re.findall(pattern, modified_text, flags=flags)
            if matches:
                count = len(matches)
                modified_text = re.sub(pattern, target_term, modified_text, flags=flags)
                replacement_count += count
                replaced_terms.append((source_term, target_term, count))

        # 显示替换日志
        if show_log and replaced_terms:
            print(f"  术语替换: {len(replaced_terms)} 个术语，共 {replacement_count} 处")

        # 恢复URL
        modified_text = self._restore_urls(modified_text, url_placeholders)

        return modified_text, replacement_count

    def _protect_urls(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        提取URL并用占位符替换

        Args:
            text: 原始文本

        Returns:
            (替换后的文本, {占位符: URL})
        """
        # 合并URL匹配正则
        url_pattern = (
            r'(?:https?|ftp|ftps)://[^\s<>"\'\)]+|'
            r'(?:dx\.)?doi\.org/[^\s<>"\'\)]+|'
            r'www\.[a-zA-Z0-9][-a-zA-Z0-9]*\.[^\s<>"\'\)]+|'
            r'\[([^\]]+)\]\(([^\)]+)\)'
        )

        urls = re.findall(url_pattern, text)

        # 展平Markdown链接
        url_list = []
        for match in urls:
            if isinstance(match, tuple):
                url_list.append(f'[{match[0]}]({match[1]})')
            else:
                url_list.append(match)

        # 去重并按长度排序
        url_list = sorted(set(url_list), key=len, reverse=True)

        # 创建占位符
        url_placeholders = {}
        modified_text = text
        for i, url in enumerate(url_list):
            placeholder = f"__URL_PLACEHOLDER_{i}__"
            url_placeholders[placeholder] = url
            modified_text = modified_text.replace(url, placeholder)

        return modified_text, url_placeholders

    def _restore_urls(self, text: str, url_placeholders: Dict[str, str]) -> str:
        """恢复URL占位符"""
        for placeholder, url in url_placeholders.items():
            text = text.replace(placeholder, url)
        return text

    def _build_prompt(self, text: str, context: Optional[Dict]) -> str:
        """
        构建翻译提示词

        Args:
            text: 待翻译文本
            context: 上下文信息

        Returns:
            完整提示词
        """
        prompt_parts = [
            "请将以下英语或者俄语翻译成中文",
            "",
            "要求：",
            "1. 保持学术风格和专业术语准确性",
            "2. 保留原文的段落结构和格式",
            "3. **保持所有URL链接（http://或https://开头）原样不变，不要翻译或修改**",
            "4. **直接输出翻译结果**，严禁废话、严禁分析",
            "5. 不要添加\"译文:\"、\"翻译:\"等前缀",
            "6. 如果有被误翻译、误术语替换的URL，记得进行修复",
            "7. 发送给你的所有文本都需要被翻译为中文，不要漏译",
            "8. **如果遇到OCR识别错误或无法识别的混乱文本，请尽力翻译可识别部分，无法识别的保持原样**"
        ]

        # 添加上下文（使用明确的分隔符，避免被翻译）
        if context:
            prompt_parts.append("")
            prompt_parts.append("=" * 50)
            prompt_parts.append("【参考上下文 - 不要翻译此部分】")

            if context.get('chapter_title'):
                prompt_parts.append(f"章节: {context['chapter_title']}")

            if context.get('chapter_summary'):
                prompt_parts.append(f"摘要: {context['chapter_summary']}")

            if context.get('keywords'):
                keywords = ', '.join(context['keywords'])
                prompt_parts.append(f"关键词: {keywords}")

            # 添加上下文窗口（前后文）
            if context.get('prev_text') or context.get('next_text'):
                prompt_parts.append("")
                if context.get('prev_text'):
                    prev = context['prev_text'].strip()
                    if prev:
                        prompt_parts.append(f"上文: ...{prev}")

                if context.get('next_text'):
                    next_text = context['next_text'].strip()
                    if next_text:
                        prompt_parts.append(f"下文: {next_text}...")

            prompt_parts.append("=" * 50)

        # 添加待翻译文本
        prompt_parts.append("")
        prompt_parts.append("【待翻译文本】")
        prompt_parts.append(text)
        prompt_parts.append("")
        prompt_parts.append("【请直接输出中文翻译】")

        return "\n".join(prompt_parts)

    def _clean_output(self, text: str) -> str:
        """
        清理翻译结果中的额外标记

        Args:
            text: 原始翻译结果

        Returns:
            清理后的译文
        """
        cleaned = text.strip()

        # 移除常见的前缀标记（合并正则）
        prefixes = r'^(?:译文|翻译|【译文】|【翻译】|\[译文\]|\[翻译\]|Translation|以下是翻译|翻译如下|翻译结果)[：:\s]+'
        cleaned = re.sub(prefixes, '', cleaned, flags=re.IGNORECASE)

        # 移除首尾的引号（统一处理）
        quote_pairs = [('"', '"'), ('「', '」'), ('『', '』'), ('《', '》')]
        for open_q, close_q in quote_pairs:
            if cleaned.startswith(open_q) and cleaned.endswith(close_q):
                cleaned = cleaned[1:-1]
                break

        return cleaned.strip()

    def translate_batch(self, tasks: List[Tuple[str, Optional[Dict]]]) -> List[str]:
        """
        批量并发翻译（使用自适应速率限制）

        Args:
            tasks: [(text, context), ...] 待翻译任务列表

        Returns:
            翻译结果列表
        """
        if not tasks:
            return []

        # 重置术语替换统计
        self.total_replacements = 0

        results = [None] * len(tasks)

        # 使用动态并发数
        def translate_single(index: int, text: str, context: Optional[Dict]) -> Tuple[int, str]:
            """翻译单个文本并返回索引和结果"""
            # 从context中提取text_id（如果有）
            text_id = context.get('text_id') if context else None
            translation = self.translate(text, context, text_id=text_id)
            return index, translation

        # 并发翻译
        with ThreadPoolExecutor(max_workers=self.rate_limiter.get_current_workers()) as executor:
            futures = {
                executor.submit(translate_single, i, text, context): i
                for i, (text, context) in enumerate(tasks)
            }

            for future in as_completed(futures):
                try:
                    index, translation = future.result()
                    results[index] = translation
                except Exception as e:
                    # 失败时返回原文，并显示详细错误
                    index = futures[future]
                    results[index] = tasks[index][0]
                    self.rate_limiter.on_failure()

                    # 打印详细错误信息
                    error_msg = str(e)
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    print(f"[ERROR] 翻译失败 (任务 {index+1}): {error_msg}")

        # 显示术语替换总计
        if self.total_replacements > 0:
            print(f"\n📊 术语替换统计: 共替换 {self.total_replacements} 处\n")

        return results

    def _translate_long_text(self, text: str, context: Optional[Dict] = None) -> str:
        """
        翻译超长文本（分段处理）

        Args:
            text: 超长文本
            context: 上下文

        Returns:
            翻译结果
        """
        # 按段落分割（保留空行）
        paragraphs = text.split('\n\n')

        # 分组：每组不超过20000字符
        groups = []
        current_group = []
        current_length = 0

        for para in paragraphs:
            para_length = len(para)

            if current_length + para_length > 20000 and current_group:
                # 当前组已满，开始新组
                groups.append('\n\n'.join(current_group))
                current_group = [para]
                current_length = para_length
            else:
                current_group.append(para)
                current_length += para_length + 2  # +2 for \n\n

        # 添加最后一组
        if current_group:
            groups.append('\n\n'.join(current_group))

        print(f"[INFO] Split into {len(groups)} chunks for translation")

        # 逐组翻译
        translations = []
        for i, group in enumerate(groups):
            print(f"[INFO] Translating chunk {i+1}/{len(groups)} ({len(group)} chars)")
            translated = self.translate(group, context)  # 递归调用（但已经小于5万了）
            translations.append(translated)

        return '\n\n'.join(translations)

    def _log_retry_events(self, request_id: int, payload: dict, response: dict, retry_events: list, final_error: Optional[str] = None):
        """
        记录重试事件到 JSONL（无论成功还是失败）

        Args:
            request_id: 请求ID
            payload: 原始请求体
            response: API响应体（失败时为None）
            retry_events: 重试事件列表 [{"attempt": 1, "error_type": "请求超时", ...}, ...]
            final_error: 最终错误信息（成功时为None）
        """
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / f"{self.current_file}_retries.jsonl"

            retry_count = len(retry_events)
            total_attempts = retry_count + 1  # 总尝试次数 = 首次尝试 + 重试次数

            # 构建日志记录
            log_entry = {
                "request_id": request_id,
                "timestamp": datetime.now().isoformat(),
                "retry_count": retry_count,  # 重试次数（不包括首次尝试）
                "total_attempts": total_attempts,  # 总尝试次数（包括首次尝试）
                "retry_events": retry_events,
                "final_status": "failed" if final_error else "success",
                "final_error": final_error,
                "request": payload,
                "response": response
            }

            # 追加到重试日志文件
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            print(f"[WARNING] Failed to log retry events: {e}")

    def _log_translation(self, request_id: int, payload: dict, response: dict,
                        error: Optional[str], attempts: int):
        """
        记录翻译请求和响应到 JSONL 文件（每个文件一个 .jsonl）

        Args:
            request_id: 请求ID
            payload: 原始请求体
            response: 原始响应体（失败时为None）
            error: 错误信息（成功时为None）
            attempts: 尝试次数
        """
        try:
            # 确保日志目录存在
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / f"{self.current_file}.jsonl"

            # 构建日志记录
            log_entry = {
                "request_id": request_id,
                "timestamp": datetime.now().isoformat(),
                "attempts": attempts,
                "request": payload,
                "response": response if response else None,
                "error": error if error else None
            }

            # 追加到 JSONL 文件
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            # 日志失败不影响翻译，但打印警告
            print(f"[WARNING] Failed to log translation: {e}")

    def _check_translation_quality(self, original_text: str, translated_text: str) -> Tuple[bool, str]:
        """
        检查翻译质量，识别异常翻译结果

        Args:
            original_text: 原文
            translated_text: 译文

        Returns:
            (是否通过检查, 问题原因)
        """
        if not translated_text or not translated_text.strip():
            return False, "译文为空"

        original_len = len(original_text)
        translated_len = len(translated_text)

        # ===== 检测提示词泄漏（上下文泄漏）=====
        # 检查译文中是否包含提示词的元信息标记
        context_leak_indicators = [
            '【参考上下文', '【不要翻译', '【待翻译',
            '【请直接输出', '上文:', '下文:',
            '章节:', '摘要:', '关键词:',
            '==============='  # 分隔符泄漏
        ]
        for indicator in context_leak_indicators:
            if indicator in translated_text:
                return False, f"提示词泄漏 (包含'{indicator}')"

        # ===== 识别特殊内容类型 =====
        # 1. HTML表格
        is_html_table = (
            '<table>' in original_text.lower() or
            '<td>' in original_text.lower() or
            '<tr>' in original_text.lower()
        )

        # 2. 结构化数据（URL、邮箱、列表等）
        is_structured_data = (
            original_text.count('@') >= 2 or  # 多个邮箱
            original_text.count('http') >= 2 or  # 多个URL
            original_text.count('$') >= 3  # 多个价格/金额
        )

        # 3. URL/链接（单独的URL不需要翻译）
        is_url_only = (
            (original_text.strip().startswith('http') or
             original_text.strip().startswith('www.') or
             '.com' in original_text or '.org' in original_text) and
            len(original_text.split()) <= 3  # 最多3个单词
        )

        # 4. 联系信息（人名+邮箱+电话等）
        is_contact_info = (
            '@' in original_text and
            (original_text.count(':') >= 2 or  # E: T: 等标记
             ('+' in original_text and len(original_text) < 200))  # 电话号码
        )

        # 5. 版权/署名信息
        is_copyright_info = (
            original_text.strip().startswith('©') or
            original_text.strip().startswith('BY:') or
            'All rights reserved' in original_text
        )

        # 6. 检测原文是否已经是中文（目标语言）
        chinese_chars = sum(1 for char in original_text if '\u4e00' <= char <= '\u9fff')
        total_chars = len(original_text.strip())
        is_already_chinese = chinese_chars / max(total_chars, 1) > 0.3  # 超过30%是中文

        # 综合判断：是否应该跳过质量检查
        should_skip_similarity_check = (
            is_url_only or
            is_contact_info or
            is_copyright_info or
            is_already_chinese
        )

        # ===== 检测完全未翻译（原文=译文） =====
        # 跳过特定类型内容的相似度检查
        if should_skip_similarity_check:
            pass  # URL、联系信息、版权信息、中文原文等不需要检查相似度
        else:
            # 移除空格后比较
            orig_stripped = original_text.replace(' ', '').replace('\n', '')
            trans_stripped = translated_text.replace(' ', '').replace('\n', '')

            # 如果去空格后超过90%相同，视为未翻译
            # 但对HTML表格和结构化数据放宽到98%（因为标签、数据必须保持不变）
            if len(orig_stripped) > 50:  # 至少50字符
                from difflib import SequenceMatcher
                similarity = SequenceMatcher(None, orig_stripped, trans_stripped).ratio()
                similarity_threshold = 0.98 if (is_html_table or is_structured_data) else 0.9
                if similarity > similarity_threshold:
                    return False, f"完全未翻译 (相似度{similarity*100:.1f}%)"

        # 检查输出长度异常（译文远超原文）
        # 正常翻译：英译中0.8-1.2倍，俄译中1.0-1.3倍
        # 对于极短文本（<20字符），长度波动较大，放宽到10倍
        # 对于普通文本，译文超过原文5倍视为异常
        max_ratio = 10 if original_len < 20 else 5
        if translated_len > original_len * max_ratio:
            return False, f"译文长度异常过长 (原文{original_len}字符, 译文{translated_len}字符, 比例{translated_len/original_len:.1f}倍)"

        # 检查重复内容（模型幻觉循环）
        # ===== 优化：HTML表格和结构化数据跳过重复检查 =====
        if is_html_table or is_structured_data:
            pass  # HTML标签、列表结构、多个联系方式等本身会重复，不是幻觉
        else:
            # 如果译文中有连续重复的片段（长度>20字符），视为异常
            if translated_len > 100:
                # 检测连续重复模式
                for chunk_size in [20, 30, 50]:
                    for i in range(0, min(200, translated_len - chunk_size)):
                        chunk = translated_text[i:i+chunk_size]
                        # 检查这个片段是否在后续重复出现3次以上
                        count = translated_text.count(chunk)
                        if count >= 3:
                            return False, f"检测到重复内容循环 (片段'{chunk[:10]}...'重复{count}次)"

        # 4. 检查是否是模型输出的元信息（非翻译内容）
        meta_indicators = [
            "I will translate",
            "Here is the translation",
            "Translation:",
            "The translated text is",
            "I'll help you translate"
        ]
        first_50_chars = translated_text[:50].lower()
        for indicator in meta_indicators:
            if indicator.lower() in first_50_chars:
                return False, f"译文包含模型元信息 ('{indicator}')"

        # 所有检查通过
        return True, ""

    def _log_quality_issue(self, request_id: int, original_text: str, translated_text: str,
                          issue_reason: str, attempt: int, used_fallback_model: bool = False):
        """
        记录翻译质量问题到 JSONL

        Args:
            request_id: 请求ID
            original_text: 原文
            translated_text: 问题译文
            issue_reason: 问题原因
            attempt: 尝试次数
            used_fallback_model: 是否使用了fallback模型
        """
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / f"{self.current_file}_quality_issues.jsonl"

            # 构建日志记录
            log_entry = {
                "request_id": request_id,
                "timestamp": datetime.now().isoformat(),
                "attempt": attempt,
                "issue_reason": issue_reason,
                "original_length": len(original_text),
                "translated_length": len(translated_text),
                "length_ratio": len(translated_text) / len(original_text) if len(original_text) > 0 else 0,
                "original_text": original_text[:500],  # 只记录前500字符
                "translated_text": translated_text[:500],
                "used_model": self.model,  # 当前使用的模型
                "used_fallback_model": used_fallback_model  # 是否使用了fallback模型
            }

            # 追加到质量问题日志文件
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            print(f"[WARNING] Failed to log quality issue: {e}")

    def _log_failed_text(self, text_id: Optional[str], original_text: str, error: str,
                        attempts: int, context: Optional[Dict] = None):
        """
        记录30次重试后仍失败的文本

        Args:
            text_id: 文本唯一标识（例如：page_5_item_12）
            original_text: 原文
            error: 错误信息
            attempts: 尝试次数
            context: 上下文信息
        """
        try:
            # 构建日志记录
            log_entry = {
                "file_name": self.current_file,
                "text_id": text_id or "unknown",
                "timestamp": datetime.now().isoformat(),
                "attempts": attempts,
                "error": error[:500] if len(error) > 500 else error,  # 限制错误长度
                "original_text": original_text[:1000] if len(original_text) > 1000 else original_text,  # 限制文本长度
                "text_length": len(original_text),
                "context": {
                    "chapter_title": context.get('chapter_title') if context else None,
                    "page_idx": context.get('page_idx') if context else None
                }
            }

            # 追加到总失败日志
            with open(self.failed_texts_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            print(f"[WARNING] Failed to log failed text: {e}")


    def close(self):
        """关闭 Session 连接池"""
        if hasattr(self, 'session'):
            self.session.close()

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭连接"""
        self.close()
