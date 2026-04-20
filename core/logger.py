
import logging
import re
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

class LazyFileHandler(logging.FileHandler):
    
    def __init__(self, filename, mode='a', encoding='utf-8', delay=True):
        self.baseFilename = os.path.abspath(filename)
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        
        logging.Handler.__init__(self)
        self.stream = None
    
    def emit(self, record):
        if self.stream is None:
            try:
                self.stream = self._open()
            except PermissionError:
                import time
                timestamp = int(time.time() * 1000)
                base_name = Path(self.baseFilename)
                new_name = base_name.parent / f"{base_name.stem}_{timestamp}{base_name.suffix}"
                self.baseFilename = str(new_name)
                try:
                    self.stream = self._open()
                except Exception:
                    self.stream = None
                    print(f"[WARNING] 无法创建日志文件，日志将仅输出到控制台: {self.baseFilename}")
                    return

        if self.stream is not None:
            logging.FileHandler.emit(self, record)
    
    def _open(self):
        return open(self.baseFilename, self.mode, encoding=self.encoding)

class LoggerManager:
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.loggers = {}
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
    
    def get_logger(
        self,
        name: str,
        level: int = logging.INFO,
        log_to_file: bool = True,
        log_to_console: bool = True
    ) -> logging.Logger:
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        
        console_formatter = logging.Formatter(
            '%(message)s'
        )
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        if log_to_file:
            timestamp = datetime.now().strftime('%Y%m%d')
            
            component_names = [
                'pdf_extractor', 'translator', 'article_translator', 'html_generator', 'excel_generator',
                'batch_processor', 'docx_extractor', 'pdf_generator', 'docx_generator',
                'ai_html_generator', 'html_postprocessor', 'json_utils', 'pdf_preprocessor',
                'image_extractor', 'image_matcher', 'image_cleaner',
                'sequential_processor',
                'vision_image_processor'
            ]
            
            if name in component_names:
                component_dir = self.log_dir / "components"
                component_dir.mkdir(exist_ok=True)
                log_file = component_dir / f"{name}_{timestamp}.log"
            else:
                log_file = self.log_dir / f"{name}_{timestamp}.log"
            
            file_handler = LazyFileHandler(str(log_file), mode='a', encoding='utf-8', delay=True)
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        self.loggers[name] = logger
        return logger
    
    def set_level(self, name: str, level: int):
        if name in self.loggers:
            self.loggers[name].setLevel(level)
            for handler in self.loggers[name].handlers:
                handler.setLevel(level)

def get_logger(name: str = "main", level: int = logging.INFO) -> logging.Logger:
    manager = LoggerManager()
    return manager.get_logger(name, level=level)

import threading
import time
from typing import Callable

class HeartbeatMonitor:
    
    def __init__(
        self,
        task_name: str,
        total: int,
        interval_seconds: int = 30,
        custom_message: Optional[Callable[[int, int], str]] = None
    ):
        self.task_name = task_name
        self.total = total
        self.interval_seconds = interval_seconds
        self.custom_message = custom_message
        
        self.current = 0
        self.running = False
        self.thread = None
        self.start_time = None
    
    def start(self):
        if self.running:
            return
        
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"Heartbeat-{self.task_name}"
        )
        self.thread.start()
    
    def _heartbeat_loop(self):
        while self.running:
            time.sleep(self.interval_seconds)
            
            if not self.running:
                break
            
            current = self.current
            if current > 0:
                if self.custom_message:
                    message = self.custom_message(current, self.total)
                else:
                    message = self._default_message(current)
                
                print(f"\n[{self.task_name}心跳] {message}\n")
    
    def _default_message(self, current: int) -> str:
        progress_pct = (current / self.total) * 100 if self.total > 0 else 0
        
        elapsed = time.time() - self.start_time
        speed = current / elapsed if elapsed > 0 else 0
        
        if speed > 0 and self.total > current:
            remaining = self.total - current
            eta_seconds = remaining / speed
            eta_minutes = int(eta_seconds / 60)
            eta_str = f", 预计还需 {eta_minutes} 分钟" if eta_minutes > 0 else ", 即将完成"
        else:
            eta_str = ""
        
        return f"已完成 {current}/{self.total} ({progress_pct:.1f}%){eta_str}"
    
    def update(self, current: int):
        self.current = current
    
    def stop(self):
        if not self.running:
            return
        
        self.running = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

