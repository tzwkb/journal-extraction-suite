
import re
import time
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
import requests
from tqdm import tqdm

from config import UserConfig, Constants
from core.logger import HeartbeatMonitor, LoggerManager, ConsoleOutput, NetworkErrorHandler, UnifiedRetryPolicy
from core.logger import JSONLWriter

class ArticleTranslator:
    
    def __init__(
        self,
        api_key: str,
        api_url: str = None,
        model: str = None,
        source_lang: str = "English",
        target_lang: str = "Chinese",
        glossary: Optional[Dict[str, str]] = None,
        case_sensitive: bool = None,
        whole_word_only: bool = None,
        max_retries: int = None,
        retry_delay: int = None,
        max_workers: int = None,
        log_dir: str = None,
        api_semaphore = None
    ):
        self.api_key = api_key
        self.api_url = (api_url or UserConfig.TRANSLATION_API_BASE_URL).rstrip('/')
        self.model = model or UserConfig.TRANSLATION_API_MODEL
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.glossary = glossary or {}
        self.case_sensitive = case_sensitive if case_sensitive is not None else UserConfig.CASE_SENSITIVE
        self.whole_word_only = whole_word_only if whole_word_only is not None else UserConfig.WHOLE_WORD_ONLY
        self.chat_endpoint = f"{self.api_url}/chat/completions"
        self.max_retries = max_retries or UserConfig.TRANSLATION_MAX_RETRIES
        self.retry_delay = retry_delay or UserConfig.TRANSLATION_RETRY_DELAY
        self.max_workers = max_workers or UserConfig.TRANSLATION_MAX_WORKERS
        self.journal_outline = None
        self.log_dir = Path(log_dir) if log_dir else None
        self.api_semaphore = api_semaphore

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

        self.failure_stats = {
            'network_error': 0,
            'json_error': 0,
            'rate_limit': 0,
            'server_error': 0,
            'auth_error': 0,
            'client_error': 0,
            'timeout_error': 0,
            'truncation_error': 0,
            'other': 0
        }

        self.logger = LoggerManager().get_logger(
            'article_translator',
            log_to_file=True,
            log_to_console=False
        )
    
    def set_journal_outline(self, journal_outline: Optional[Dict[str, any]]):
        self.journal_outline = journal_outline
        if journal_outline and journal_outline.get('journal_name') != 'Unknown':
            ConsoleOutput.info(f"已加载期刊上下文: {journal_outline.get('journal_name', 'Unknown')}", 2)
    
    def _call_llm(
        self,
        prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        use_system_prompt: bool = True
    ) -> str:
        if temperature is None:
            temperature = UserConfig.TRANSLATION_TEMPERATURE
        if max_tokens is None:
            max_tokens = UserConfig.TRANSLATION_MAX_TOKENS
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        
        if use_system_prompt:
            messages.append({
                "role": "system",
                "content": UserConfig.TRANSLATION_SYSTEM_PROMPT
            })
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if self.api_semaphore:
                    with self.api_semaphore:
                        response = self.session.post(
                            self.chat_endpoint,
                            headers=headers,
                            json=payload,
                            timeout=UserConfig.TRANSLATION_TIMEOUT,
                            verify=True
                        )
                else:
                    response = self.session.post(
                        self.chat_endpoint,
                        headers=headers,
                        json=payload,
                        timeout=UserConfig.TRANSLATION_TIMEOUT,
                        verify=True
                    )

                response.raise_for_status()

                result = response.json()

                from core.logger import APIResponseValidator

                is_valid, response_data, error_msg = APIResponseValidator.validate_and_extract(
                    result,
                    max_tokens,
                    api_type="openai"
                )

                if not is_valid:
                    self.failure_stats['truncation_error'] += 1
                    self.logger.warning(f"⚠️ {error_msg}")
                    raise ValueError(error_msg)

                translated_content = response_data["content"]
                finish_reason = response_data["finish_reason"]
                usage = response_data["usage"]

                from core.logger import UnifiedLLMLogger

                request_log = {
                    "endpoint": self.chat_endpoint,
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "system_prompt": UserConfig.TRANSLATION_SYSTEM_PROMPT if use_system_prompt else None
                }

                response_log = {
                    "content": translated_content,
                    "content_length": len(translated_content),
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "full_response": result
                }

                context_log = {
                    "source_lang": self.source_lang,
                    "target_lang": self.target_lang,
                    "prompt_length": len(prompt)
                }

                if self.log_dir:
                    log_file = self.log_dir / "translation.jsonl"
                else:
                    log_file = Constants.LLM_LOG_TRANSLATION

                UnifiedLLMLogger.log_success(
                    log_file,
                    request_log,
                    response_log,
                    context_log,
                    metadata={
                        "stage": "translation",
                        "status": "success",
                        "source_lang": self.source_lang,
                        "target_lang": self.target_lang
                    }
                )

                self.logger.debug(f"✅ 已保存翻译日志到: {log_file}")

                return translated_content
                
            except requests.exceptions.RequestException as e:
                last_error = e

                from core.logger import NetworkErrorHandler

                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

                error_detail = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    response_text = e.response.text[:500] if e.response.text else ''
                    error_detail = f"{status_code} - {response_text}"

                    self.logger.error(f"API调用失败 (尝试 {attempt+1}/{self.max_retries}): "
                                     f"状态码={status_code}, 响应={response_text}")

                    if status_code == 429:
                        self.failure_stats['rate_limit'] += 1
                    elif status_code >= 500:
                        self.failure_stats['server_error'] += 1
                    elif status_code in [401, 403]:
                        self.failure_stats['auth_error'] += 1
                    elif status_code == 400:
                        self.failure_stats['client_error'] += 1
                    else:
                        self.failure_stats['other'] += 1
                else:
                    if 'timeout' in error_detail.lower():
                        self.failure_stats['timeout_error'] += 1
                        self.logger.error(f"API调用超时 (尝试 {attempt+1}/{self.max_retries}): {error_detail}")
                    else:
                        self.failure_stats['network_error'] += 1
                        self.logger.error(f"网络错误 (尝试 {attempt+1}/{self.max_retries}): {error_detail}")

                from core.logger import UnifiedLLMLogger

                if self.log_dir:
                    error_log_file = self.log_dir / "translation_errors.jsonl"
                else:
                    error_log_file = Constants.LLM_LOG_TRANSLATION_ERRORS

                request_log = {
                    "endpoint": self.chat_endpoint,
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "system_prompt": UserConfig.TRANSLATION_SYSTEM_PROMPT if use_system_prompt else None
                }

                error_log = {
                    "type": error_type,
                    "detail": error_detail[:200],
                    "attempt": attempt + 1,
                    "max_retries": self.max_retries,
                    "should_retry": should_retry
                }

                context_log = {
                    "source_lang": self.source_lang,
                    "target_lang": self.target_lang,
                    "prompt_length": len(prompt)
                }

                UnifiedLLMLogger.log_error(
                    error_log_file,
                    request_log,
                    error_log,
                    context_log,
                    metadata={
                        "stage": "translation",
                        "status": "retry_error"
                    }
                )
                self.logger.debug(f"已保存翻译错误日志到: {error_log_file.name if hasattr(error_log_file, 'name') else error_log_file}")

                
                if should_retry and attempt < self.max_retries - 1:
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt,
                        base_delay=self.retry_delay
                    )
                    ConsoleOutput.retry(error_type, wait_time, attempt + 1, self.max_retries, 2)
                    ConsoleOutput.info(f"详情: {error_detail[:100]}", 3)
                    time.sleep(wait_time)
                    continue
                else:
                    if not should_retry:
                        ConsoleOutput.error(f"{error_type}（不可重试）", 2)
                    break
        
        raise Exception(f"API调用失败: {str(last_error)}")
    
    def apply_glossary(self, text: str, show_log: bool = False) -> tuple[str, int]:
        if not self.glossary or not text:
            return text, 0

        modified_text = text
        replacement_count = 0
        replaced_terms = []

        url_pattern = r'https?://[^\s<>"]+(?:[^\s<>"])*'
        urls = re.findall(url_pattern, modified_text)
        urls = sorted(urls, key=len, reverse=True)
        url_placeholders = {}
        for i, url in enumerate(urls):
            placeholder = f"__URL_PLACEHOLDER_{i}__"
            url_placeholders[placeholder] = url
            modified_text = modified_text.replace(url, placeholder)

        sorted_terms = sorted(self.glossary.items(), key=lambda x: len(x[0]), reverse=True)

        for source_term, target_term in sorted_terms:
            if not source_term or not target_term:
                continue

            if self.whole_word_only:
                pattern = r'\b' + re.escape(source_term) + r'\b'
            else:
                pattern = re.escape(source_term)

            flags = 0 if self.case_sensitive else re.IGNORECASE
            matches = re.findall(pattern, modified_text, flags=flags)
            if not matches:
                continue

            count = len(matches)
            modified_text = re.sub(pattern, target_term, modified_text, flags=flags)
            replacement_count += count
            replaced_terms.append((source_term, target_term, count))

        if show_log and replaced_terms:
            ConsoleOutput.info(f"术语替换: {len(replaced_terms)} 个术语，共 {replacement_count} 处", 3)
            for source, target, count in replaced_terms[:3]:
                ConsoleOutput.info(f"• {source} → {target} ({count}次)", 3)
            if len(replaced_terms) > 3:
                ConsoleOutput.info(f"... 还有 {len(replaced_terms) - 3} 个术语", 3)

        for placeholder, url in url_placeholders.items():
            modified_text = modified_text.replace(placeholder, url)

        if '__URL_PLACEHOLDER_' in modified_text:
            self.logger.warning(f"⚠️  URL占位符未完全恢复！可能存在嵌套URL或替换冲突")

        return modified_text, replacement_count
    
    def clean_translation_output(self, text: str) -> str:
        if not text:
            return text
        
        cleaned = text.strip()
        
        prefixes_to_remove = [
            r'^译文[：:]\s*',
            r'^翻译[：:]\s*',
            r'^【译文】\s*',
            r'^【翻译】\s*',
            r'^\[译文\]\s*',
            r'^\[翻译\]\s*',
            r'^Translation[:\s]+',
            r'^Translated text[:\s]+',
            r'^以下是翻译[：:]\s*',
            r'^翻译如下[：:]\s*',
            r'^翻译结果[：:]\s*',
        ]
        
        for prefix_pattern in prefixes_to_remove:
            cleaned = re.sub(prefix_pattern, '', cleaned, flags=re.IGNORECASE)
        
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        if cleaned.startswith('「') and cleaned.endswith('」'):
            cleaned = cleaned[1:-1]
        if cleaned.startswith('『') and cleaned.endswith('』'):
            cleaned = cleaned[1:-1]
        
        if cleaned.startswith('《') and cleaned.endswith('》'):
            cleaned = cleaned[1:-1]
        
        return cleaned.strip()
    
    def _translate_long_text(self, text: str, field_name: str, article_idx: int, max_chars: int) -> str:
        paragraphs = re.split(r'(\n\n+)', text)
        chunks = []
        current = []
        current_len = 0

        for part in paragraphs:
            if current_len + len(part) > max_chars and current:
                chunks.append(''.join(current))
                current = [part]
                current_len = len(part)
            else:
                current.append(part)
                current_len += len(part)
        if current:
            chunks.append(''.join(current))

        article_info = f"文章{article_idx+1}" if article_idx is not None else "某文章"
        ConsoleOutput.info(
            f"{article_info}{field_name}分为{len(chunks)}块翻译（每块≤{max_chars}字符）", 3
        )

        translated_chunks = []
        for i, chunk in enumerate(chunks, 1):
            ConsoleOutput.info(f"  翻译第{i}/{len(chunks)}块（{len(chunk)}字符）...", 3)
            modified_text, _ = self.apply_glossary(chunk, show_log=False)
            prompt = UserConfig.TRANSLATION_CONTENT_PROMPT.format(
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                text=modified_text
            )
            max_retries = 3
            chunk_result = chunk
            for attempt in range(max_retries):
                try:
                    translation = self._call_llm(prompt)
                    final = self.clean_translation_output(translation)
                    if final.strip():
                        chunk_result = final
                        break
                except Exception as e:
                    self.logger.warning(f"分块翻译失败（尝试{attempt+1}/{max_retries}）: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            else:
                self.logger.error(f"分块翻译最终失败，返回原文块（{len(chunk)}字符）")
            translated_chunks.append(chunk_result)

        return '\n\n'.join(translated_chunks)

    def translate_text(self, text: str, field_name: str = "内容", article_idx: int = None) -> str:
        if not text or pd.isna(text) or text.strip() == '':
            return ''
        
        text_length = len(text)
        max_chars = getattr(UserConfig, 'TRANSLATION_CONTENT_MAX_CHARS', 8000)
        if field_name == "正文" and text_length > max_chars:
            article_info = f"文章{article_idx+1}" if article_idx is not None else "某文章"
            ConsoleOutput.warning(
                f"{article_info}{field_name}过长({text_length}字符)，分块翻译...", 3
            )
            return self._translate_long_text(text, field_name, article_idx, max_chars)

        modified_text, _ = self.apply_glossary(text, show_log=False)
        
        if field_name in ["标题", "副标题"]:
            prompt = UserConfig.TRANSLATION_TITLE_PROMPT.format(
                field_name=field_name,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                text=modified_text
            )
        else:
            prompt = UserConfig.TRANSLATION_CONTENT_PROMPT.format(
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                text=modified_text
            )

        from core.logger import ResponseValidator
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                current_prompt = prompt
                if attempt > 0:
                    warning = "\n\n【重要警告】前一次翻译与原文完全相同！这是不可接受的。请务必将所有内容翻译成中文，包括人名、地名等专有名词。译文不能与原文相同！"
                    current_prompt = prompt + warning
                
                translation = self._call_llm(current_prompt)
            
                is_valid, reason = ResponseValidator.validate_translation(text, translation)

                if not is_valid:
                    ConsoleOutput.warning(f"{field_name}翻译验证失败（尝试{attempt+1}/{max_retries}）: {reason}", 2)
                    self.logger.warning(f"翻译验证失败 - 字段: {field_name}, 尝试: {attempt+1}/{max_retries}, "
                                       f"原因: {reason}, 原文长度: {len(text)}")

                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        ConsoleOutput.error(f"{field_name}翻译验证始终失败，使用原文", 2)
                        self.logger.error(f"翻译验证最终失败 - 字段: {field_name}, 原因: {reason}, "
                                         f"原文前100字符: {text[:100]}")
                        return f"[验证失败-原文] {text}"
                
                final_translation = self.clean_translation_output(translation)
                
                if final_translation.strip() == text.strip():
                    ConsoleOutput.warning(f"{field_name}翻译结果与原文完全相同（尝试{attempt+1}/{max_retries}）", 2)
                    self.logger.warning(f"译文与原文相同 - 字段: {field_name}, 尝试: {attempt+1}/{max_retries}, "
                                       f"原文长度: {len(text)}")

                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        ConsoleOutput.error(f"{field_name}翻译始终与原文相同，标记为需要人工检查", 2)
                        self.logger.error(f"译文与原文相同最终失败 - 字段: {field_name}, "
                                         f"原文前100字符: {text[:100]}")
                        return f"[需人工检查-译文与原文相同] {text}"

                return final_translation

            except Exception as e:
                ConsoleOutput.warning(f"{field_name}翻译失败（尝试{attempt+1}/{max_retries}）: {str(e)}", 2)
                self.logger.error(f"翻译异常 - 字段: {field_name}, 尝试: {attempt+1}/{max_retries}, "
                                 f"错误: {str(e)}, 原文长度: {len(text)}")

                try:
                    from core.logger import UnifiedLLMLogger

                    if self.log_dir:
                        error_log_file = self.log_dir / "translation_errors.jsonl"
                    else:
                        error_log_file = Constants.LLM_LOG_TRANSLATION_ERRORS

                    request_log = {
                        "endpoint": self.chat_endpoint,
                        "model": self.model,
                        "prompt": current_prompt,
                        "prompt_length": len(current_prompt),
                        "temperature": UserConfig.TRANSLATION_TEMPERATURE,
                        "max_tokens": UserConfig.TRANSLATION_MAX_TOKENS
                    }

                    error_log = {
                        "type": type(e).__name__,
                        "detail": str(e)[:200],
                        "attempt": attempt + 1,
                        "max_retries": max_retries
                    }

                    context_log = {
                        "source_lang": self.source_lang,
                        "target_lang": self.target_lang,
                        "field_name": field_name,
                        "text_length": len(text)
                    }

                    UnifiedLLMLogger.log_error(
                        error_log_file,
                        request_log,
                        error_log,
                        context_log,
                        metadata={
                            "stage": "translation",
                            "status": "field_error"
                        }
                    )
                    self.logger.debug(f"已保存翻译异常日志到: {error_log_file.name if hasattr(error_log_file, 'name') else error_log_file}")
                except Exception as log_e:
                    self.logger.debug(f"记录翻译异常日志失败: {log_e}")

                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    self.logger.error(f"翻译最终失败 - 字段: {field_name}, 错误: {str(e)}, "
                                     f"原文前100字符: {text[:100]}")
                    return f"[翻译失败: {str(e)}]"

    def translate_article_batch(self, article: pd.Series, article_idx: int = 0) -> Dict[str, str]:
        import json

        title = article.get('title', '') or ''
        subtitle = article.get('subtitle', '') or ''
        authors = article.get('authors', '') or ''
        content = article.get('content', '') or ''

        max_chars = getattr(UserConfig, 'TRANSLATION_CONTENT_MAX_CHARS', 8000)
        if len(content) > max_chars:
            ConsoleOutput.info(
                f"文章{article_idx+1}正文过长({len(content)}字符)，跳过批量翻译，使用分块模式", 3
            )
            return None

        title_mod, _ = self.apply_glossary(title, show_log=False) if title else ('', {})
        subtitle_mod, _ = self.apply_glossary(subtitle, show_log=False) if subtitle else ('', {})
        authors_mod, _ = self.apply_glossary(authors, show_log=False) if authors else ('', {})
        content_mod, _ = self.apply_glossary(content, show_log=False) if content else ('', {})

        prompt = UserConfig.BATCH_TRANSLATION_PROMPT.format(
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            title=title_mod,
            subtitle=subtitle_mod,
            authors=authors_mod,
            content=content_mod
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response_text = self._call_llm(prompt, use_system_prompt=False)

                response_text = response_text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.startswith('```'):
                    response_text = response_text[3:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

                translation_dict = json.loads(response_text)

                required_fields = ['title_zh', 'subtitle_zh', 'authors_zh', 'content_zh']
                for field in required_fields:
                    if field not in translation_dict:
                        raise ValueError(f"API响应缺少必需字段: {field}")

                results = {
                    'title_zh': translation_dict['title_zh'],
                    'subtitle_zh': translation_dict['subtitle_zh'],
                    'authors_zh': translation_dict['authors_zh'],
                    'content_zh': translation_dict['content_zh']
                }

                ConsoleOutput.success(f"批量翻译成功（4字段合并为1次API调用）", 3)
                return results

            except json.JSONDecodeError as e:
                ConsoleOutput.warning(f"批量翻译JSON解析失败（尝试{attempt+1}/{max_retries}）: {str(e)}", 2)
                self.logger.warning(f"JSON解析失败 - 文章{article_idx}, 尝试{attempt+1}/{max_retries}: {str(e)}, "
                                  f"响应预览: {response_text[:200] if 'response_text' in locals() else 'N/A'}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    ConsoleOutput.warning(f"批量翻译失败，降级到单字段翻译模式", 2)
                    return None

            except Exception as e:
                ConsoleOutput.warning(f"批量翻译失败（尝试{attempt+1}/{max_retries}）: {str(e)}", 2)
                self.logger.error(f"批量翻译异常 - 文章{article_idx}, 尝试{attempt+1}/{max_retries}: {type(e).__name__} - {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    ConsoleOutput.warning(f"批量翻译失败，降级到单字段翻译模式", 2)
                    return None

        return None

    def translate_article(self, article: pd.Series, article_idx: int = 0) -> pd.Series:
        translated = article.copy()
        
        try:
            article_title = article.get('title', 'Untitled')[:50]
            
            title = article.get('title')
            subtitle = article.get('subtitle')
            authors = article.get('authors')
            content = article.get('content')
            
            translated['title'] = title or ''
            translated['subtitle'] = subtitle or ''
            translated['authors'] = authors or ''
            translated['content'] = content or ''

            batch_result = self.translate_article_batch(article, article_idx)

            if batch_result:
                translated['title_zh'] = batch_result['title_zh']
                translated['subtitle_zh'] = batch_result['subtitle_zh']
                translated['authors_zh'] = batch_result['authors_zh']
                translated['content_zh'] = batch_result['content_zh']
            else:
                ConsoleOutput.warning(f"使用单字段翻译模式（降级方案）", 3)

                if title and not pd.isna(title):
                    translated['title_zh'] = self.translate_text(title, "标题", article_idx)
                else:
                    translated['title_zh'] = ''

                if subtitle and not pd.isna(subtitle) and str(subtitle).strip():
                    translated['subtitle_zh'] = self.translate_text(subtitle, "副标题", article_idx)
                else:
                    translated['subtitle_zh'] = ''

                if authors and not pd.isna(authors) and str(authors).strip():
                    translated['authors_zh'] = self.translate_text(authors, "作者", article_idx)
                else:
                    translated['authors_zh'] = ''

                if content and not pd.isna(content):
                    translated['content_zh'] = self.translate_text(content, "正文", article_idx)
                else:
                    translated['content_zh'] = ''

            images = article.get('images')
            if isinstance(images, list) and images:
                self.logger.debug(f"文章{article_idx+1}: 开始翻译{len(images)}张图片的描述")
                translated_images = []
                for img_idx, img in enumerate(images, 1):
                    if isinstance(img, dict):
                        translated_img = img.copy()

                        description = img.get('description', '')
                        if not isinstance(description, str):
                            description = str(description) if description and not pd.isna(description) else ''
                        description = description.strip()

                        if description:
                            translated_img['description_zh'] = self.translate_text(description, "图片描述", article_idx)
                            self.logger.debug(f"  图片{img_idx}: description翻译完成 ({len(description)}→{len(translated_img['description_zh'])}字符)")
                        else:
                            translated_img['description_zh'] = ''
                            self.logger.debug(f"  图片{img_idx}: description为空，跳过翻译")

                        relevance = img.get('relevance', '')
                        if not isinstance(relevance, str):
                            relevance = str(relevance) if relevance and not pd.isna(relevance) else ''
                        relevance = relevance.strip()

                        if relevance:
                            translated_img['relevance_zh'] = self.translate_text(relevance, "图片相关性", article_idx)
                            self.logger.debug(f"  图片{img_idx}: relevance翻译完成 ({len(relevance)}→{len(translated_img['relevance_zh'])}字符)")
                        else:
                            translated_img['relevance_zh'] = ''

                        anchor_text = img.get('anchor_text', '')
                        if not isinstance(anchor_text, str):
                            anchor_text = str(anchor_text) if anchor_text and not pd.isna(anchor_text) else ''
                        anchor_text = anchor_text.strip()

                        if anchor_text:
                            translated_img['anchor_text_zh'] = self.translate_text(anchor_text, "图片锚点文本", article_idx)
                            self.logger.debug(f"  图片{img_idx}: anchor_text翻译完成 ({len(anchor_text)}→{len(translated_img['anchor_text_zh'])}字符)")
                        else:
                            translated_img['anchor_text_zh'] = ''

                        translated_images.append(translated_img)
                    else:
                        translated_images.append(img)

                translated['images'] = translated_images
            else:
                translated['images'] = images

        except Exception as e:
            ConsoleOutput.warning(f"第 {article_idx + 1} 篇文章翻译失败: {str(e)}", 1)
            self.logger.error(f"文章翻译失败 - 文章索引: {article_idx}, 标题: {title[:50] if title else 'N/A'}, "
                             f"错误: {str(e)}")
            translated['title_zh'] = ''
            translated['subtitle_zh'] = ''
            translated['authors_zh'] = ''
            translated['content_zh'] = ''

            if article.get('images') and isinstance(article.get('images'), list):
                failed_images = []
                for img in article.get('images', []):
                    if isinstance(img, dict):
                        failed_img = img.copy()
                        failed_img['description_zh'] = ''
                        failed_img['relevance_zh'] = ''
                        failed_img['anchor_text_zh'] = ''
                        failed_images.append(failed_img)
                    else:
                        failed_images.append(img)
                translated['images'] = failed_images

            return translated
        
        return translated
    
    def translate_dataframe(self, df: pd.DataFrame, cache_dir: str = None, progress_manager = None,
                            file_signature: str = None, source_file: str = None) -> pd.DataFrame:
        ConsoleOutput.section(f"🌐 开始翻译: {self.source_lang} → {self.target_lang}")
        ConsoleOutput.info(f"共 {len(df)} 篇文章", 2)
        ConsoleOutput.info(f"并发数: {self.max_workers} 线程", 2)

        cached_count = 0
        if cache_dir and progress_manager:
            cached_count = progress_manager.count_translations(cache_dir)
            if cached_count > 0:
                ConsoleOutput.success(f"检测到 {cached_count} 篇翻译缓存", 2)
                ConsoleOutput.info(f"将跳过已翻译文章", 2)

        heartbeat_monitor = HeartbeatMonitor(
            task_name="翻译",
            total=len(df),
            interval_seconds=30
        )
        heartbeat_monitor.start()

        if self.glossary:
            ConsoleOutput.subsection("📚 术语库分析:")
            ConsoleOutput.info(f"术语总数: {len(self.glossary)} 个", 2)
        else:
            ConsoleOutput.info(f"未使用术语库", 2)
        
        translated_articles = [None] * len(df)
        cached_count = 0
        new_count = 0
        
        articles_to_translate = []
        for idx, article in df.iterrows():
            if cache_dir and progress_manager:
                cached_trans = progress_manager.load_translation(cache_dir, idx, expected_signature=file_signature)
                if cached_trans:
                    trans_article = article.copy()
                    trans_article['title'] = article.get('title', '')
                    trans_article['subtitle'] = article.get('subtitle', '')
                    trans_article['authors'] = article.get('authors', '')
                    trans_article['content'] = article.get('content', '')

                    trans_article['title_zh'] = cached_trans.get('title_zh', '')
                    trans_article['subtitle_zh'] = cached_trans.get('subtitle_zh', '')
                    trans_article['authors_zh'] = cached_trans.get('authors_zh', '')
                    trans_article['content_zh'] = cached_trans.get('content_zh', '')

                    cached_images = cached_trans.get('images', [])
                    if not isinstance(cached_images, list):
                        cached_images = article.get('images', [])
                    trans_article['images'] = cached_images

                    translated_articles[idx] = trans_article
                    cached_count += 1
                else:
                    articles_to_translate.append((idx, article))
            else:
                articles_to_translate.append((idx, article))
        
        if cached_count > 0:
            ConsoleOutput.success(f"从缓存加载 {cached_count}/{len(df)} 篇", 2)
            ConsoleOutput.info(f"需翻译 {len(articles_to_translate)} 篇", 2)
        
        if articles_to_translate:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_idx = {
                    executor.submit(self.translate_article, article, idx): idx
                    for idx, article in articles_to_translate
                }
                
                with tqdm(total=len(articles_to_translate), desc="翻译进度") as pbar:
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            translated_article = future.result()
                            translated_articles[idx] = translated_article
                            new_count += 1
                            
                            heartbeat_monitor.update(cached_count + new_count)
                            
                            if cache_dir and progress_manager and 'content_zh' in translated_article:
                                progress_manager.save_translation(
                                    cache_dir, idx,
                                    translated_article['content_zh'],
                                    translated_article.to_dict(),
                                    file_signature=file_signature,
                                    source_file=source_file
                                )
                        except Exception as e:
                            ConsoleOutput.warning(f"第 {idx + 1} 篇翻译失败: {str(e)}", 1)
                            article_title = df.iloc[idx].get('title', 'N/A')[:50] if 'title' in df.columns else 'N/A'
                            self.logger.error(f"translate_articles异常 - 文章索引: {idx}, 标题: {article_title}, "
                                             f"错误: {str(e)}")
                            failed_article = df.iloc[idx].copy()
                            failed_article['title_zh'] = ''
                            failed_article['subtitle_zh'] = ''
                            failed_article['authors_zh'] = ''
                            failed_article['content_zh'] = ''
                            translated_articles[idx] = failed_article
                        finally:
                            pbar.update(1)
        
        heartbeat_monitor.stop()
        
        translated_df = pd.DataFrame(translated_articles)

        total_images = 0
        for _, article in translated_df.iterrows():
            images = article.get('images')
            if isinstance(images, list) and images:
                total_images += len([img for img in images if isinstance(img, dict)])

        if cached_count == len(df):
            ConsoleOutput.success(f"全部 {len(df)} 篇文章从缓存加载（共 {total_images} 张图片）", 1)
        elif cached_count > 0:
            ConsoleOutput.success(f"翻译完成（缓存: {cached_count} 篇, 新翻译: {new_count} 篇, 共 {total_images} 张图片）", 1)
        else:
            ConsoleOutput.success(f"翻译完成（共 {new_count} 篇文章, {total_images} 张图片）", 1)
        

        return translated_df
    
    def translate_cover_images(self, pdf_name: str) -> bool:
        from pathlib import Path
        import json
        import time

        cover_path = Path("output/json") / pdf_name / "outline" / "cover_images.json"

        if not cover_path.exists():
            self.logger.debug(f"封面图片文件不存在: {cover_path}")
            return False

        cover_images = None
        max_file_retries = 3
        for attempt in range(max_file_retries):
            try:
                with open(cover_path, 'r', encoding='utf-8') as f:
                    cover_images = json.load(f)
                break
            except (IOError, json.JSONDecodeError) as e:
                if attempt < max_file_retries - 1:
                    self.logger.warning(f"⚠️  读取封面图片失败(尝试{attempt+1}/{max_file_retries}): {str(e)[:50]}")
                    time.sleep(2)
                else:
                    self.logger.error(f"❌ 读取封面图片失败（已重试{max_file_retries}次）: {e}")
                    return False

        if not isinstance(cover_images, list) or len(cover_images) == 0:
            self.logger.debug(f"封面图片为空或格式错误: {cover_path}")
            return False

        translated_count = 0
        failed_count = 0
        total_items = 0

        for img_idx, img in enumerate(cover_images):
            if not isinstance(img, dict):
                continue

            if 'description' in img and img['description']:
                total_items += 1
                try:
                    description = img['description']
                    img['description_zh'] = self.translate_text(
                        description,
                        "封面图片描述",
                        img_idx
                    )
                    translated_count += 1
                except Exception as e:
                    failed_count += 1
                    img['description_zh'] = f"[翻译失败: {str(e)[:30]}]"
                    self.logger.warning(f"⚠️  封面图{img_idx}描述翻译失败: {str(e)[:50]}")

            if 'relevance' in img and img['relevance']:
                try:
                    relevance = img['relevance']
                    img['relevance_zh'] = self.translate_text(
                        relevance,
                        "封面图片相关性",
                        img_idx
                    )
                except Exception as e:
                    img['relevance_zh'] = f"[翻译失败: {str(e)[:30]}]"
                    self.logger.warning(f"⚠️  封面图{img_idx}相关性翻译失败: {str(e)[:50]}")

        max_save_retries = 3
        save_success = False
        for attempt in range(max_save_retries):
            try:
                temp_path = cover_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(cover_images, f, ensure_ascii=False, indent=2)

                temp_path.replace(cover_path)
                save_success = True
                break
            except IOError as e:
                if attempt < max_save_retries - 1:
                    self.logger.warning(f"⚠️  保存封面图片失败(尝试{attempt+1}/{max_save_retries}): {str(e)[:50]}")
                    time.sleep(2)
                else:
                    self.logger.error(f"❌ 保存封面图片失败（已重试{max_save_retries}次）: {e}")
                    return False

        if save_success and total_items > 0:
            self.logger.info(f"✅ 封面图片翻译完成: {translated_count}成功, {failed_count}失败 (共{total_items}项)")
            return True
        elif save_success:
            self.logger.debug(f"封面图片无需翻译（无有效内容）")
            return True
        else:
            return False