class ConsoleOutput:

    INDENT_L1 = "  "
    INDENT_L2 = "    "
    INDENT_L3 = "      "

    @staticmethod
    def section(title: str):
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}")

    @staticmethod
    def subsection(title: str):
        print(f"\n{ConsoleOutput.INDENT_L1}{'-'*60}")
        print(f"{ConsoleOutput.INDENT_L1}{title}")
        print(f"{ConsoleOutput.INDENT_L1}{'-'*60}")

    @staticmethod
    def file_start(file_name: str, current: int = None, total: int = None):
        progress = f" [{current}/{total}]" if current and total else ""
        print(f"\n📄 处理文件{progress}: {file_name}")

    @staticmethod
    def batch_start(batch_idx: int, total: int, page_range: str):
        percent = (batch_idx / total * 100) if total > 0 else 0
        print(f"\n{ConsoleOutput.INDENT_L1}📦 批次 {batch_idx}/{total} ({percent:.1f}%) | 页码 {page_range}")

    @staticmethod
    def step(message: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}{message}")

    @staticmethod
    def success(message: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}✅ {message}")

    @staticmethod
    def error(message: str, level: int = 1, detail: str = None):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}❌ {message}")
        if detail:
            detail_short = detail[:100] if len(detail) > 100 else detail
            print(f"{indent}   {detail_short}")

    @staticmethod
    def warning(message: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}⚠️  {message}")

    @staticmethod
    def info(message: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}ℹ️  {message}")

    @staticmethod
    def cache(message: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}💾 {message}")

    @staticmethod
    def retry(attempt: int, max_retries: int, wait_time: float, error_type: str, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}🔄 {error_type}，{wait_time:.0f}秒后重试 (第{attempt}/{max_retries}次)")

    @staticmethod
    def timing(message: str, seconds: float, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        if seconds < 60:
            time_str = f"{seconds:.1f}秒"
        elif seconds < 3600:
            time_str = f"{seconds/60:.1f}分钟"
        else:
            time_str = f"{seconds/3600:.1f}小时"
        print(f"{indent}⏱️  {message}: {time_str}")

    @staticmethod
    def progress_summary(current: int, total: int, success: int = None, failed: int = None, level: int = 1):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        percent = (current / total * 100) if total > 0 else 0
        status = f"进度 {current}/{total} ({percent:.1f}%)"
        if success is not None:
            status += f" | 成功 {success}"
        if failed is not None:
            status += f" | 失败 {failed}"
        print(f"{indent}📊 {status}")

    @staticmethod
    def vision_start(image_count: int, article_count: int, page_range: str, level: int = 2):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}👁️  Vision处理: {image_count}张图片 → {article_count}篇文章 (页码{page_range})")

    @staticmethod
    def vision_result(annotated: int, total: int, matched: int, level: int = 2):
        indent = [ConsoleOutput.INDENT_L1, ConsoleOutput.INDENT_L2, ConsoleOutput.INDENT_L3][min(level-1, 2)]
        print(f"{indent}✅ 标注 {annotated}/{total} 张, 匹配 {matched} 张")

import json
from typing import Dict, Any

class JSONLWriter:

    _locks = {}
    _locks_lock = threading.Lock()

    @classmethod
    def _get_lock(cls, file_path: Path) -> threading.Lock:
        with cls._locks_lock:
            if file_path not in cls._locks:
                cls._locks[file_path] = threading.Lock()
            return cls._locks[file_path]

    @staticmethod
    def append(file_path: str, data: Dict[str, Any], metadata: Dict[str, Any] = None):
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        entry = metadata.copy() if metadata else {}
        entry['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry['data'] = data
        json_line = json.dumps(entry, ensure_ascii=False)
        lock = JSONLWriter._get_lock(file_path)
        with lock:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json_line + '\n')

def append_to_jsonl(file_path: str, data: Dict[str, Any], metadata: Dict[str, Any] = None):
    JSONLWriter.append(file_path, data, metadata)

class NetworkErrorHandler:

    @staticmethod
    def is_retryable_error(exception: Exception) -> Tuple[bool, str]:
        import requests

        error_str = str(exception).lower()

        if isinstance(exception, (requests.exceptions.Timeout,
                                 requests.exceptions.ConnectTimeout,
                                 requests.exceptions.ReadTimeout)):
            return True, f"超时错误: {type(exception).__name__}"

        if 'timeout' in error_str or 'timed out' in error_str:
            return True, "超时错误"

        if isinstance(exception, (requests.exceptions.ConnectionError,
                                 requests.exceptions.HTTPError)):
            return True, f"连接错误: {type(exception).__name__}"

        if any(keyword in error_str for keyword in ['connection', 'connectionpool']):
            return True, "连接错误"

        if 'ssl' in error_str or 'tls' in error_str:
            return True, "SSL/TLS错误"

        if 'rate limit' in error_str or '429' in error_str:
            return True, "API限流"

        if any(code in error_str for code in ['500', '502', '503', '504']):
            return True, "服务器错误"

        if 'eof' in error_str:
            return True, "EOF错误"

        if any(keyword in error_str for keyword in ['insufficient_user_quota', 'quota', '余额不足']):
            return False, "余额不足/配额限制（不可重试）"

        if '401' in error_str or '403' in error_str:
            return True, "认证/权限错误"

        if '400' in error_str or '404' in error_str:
            return True, "客户端错误"

        if isinstance(exception, (TypeError, AttributeError, ValueError)):
            return False, f"代码错误（不可重试）: {type(exception).__name__}"

        return True, f"未知错误: {type(exception).__name__}"

class UnifiedRetryPolicy:

    @staticmethod
    def calculate_backoff_time(
        attempt: int,
        base_delay: int = 2,
        max_exponent: int = 10,
        max_wait_time: int = 60
    ) -> float:
        capped_attempt = min(attempt, max_exponent)
        wait_time = base_delay * (2 ** capped_attempt)

        return min(wait_time, max_wait_time)

    @staticmethod
    def calculate_backoff_time_by_error_type(
        error_type: str,
        attempt: int,
        base_delay: int = 2
    ) -> float:
        error_lower = error_type.lower()

        if "connectionerror" in error_lower or "connectionreset" in error_lower or "connection reset" in error_lower:
            wait_time = base_delay * (2 ** attempt)
            return min(wait_time, 30)

        elif "timeout" in error_lower:
            wait_time = base_delay * (2 ** attempt)
            return min(wait_time, 60)

        else:
            wait_time = base_delay * (2 ** attempt)
            return min(wait_time, 60)

    @staticmethod
    def should_continue_retry(
        attempt: int,
        max_retries: int,
        error_type: str = None
    ) -> Tuple[bool, str]:
        if attempt >= max_retries:
            return False, f"已达到最大重试次数({max_retries})"

        if error_type and "不可重试" in error_type:
            return False, f"错误类型不可重试: {error_type}"

        return True, ""

    @staticmethod
    def get_retry_message(
        attempt: int,
        max_retries: int,
        wait_time: float,
        error_type: str
    ) -> str:
        return f"调用失败 ({error_type})，{wait_time:.0f}秒后重试（第{attempt + 1}/{max_retries}次）"

class UnifiedLLMLogger:

    @staticmethod
    def log_success(
        log_file,
        request_data: dict,
        response_data: dict,
        context: dict,
        metadata: dict
    ):
        log_data = {
            "request": request_data,
            "response": response_data,
            "context": context
        }

        JSONLWriter.append(log_file, log_data, metadata=metadata)

    @staticmethod
    def log_error(
        log_file,
        request_data: dict,
        error_data: dict,
        context: dict,
        metadata: dict
    ):
        log_data = {
            "request": request_data,
            "error": error_data,
            "context": context
        }

        JSONLWriter.append(log_file, log_data, metadata=metadata)

class ResponseValidator:

    ERROR_PATTERNS = [
        re.compile(r'^\s*\{\s*["\']error["\']', re.IGNORECASE),
        re.compile(r'"error"\s*:\s*\{', re.IGNORECASE),
        re.compile(r'"error"\s*:\s*"[^"]{10,}', re.IGNORECASE),
        re.compile(r'"code"\s*:\s*"(insufficient_quota|insufficient_user_quota|auth_error|invalid_api_key)"', re.IGNORECASE),
        re.compile(r'400\s+bad\s+request', re.IGNORECASE),
        re.compile(r'401\s+unauthorized', re.IGNORECASE),
        re.compile(r'403\s+forbidden', re.IGNORECASE),
        re.compile(r'404\s+not\s+found', re.IGNORECASE),
        re.compile(r'429\s+too\s+many\s+requests', re.IGNORECASE),
        re.compile(r'500\s+internal\s+server\s+error', re.IGNORECASE),
        re.compile(r'502\s+bad\s+gateway', re.IGNORECASE),
        re.compile(r'503\s+service\s+unavailable', re.IGNORECASE),
        re.compile(r'504\s+gateway\s+timeout', re.IGNORECASE),
    ]

    EMPTY_PATTERN = re.compile(r'^\s*$')
    INCOMPLETE_PATTERN = re.compile(r'\[truncated\]', re.IGNORECASE)

    @classmethod
    def is_error_response(cls, content: str) -> Tuple[bool, str]:
        if not content or not isinstance(content, str):
            return True, "内容为空或类型错误"
        for pattern in cls.ERROR_PATTERNS:
            if pattern.search(content):
                return True, f"包含错误关键词: {pattern.pattern}"
        return False, ""

    @classmethod
    def is_empty_response(cls, content: str) -> bool:
        if not isinstance(content, str) or not content:
            return True
        return bool(cls.EMPTY_PATTERN.match(content.strip()))

    @classmethod
    def is_incomplete_response(cls, content: str) -> bool:
        if not isinstance(content, str) or not content:
            return True
        return bool(cls.INCOMPLETE_PATTERN.search(content))

    @classmethod
    def validate_translation(cls, original: str, translated: str, min_length_ratio: float = 0.3) -> Tuple[bool, str]:
        if not isinstance(translated, str):
            return False, f"译文类型错误: 期望str，得到{type(translated).__name__}"

        if not isinstance(original, str):
            return False, f"原文类型错误: 期望str，得到{type(original).__name__}"

        is_error, error_desc = cls.is_error_response(translated)
        if is_error:
            return False, f"翻译结果包含错误: {error_desc}"

        if cls.is_empty_response(translated):
            return False, "翻译结果为空"

        if cls.is_incomplete_response(translated):
            return False, "翻译结果不完整"

        if translated.strip() == original.strip():
            return False, "翻译结果与原文完全相同"

        if original.startswith(translated.strip()):
            return False, "翻译结果只是原文的前缀"

        return True, ""

    @classmethod
    def validate_html(cls, html: str, min_length: int = 50) -> Tuple[bool, str]:
        if not isinstance(html, str):
            return False, f"HTML类型错误: 期望str，得到{type(html).__name__}"

        is_error, error_desc = cls.is_error_response(html)
        if is_error:
            return False, f"HTML包含错误: {error_desc}"

        if cls.is_empty_response(html):
            return False, "HTML为空"

        if cls.is_incomplete_response(html):
            return False, "HTML不完整"

        html_lower = html.lower()
        if '<' not in html or '>' not in html:
            return False, "不包含HTML标签"

        has_content_tags = any(tag in html_lower for tag in ['<p', '<div', '<h1', '<h2', '<h3', '<span'])
        if not has_content_tags:
            return False, "缺少内容标签"

        return True, ""

    @classmethod
    def validate_json_array(cls, json_str: str) -> Tuple[bool, str]:
        import json

        if not isinstance(json_str, str):
            return False, f"JSON类型错误: 期望str，得到{type(json_str).__name__}"

        is_error, error_desc = cls.is_error_response(json_str)
        if is_error:
            return False, f"JSON包含错误: {error_desc}"

        if cls.is_empty_response(json_str):
            return False, "JSON为空"

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, f"JSON解析失败: {e}"

        if not isinstance(data, list):
            return False, "JSON不是数组格式"

        if len(data) == 0:
            return False, "JSON数组为空"

        return True, ""

    @classmethod
    def validate_journal_outline(cls, outline_data: dict) -> Tuple[bool, str]:
        if not outline_data or not isinstance(outline_data, dict):
            return False, "大纲数据为空或类型错误"

        required_fields = ['journal_name', 'issue_number', 'language', 'journal_type', 'content_summary']
        missing_fields = [field for field in required_fields if field not in outline_data]
        if missing_fields:
            return False, f"缺少必需字段: {', '.join(missing_fields)}"

        journal_name = outline_data.get('journal_name', '')
        if not journal_name or not isinstance(journal_name, str):
            return False, "期刊名称为空或无效"

        if not journal_name.strip():
            return False, "期刊名称只包含空白字符"

        content_summary = outline_data.get('content_summary', '')
        error_summaries = [
            'Outline extraction failed',
            'No context summary available',
        ]

        if any(error_msg in content_summary for error_msg in error_summaries):
            return False, f"内容摘要包含错误标记: '{content_summary}'"

        language = outline_data.get('language', '')
        valid_languages = ['English', 'Russian', 'Chinese']
        if language not in valid_languages:
            return False, f"语言标识无效: '{language}' (应为: {', '.join(valid_languages)})"

        journal_type = outline_data.get('journal_type', '')
        valid_types = ['multi-article-magazine', 'single-research-paper', 'mixed', 'unknown', 'long-document-with-chapters']
        if journal_type not in valid_types:
            return False, f"期刊类型无效: '{journal_type}'"

        if journal_type == 'unknown':
            return False, "期刊类型未识别（unknown）"

        if 'articles' in outline_data:
            articles = outline_data.get('articles')
            if not isinstance(articles, list):
                return False, f"文章列表类型错误: {type(articles)}"

        return True, ""

    @classmethod
    def should_retry(cls, content: str, content_type: str = "general") -> Tuple[bool, str]:
        is_error, error_desc = cls.is_error_response(content)
        if is_error:
            return True, error_desc

        if cls.is_empty_response(content):
            return True, "内容为空"

        if cls.is_incomplete_response(content):
            return True, "内容不完整"

        if content_type == "html":
            is_valid, reason = cls.validate_html(content)
            if not is_valid:
                return True, reason

        elif content_type == "json":
            is_valid, reason = cls.validate_json_array(content)
            if not is_valid:
                return True, reason

        return False, ""

class APIResponseValidator:

    @staticmethod
    def validate_and_extract(
        result: dict,
        max_tokens: int,
        api_type: str = "auto"
    ) -> tuple[bool, dict, str]:
        if api_type == "auto":
            if 'choices' in result:
                api_type = "openai"
            elif 'candidates' in result:
                api_type = "gemini"
            else:
                return False, {}, "无法识别API响应格式（缺少choices或candidates字段）"

        if api_type == "openai":
            return APIResponseValidator._extract_openai(result, max_tokens)
        elif api_type == "gemini":
            return APIResponseValidator._extract_gemini(result, max_tokens)
        else:
            return False, {}, f"不支持的API类型: {api_type}"

    @staticmethod
    def _extract_openai(result: dict, max_tokens: int) -> tuple[bool, dict, str]:
        try:
            choices = result.get('choices', [])
            if not choices:
                return False, {}, "响应缺少choices字段"

            choice = choices[0]

            finish_reason = choice.get('finish_reason', '')

            is_truncated = finish_reason == 'length'
            if is_truncated:
                return False, {}, f"输出被截断: 内容过长，超出token限制({max_tokens})"

            message = choice.get('message', {})
            content = message.get('content')

            if content is None:
                return False, {}, "响应中缺少content字段"

            content = content.strip()

            usage = result.get('usage', {})

            data = {
                "content": content,
                "finish_reason": finish_reason,
                "usage": usage,
                "is_truncated": is_truncated
            }

            return True, data, ""

        except (KeyError, IndexError, TypeError) as e:
            return False, {}, f"OpenAI响应格式错误: {type(e).__name__} - {str(e)}"

    @staticmethod
    def _extract_gemini(result: dict, max_tokens: int) -> tuple[bool, dict, str]:
        try:
            candidates = result.get('candidates', [])
            if not candidates:
                return False, {}, "响应缺少candidates字段"

            candidate = candidates[0]

            finish_reason = candidate.get('finishReason', '')

            is_truncated = finish_reason in ('MAX_TOKENS', 'length')
            if is_truncated:
                return False, {}, f"输出被截断: 内容过长，超出token限制({max_tokens})"

            content_obj = candidate.get('content', {})
            parts = content_obj.get('parts', [])

            if not parts:
                return False, {}, "响应中缺少content.parts字段"

            content = parts[0].get('text')

            if content is None:
                return False, {}, "响应中缺少text字段"

            content = content.strip()

            usage = result.get('usageMetadata', {})

            data = {
                "content": content,
                "finish_reason": finish_reason,
                "usage": usage,
                "is_truncated": is_truncated
            }

            return True, data, ""

        except (KeyError, IndexError, TypeError) as e:
            return False, {}, f"Gemini响应格式错误: {type(e).__name__} - {str(e)}"

    @staticmethod
    def check_error_response(result: dict) -> tuple[bool, str]:
        if 'error' in result:
            error = result['error']
            if isinstance(error, dict):
                error_msg = error.get('message', str(error))
            else:
                error_msg = str(error)
            return True, f"API返回错误: {error_msg}"

        return False, ""
