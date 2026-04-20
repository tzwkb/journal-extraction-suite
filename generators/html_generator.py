
import os
import re
import time
import json
import requests
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import pandas as pd

from config import Constants, UserConfig, HTMLGenerationPrompts
from core.logger import get_logger, HeartbeatMonitor, ConsoleOutput, NetworkErrorHandler, UnifiedRetryPolicy
from core.logger import JSONLWriter

from processors.image_processor import (
    RuleBasedCoverSelector,
    RuleBasedCaptionGenerator,
    RuleBasedImageMatcher
)

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

logger = get_logger("ai_html_generator")

class HTMLTemplateManager:

    def __init__(self, template_dir: str = None):
        if template_dir is None:
            template_dir = Path(__file__).parent / "html_template"
        self.template_dir = Path(template_dir)
        self._template_cache: dict = {}

    def get_template(self, template_name: str = "default") -> str:
        if template_name in self._template_cache:
            return self._template_cache[template_name]
        template_file = self.template_dir / f"{template_name}.html"
        if not template_file.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_file}")
        with open(template_file, 'r', encoding='utf-8') as f:
            content = f.read()
        self._template_cache[template_name] = content
        return content

class AIHTMLGenerator:
    
    def __init__(
        self,
        api_key: str = None,
        api_base_url: str = None,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        timeout: int = None,
        max_concurrent: int = None,
        log_dir: str = None,
        api_semaphore = None,
        template_name: str = None
    ):
        self.api_key = api_key or UserConfig.HTML_API_KEY
        self.api_base_url = api_base_url or UserConfig.HTML_API_BASE_URL
        self.model = model or UserConfig.HTML_API_MODEL
        self.temperature = temperature if temperature is not None else UserConfig.HTML_TEMPERATURE
        self.max_tokens = max_tokens or UserConfig.HTML_MAX_TOKENS
        self.timeout = timeout or UserConfig.HTML_TIMEOUT
        self.max_concurrent = max_concurrent or UserConfig.HTML_CONCURRENT_REQUESTS
        self.log_dir = Path(log_dir) if log_dir else None
        self.api_semaphore = api_semaphore
        self.template_name = template_name or "default"

        self.api_url = f"{self.api_base_url.rstrip('/')}/chat/completions"

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

        logger.info(f"初始化 AI HTML 生成器: {self.model}")
        logger.info(f"使用HTML模板: {self.template_name}")

    @staticmethod
    def _image_to_base64(img_path: str) -> str:
        import base64
        from pathlib import Path
        import os

        try:
            img_file = Path(img_path)

            if not img_file.is_absolute():
                if not img_file.exists():
                    script_dir = Path(__file__).parent
                    img_file_alt = script_dir / img_path
                    if img_file_alt.exists():
                        img_file = img_file_alt
                    else:
                        if str(img_path).startswith('output'):
                            root_dir = script_dir
                            img_file_root = root_dir / img_path
                            if img_file_root.exists():
                                img_file = img_file_root

            if not img_file.exists():
                logger.error(f"❌ 图片文件不存在: {img_path}")
                logger.error(f"   当前工作目录: {os.getcwd()}")
                logger.error(f"   尝试的绝对路径: {img_file.absolute()}")

                placeholder_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                logger.warning(f"   ⚠️  使用透明占位符代替（PDF中会显示为空白）")
                return f"data:image/png;base64,{placeholder_base64}"

            ext = img_file.suffix.lower()
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.svg': 'image/svg+xml',
                '.bmp': 'image/bmp',
                '.tiff': 'image/tiff',
                '.tif': 'image/tiff'
            }
            mime_type = mime_types.get(ext, 'image/png')

            with open(img_file, 'rb') as f:
                img_data = f.read()

            file_size_mb = len(img_data) / (1024 * 1024)
            if file_size_mb > 5:
                logger.warning(f"⚠️  图片文件较大 ({file_size_mb:.1f}MB): {img_path}")
                logger.warning(f"   这可能导致HTML文件过大，建议压缩图片")

            base64_data = base64.b64encode(img_data).decode('utf-8')
            data_uri = f"data:{mime_type};base64,{base64_data}"

            logger.debug(f"✅ Base64编码成功: {img_path} ({file_size_mb:.2f}MB)")
            return data_uri

        except Exception as e:
            logger.error(f"❌ 图片Base64编码失败 ({img_path}): {e}")
            logger.exception("详细错误:")

            placeholder_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            return f"data:image/png;base64,{placeholder_base64}"

    def _call_api(self, prompt: str, max_retries: int = None, retry_delay: int = None) -> str:
        if max_retries is None:
            max_retries = UserConfig.HTML_API_MAX_RETRIES
        if retry_delay is None:
            retry_delay = UserConfig.HTML_RETRY_DELAY
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "system",
                "content": HTMLGenerationPrompts.SYSTEM_PROMPT
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
            "max_tokens": self.max_tokens
        }
        
        for attempt in range(max_retries):
            try:
                if self.api_semaphore:
                    acquired = self.api_semaphore.acquire(timeout=300)
                    if not acquired:
                        raise TimeoutError(f"等待API信号量超时（>300秒），可能存在资源死锁")

                    try:
                        response = self.session.post(
                            self.api_url,
                            json=payload,
                            headers=headers,
                            timeout=self.timeout
                        )
                    finally:
                        self.api_semaphore.release()
                else:
                    response = self.session.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                        timeout=self.timeout
                    )
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                    except json.JSONDecodeError as e:
                        self.failure_stats['json_error'] += 1
                        error_preview = (response.text or '').strip()[:200]
                        logger.error(
                            f"JSON解析失败(HTTP 200): {e}. 响应预览: {error_preview or '<empty>'}"
                        )
                        if attempt < max_retries - 1:
                            wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                                error_type="JSONDecodeError",
                                attempt=attempt,
                                base_delay=retry_delay
                            )
                            logger.info(
                                f"⏳ JSON解析错误，{wait_time:.0f}秒后重试（第{attempt + 1}/{max_retries}次）"
                            )
                            time.sleep(wait_time)
                            continue
                        raise ValueError(f"API响应无法解析为JSON: {e}")

                    from core.logger import APIResponseValidator

                    is_valid, response_data, error_msg = APIResponseValidator.validate_and_extract(
                        result,
                        self.max_tokens,
                        api_type="openai"
                    )

                    if not is_valid:
                        self.failure_stats['truncation_error'] += 1
                        logger.warning(f"⚠️ {error_msg}")
                        raise ValueError(error_msg)

                    html_content = response_data["content"]
                    finish_reason = response_data["finish_reason"]
                    usage = response_data["usage"]

                    if html_content.startswith('```html'):
                        html_content = html_content[7:]
                    elif html_content.startswith('```'):
                        html_content = html_content[3:]

                    if html_content.endswith('```'):
                        html_content = html_content[:-3]

                    from core.logger import ResponseValidator

                    is_valid, reason = ResponseValidator.validate_html(html_content)
                    if not is_valid:
                        error_msg = f"HTML验证失败: {reason}"
                        logger.warning(f"⚠️ {error_msg}")

                        if attempt < max_retries - 1:
                            wait_time = 5 * (attempt + 1)
                            logger.warning(f"   等待{wait_time}秒后重试...")
                            time.sleep(wait_time)
                            continue
                        else:
                            raise ValueError(error_msg)

                    try:
                        from core.logger import UnifiedLLMLogger

                        request_log = {
                            "endpoint": self.api_url,
                            "model": self.model,
                            "messages": messages,
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "system_prompt": HTMLGenerationPrompts.SYSTEM_PROMPT
                        }

                        response_log = {
                            "content": html_content,
                            "content_length": len(html_content),
                            "finish_reason": finish_reason,
                            "usage": usage,
                            "full_response": result
                        }

                        context_log = {
                            "prompt_length": len(prompt)
                        }

                        if self.log_dir:
                            log_file = self.log_dir / "html.jsonl"
                        else:
                            log_file = Constants.LLM_LOG_HTML

                        UnifiedLLMLogger.log_success(
                            log_file,
                            request_log,
                            response_log,
                            context_log,
                            metadata={
                                "stage": "html_generation",
                                "status": "success"
                            }
                        )

                        logger.debug(f"✅ 已保存HTML成功日志到: {log_file.name if hasattr(log_file, 'name') else log_file}")
                    except Exception as log_error:
                        logger.warning(f"⚠️ 保存HTML成功日志失败: {log_error}")

                    return html_content.strip()
                else:
                    from core.logger import NetworkErrorHandler
                    
                    status_code = response.status_code
                    error_text = response.text[:200] if response.text else ""
                    
                    temp_error = requests.exceptions.HTTPError()
                    temp_error.response = response
                    
                    should_retry, error_type = NetworkErrorHandler.is_retryable_error(temp_error)
                    error_msg = f"{error_type}: {status_code} - {error_text}"
                    
                    if status_code == 429:
                        self.failure_stats['rate_limit'] += 1
                    elif status_code >= 500:
                        self.failure_stats['server_error'] += 1
                    elif status_code in [401, 403]:
                        self.failure_stats['auth_error'] += 1
                    elif status_code in [400, 404]:
                        self.failure_stats['client_error'] += 1
                    else:
                        self.failure_stats['other'] += 1
                    
                    logger.error(error_msg)

                    if should_retry and attempt < max_retries - 1:
                        wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                            error_type=error_type,
                            attempt=attempt,
                            base_delay=retry_delay
                        )
                        logger.info(f"⏳ {error_type}，{wait_time:.0f}秒后重试（第{attempt + 1}/{max_retries}次）")
                        time.sleep(wait_time)
                    else:
                        raise Exception(error_msg)
                        
            except Exception as e:
                from core.logger import NetworkErrorHandler
                
                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)
                error_detail = str(e)[:200]
                
                if 'timeout' in error_detail.lower():
                    self.failure_stats['timeout_error'] += 1
                elif isinstance(e, requests.exceptions.RequestException):
                    self.failure_stats['network_error'] += 1
                else:
                    self.failure_stats['other'] += 1
                
                if self.log_dir:
                    try:
                        from core.logger import UnifiedLLMLogger

                        error_log_file = self.log_dir / "html_errors.jsonl"

                        request_log = {
                            "endpoint": self.api_url,
                            "model": self.model,
                            "messages": messages,
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "system_prompt": HTMLGenerationPrompts.SYSTEM_PROMPT
                        }

                        error_log = {
                            "type": error_type,
                            "detail": error_detail,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "should_retry": should_retry
                        }

                        context_log = {
                            "prompt_length": len(prompt)
                        }

                        UnifiedLLMLogger.log_error(
                            error_log_file,
                            request_log,
                            error_log,
                            context_log,
                            metadata={
                                "stage": "html_generation",
                                "status": "retry_error"
                            }
                        )
                        logger.debug(f"已保存HTML错误日志到: {error_log_file.name}")
                    except Exception as log_e:
                        logger.debug(f"记录HTML错误日志失败: {log_e}")
                
                if should_retry and attempt < max_retries - 1:
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt,
                        base_delay=retry_delay
                    )
                    logger.warning(f"⏳ {error_type}，{wait_time:.0f}秒后重试（第{attempt + 1}/{max_retries}次）")
                    logger.warning(f"   详情: {error_detail}")
                    time.sleep(wait_time)
                else:
                    if not should_retry:
                        logger.error(f"❌ {error_type}（不可重试）")
                    else:
                        logger.error(f"❌ 达到最大重试次数: {error_detail}")
                    raise
        
        raise Exception("HTML 生成失败")

    def _generate_single_image_html(self, img: dict, figure_number: int, image_class: str = "article-image", is_translated: bool = False) -> str:
        img_path = img.get('path', '')
        page = img.get('page', '')
        position = img.get('vertical_position', 'middle')

        img_src = self._image_to_base64(img_path)

        if is_translated:
            ai_description = (img.get('description_zh') or '').strip() or (img.get('description') or '').strip()
        else:
            ai_description = (img.get('description') or '').strip()

        has_native_caption = img.get('has_native_caption', False)

        if ai_description:
            caption = ai_description
            if not has_native_caption:
                caption = ''
        else:
            caption = f"Figure {figure_number}"
            if page:
                caption += f" (Page {page}"
                if position:
                    caption += f", {position}"
                caption += ")"

        img_html = f'''
    <figure class="{image_class}">
        <img src="{img_src}" alt="{caption}" loading="lazy">
        <figcaption>{caption}</figcaption>
    </figure>'''

        return img_html

    def _generate_image_html(self, images: list, image_class: str = "article-image", is_translated: bool = False) -> str:
        if not isinstance(images, list) or not images:
            return ""

        html_parts = ['<div class="article-images">']
        for idx, img in enumerate(images, 1):
            html_parts.append(self._generate_single_image_html(img, idx, image_class, is_translated))
        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def _inject_article_images_by_anchor(self, html_content: str, article_data: dict, is_translated: bool = False) -> str:
        images = article_data.get('images', [])

        if not isinstance(images, list):
            return html_content

        if not images:
            return html_content

        seen_paths = set()
        unique_images = []
        for img in images:
            img_path = img.get('path', '')
            if not img_path:
                logger.warning(f"图片缺少path字段，跳过: {img}")
                continue
            if img_path not in seen_paths:
                seen_paths.add(img_path)
                unique_images.append(img)

        if not unique_images:
            return html_content

        import re
        figure_number = 1
        result_html = html_content

        for img in unique_images:
            if is_translated and img.get('anchor_text_zh'):
                anchor_text = str(img.get('anchor_text_zh', '')).strip()
            else:
                anchor_value = img.get('anchor_text', '')
                anchor_text = str(anchor_value).strip() if anchor_value else ''

            insert_position = img.get('insert_position', 'after')

            img_html = self._generate_single_image_html(img, figure_number, "article-image", is_translated=is_translated)

            if anchor_text and len(anchor_text) >= 5:
                escaped_anchor = re.escape(anchor_text)

                pattern_p = f'(<p[^>]*>(?:[^<]|<[^/][^>]*>|</[^>]+>)*?{escaped_anchor}(?:[^<]|<[^/][^>]*>|</[^>]+>)*?</p>)'
                match = re.search(pattern_p, result_html, re.DOTALL | re.IGNORECASE)

                if match:
                    if insert_position == 'before':
                        insert_pos = match.start()
                        result_html = result_html[:insert_pos] + '\n' + img_html + '\n' + result_html[insert_pos:]
                    else:
                        insert_pos = match.end()
                        result_html = result_html[:insert_pos] + '\n' + img_html + '\n' + result_html[insert_pos:]
                    figure_number += 1
                    continue

                pattern_text = f'([^<>]*{escaped_anchor}[^<>]*)'
                match = re.search(pattern_text, result_html, re.DOTALL | re.IGNORECASE)

                if match:
                    if insert_position == 'before':
                        insert_pos = match.start()
                        result_html = result_html[:insert_pos] + '\n' + img_html + '\n' + result_html[insert_pos:]
                    else:
                        insert_pos = match.end()
                        result_html = result_html[:insert_pos] + '\n' + img_html + '\n' + result_html[insert_pos:]
                    figure_number += 1
                    continue

                logger.debug(f"anchor_text未找到匹配位置，降级到末尾插入: '{anchor_text[:30]}'")
            else:
                if anchor_text:
                    logger.debug(f"anchor_text过短（{len(anchor_text)}字符），降级到末尾插入")

            first_div_close = result_html.find('</div>')
            if first_div_close != -1:
                result_html = result_html[:first_div_close] + '\n' + img_html + '\n' + result_html[first_div_close:]
            else:
                result_html = result_html + '\n' + img_html

            figure_number += 1

        return result_html

    def _inject_article_images(self, html_content: str, article_data: dict, is_translated: bool = False) -> str:
        images = article_data.get('images', [])

        if not isinstance(images, list):
            return html_content

        if not images:
            return html_content

        has_anchor = any(img.get('anchor_text') for img in images)

        if not UserConfig.ENABLE_VISION_API:
            return self._inject_article_images_with_rules(html_content, article_data, is_translated)
        elif has_anchor:
            return self._inject_article_images_by_anchor(html_content, article_data, is_translated)

        seen_paths = set()
        unique_images = []
        for img in images:
            img_path = img.get('path', '')
            if img_path and img_path not in seen_paths:
                seen_paths.add(img_path)
                unique_images.append(img)

        if not unique_images:
            return html_content

        article_start = article_data.get('start_page', 1)
        article_end = article_data.get('end_page', 999)
        article_length = article_end - article_start + 1

        sorted_images = sorted(unique_images, key=lambda x: x.get('page', 0))

        import re

        block_pattern = r'(</p>|</div>|</ul>|</ol>|</table>|</blockquote>|</h2>|</h3>|</h4>|</section>)'
        blocks = re.split(block_pattern, html_content)

        content_blocks = []
        i = 0
        while i < len(blocks) - 1:
            content_blocks.append(blocks[i] + blocks[i + 1])
            i += 2
        if i < len(blocks):
            content_blocks.append(blocks[i])

        if not content_blocks or len(content_blocks) == 0:
            image_html = self._generate_image_html(sorted_images, image_class="article-image")
            if '</div>' in html_content:
                parts = html_content.rsplit('</div>', 1)
                return parts[0] + image_html + '</div>' + parts[1]
            else:
                return html_content + image_html

        result_blocks = []
        image_idx = 0
        figure_number = 1

        for block_idx, block in enumerate(content_blocks):
            result_blocks.append(block)

            block_relative_position = (block_idx + 1) / len(content_blocks)

            while image_idx < len(sorted_images):
                img = sorted_images[image_idx]
                img_page = img.get('page', article_start)

                if article_length > 1:
                    img_relative_position = (img_page - article_start) / article_length
                else:
                    img_relative_position = img.get('relative_y_top', 0.5)

                if img_relative_position <= block_relative_position:
                    img_html = self._generate_single_image_html(img, figure_number, "article-image", is_translated=is_translated)
                    result_blocks.append(img_html)
                    figure_number += 1
                    image_idx += 1
                else:
                    break

        while image_idx < len(sorted_images):
            img = sorted_images[image_idx]
            img_html = self._generate_single_image_html(img, figure_number, "article-image", is_translated=is_translated)
            result_blocks.append(img_html)
            figure_number += 1
            image_idx += 1

        return '\n'.join(result_blocks)

    def _inject_article_images_with_rules(
        self,
        html_content: str,
        article_data: dict,
        is_translated: bool = False
    ) -> str:
        from bs4 import BeautifulSoup

        images = article_data.get('images', [])
        if not images:
            return html_content

        logger.info(f"规则模式: 准备注入 {len(images)} 张图片")

        soup = BeautifulSoup(html_content, 'html.parser')
        caption_generator = RuleBasedCaptionGenerator()

        position_stats = {'start': 0, 'middle': 0, 'end': 0, 'unknown': 0}

        for img in images:
            caption = caption_generator.generate_caption(img, article_data, UserConfig)

            img_src = self._image_to_base64(img.get('path', ''))

            img_html_str = f'''
    <figure class="article-image">
        <img src="{img_src}" alt="{caption}" loading="lazy">
        <figcaption>{caption}</figcaption>
    </figure>'''

            insert_pos = img.get('insert_position', 'end')
            position_stats[insert_pos if insert_pos in position_stats else 'unknown'] += 1

            img_soup = BeautifulSoup(img_html_str, 'html.parser')

            if insert_pos == 'start':
                first_p = soup.find('p')
                if first_p:
                    first_p.insert_before(img_soup)
                    logger.debug(f"图片插入到开头: {Path(img['path']).name}")
                else:
                    soup.append(img_soup)
                    logger.debug(f"无段落，追加到末尾: {Path(img['path']).name}")

            elif insert_pos == 'middle':
                paragraphs = soup.find_all('p')
                if paragraphs:
                    mid_idx = len(paragraphs) // 2
                    paragraphs[mid_idx].insert_after(img_soup)
                    logger.debug(f"图片插入到中间（第{mid_idx}段之后）: {Path(img['path']).name}")
                else:
                    soup.append(img_soup)
                    logger.debug(f"无段落，追加到末尾: {Path(img['path']).name}")

            else:
                soup.append(img_soup)
                logger.debug(f"图片插入到末尾: {Path(img['path']).name}")

        logger.info(f"规则模式插入完成: start={position_stats['start']}, middle={position_stats['middle']}, end={position_stats['end']}")
        return str(soup)

    def generate_article_html(
        self,
        title: str,
        subtitle: str,
        authors: str,
        content: str
    ) -> str:
        prompt = HTMLGenerationPrompts.CONTENT_GENERATION_PROMPT.format(
            title=title or "（无标题）",
            subtitle=subtitle or "",
            authors=authors or "",
            content=content or "（无内容）"
        )
        
        html = self._call_api(prompt)
        
        return html
    
    def generate_all_articles_html(
        self,
        df: pd.DataFrame,
        show_progress: bool = True,
        max_retries: int = None,
        is_translated: bool = False,
        cache_dir: str = None,
        progress_manager = None,
        html_output_file = None
    ) -> list:
        if max_retries is None:
            max_retries = UserConfig.HTML_BATCH_MAX_RETRIES
            
        total = len(df)
        logger.info(f"开始生成 {total} 篇文章的 HTML...")
        
        results = [None] * total
        
        heartbeat_monitor = HeartbeatMonitor(
            task_name="HTML生成",
            total=total,
            interval_seconds=30
        )
        heartbeat_monitor.start()
        
        cached_count = 0
        need_generate = []

        if cache_dir and progress_manager:
            logger.info(f"检查HTML片段缓存...")
            for idx in range(total):
                row = df.iloc[idx]

                if is_translated:
                    expected_title = row.get('title_zh', '') or row.get('title', '')
                else:
                    expected_title = row.get('title', '')

                cached_html = progress_manager.load_html_fragment_with_validation(
                    cache_dir,
                    idx,
                    expected_title,
                    is_translated=is_translated
                )

                if cached_html:
                    results[idx] = cached_html
                    cached_count += 1
                else:
                    need_generate.append(idx)

            if cached_count > 0:
                logger.info(f"   ✅ 从缓存加载 {cached_count}/{total} 篇文章的HTML")
                logger.info(f"   📝 需要生成 {len(need_generate)} 篇新文章")
        else:
            need_generate = list(range(total))
        
        def _extract_article_fields(row, idx):
            def _safe_str(value, default=''):
                try:
                    if pd.isna(value):
                        return default
                    return str(value) if not isinstance(value, str) else value
                except (TypeError, ValueError):
                    return default

            if is_translated:
                title = row.get('title_zh', '') or row.get('title', '')
                subtitle = row.get('subtitle_zh', '') or row.get('subtitle', '')
                authors = row.get('authors_zh', '') or row.get('authors', '')

                title = _safe_str(title, '')
                subtitle = _safe_str(subtitle, '')
                authors = _safe_str(authors, '')

                if 'content_zh' not in row:
                    raise ValueError(f"文章{idx+1}缺少content_zh列！译文DataFrame必须包含content_zh列。")
                content = row.get('content_zh', '')
                if not content or pd.isna(content):
                    raise ValueError(f"文章{idx+1}的content_zh字段为空！请确认翻译已完成。")
                content = _safe_str(content, '')
            else:
                title = row.get('title', '') or ''
                subtitle = row.get('subtitle', '') or ''
                authors = row.get('authors', '') or ''
                content = row.get('content', '') or ''

                title = _safe_str(title, '')
                subtitle = _safe_str(subtitle, '')
                authors = _safe_str(authors, '')
                content = _safe_str(content, '')

            return title, subtitle, authors, content
        
        def process_article(idx, row, retry_attempt=0):
            max_article_retries = UserConfig.HTML_ARTICLE_RETRIES
            
            for attempt in range(max_article_retries + 1):
                try:
                    title, subtitle, authors, content = _extract_article_fields(row, idx)
                    
                    if attempt > 0:
                        logger.debug(f"重试生成文章 {idx + 1}/{total} (第{attempt + 1}次尝试): {title[:50]}...")
                    else:
                        logger.debug(f"生成文章 {idx + 1}/{total}: {title[:50]}...")
                    
                    html = self.generate_article_html(
                        title=title,
                        subtitle=subtitle,
                        authors=authors,
                        content=content
                    )

                    html = self._inject_article_images(html, row.to_dict(), is_translated=is_translated)

                    if cache_dir and progress_manager:
                        progress_manager.save_html_fragment(
                            cache_dir, idx, html, row.to_dict(), is_translated=is_translated
                        )

                    return idx, html, None, row
                    
                except Exception as e:
                    if attempt < max_article_retries:
                        time.sleep(UserConfig.HTML_ARTICLE_RETRY_DELAY)
                        continue
                    else:
                        error_msg = f"文章 {idx + 1} 生成失败 (尝试{attempt + 1}次): {str(e)}"
                        logger.error(error_msg)
                        return idx, None, error_msg, row
            
            return idx, None, "未知错误", row
        
        def _process_batch_concurrent(article_list, delay_config, is_retry=False, retry_round=0):
            nonlocal success_count, fail_count
            
            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                futures = {}
                
                for item in article_list:
                    if isinstance(item, tuple):
                        idx, row = item
                    else:
                        idx = item
                        row = df.iloc[idx]

                    future = executor.submit(process_article, idx, row, retry_round if is_retry else 0)
                    futures[future] = idx
                
                batch_success = 0
                batch_failed = []
                
                if show_progress and not is_retry:
                    pbar = tqdm(total=len(article_list), desc="🎨 AI生成HTML")
                
                for future in as_completed(futures):
                    idx, html, error, row = future.result()
                    
                    if html:
                        results[idx] = html
                        success_count += 1
                        batch_success += 1
                    else:
                        batch_failed.append((idx, row))
                        fail_count += 1
                    
                    if show_progress and not is_retry:
                        pbar.update(1)
                        pbar.set_postfix({
                            '成功': success_count,
                            '失败': fail_count,
                            '缓存': cached_count
                        })
                
                if show_progress and not is_retry:
                    pbar.close()
                
                return batch_success, batch_failed
        
        failed_articles = []
        
        if not need_generate:
            logger.info(f"   ✅ 所有文章都已从缓存加载，跳过生成")
            return results
        
        success_count = cached_count
        fail_count = 0
        
        _, failed_articles = _process_batch_concurrent(
            need_generate,
            UserConfig.HTML_REQUEST_DELAY,
            is_retry=False
        )
        
        if failed_articles and max_retries > 0:
            logger.info(f"\n🔄 重试 {len(failed_articles)} 篇失败的文章...")
            
            for retry_round in range(max_retries):
                if not failed_articles:
                    break

                ConsoleOutput.info(f"🔄 第 {retry_round + 1}/{max_retries} 轮重试 ({len(failed_articles)} 篇)...", 1)
                
                retry_success, failed_articles = _process_batch_concurrent(
                    failed_articles,
                    UserConfig.HTML_RETRY_DELAY,
                    is_retry=True,
                    retry_round=retry_round + 1
                )
                
                logger.info(f"   本轮重试成功: {retry_success} 篇")
        
        if failed_articles:
            logger.warning(f"⚠️  {len(failed_articles)} 篇文章最终生成失败，使用占位符")
            for idx, _ in failed_articles:
                results[idx] = "<p style='color: #999; font-style: italic;'>（Failed generating HTML of this article, check the Excel or JSON file for more info / 此文章的HTML生成失败，请查看Excel或JSON文件获取原文）</p>"
        
        logger.info(f"✅ HTML 生成完成: 成功 {success_count}/{total}, 失败 {fail_count}/{total}")
        
        return results
    
    def print_failure_stats(self):
        total_failures = sum(self.failure_stats.values())
        
        if total_failures == 0:
            return

        ConsoleOutput.section("📊 HTML生成失败原因分析统计")

        sorted_stats = sorted(self.failure_stats.items(), key=lambda x: x[1], reverse=True)

        failure_names = {
            'network_error': '网络连接错误',
            'json_error': 'JSON解析错误',
            'rate_limit': '速率限制(429)',
            'server_error': '服务器错误(5xx)',
            'auth_error': '认证/权限错误(401/403)',
            'client_error': '客户端错误(400/404)',
            'timeout_error': '超时错误',
            'truncation_error': '输出截断(token限制)',
            'other': '其他错误'
        }

        for reason, count in sorted_stats:
            if count > 0:
                name = failure_names.get(reason, reason)
                percentage = (count / total_failures) * 100
                ConsoleOutput.info(f"{name}: {count} 次 ({percentage:.1f}%)", 2)

        ConsoleOutput.info(f"总计失败: {total_failures} 次", 2)
        ConsoleOutput.section("")

    def _load_cover_images_html(self, pdf_name: str, cache_dir: str, is_translated: bool) -> str:
        import json
        try:
            cover_images_file = None

            if pdf_name:
                possible_cover_file = Path("output/json") / pdf_name / "outline" / "cover_images.json"
                if possible_cover_file.exists():
                    cover_images_file = possible_cover_file
                    logger.debug(f"使用传入的pdf_name: {pdf_name}")

            if not cover_images_file and cache_dir:
                inferred_pdf_name = Path(cache_dir).name
                possible_cover_file = Path("output/json") / inferred_pdf_name / "outline" / "cover_images.json"
                if possible_cover_file.exists():
                    cover_images_file = possible_cover_file
                    logger.debug(f"从cache_dir推断PDF名称: {inferred_pdf_name}")

            if cover_images_file:
                with open(cover_images_file, 'r', encoding='utf-8') as f:
                    cover_images_data = json.load(f)
                if cover_images_data:
                    logger.info(f"成功加载封面图片: {len(cover_images_data)} 张（来源: {cover_images_file}）")
                    return self._generate_image_html(cover_images_data, image_class="cover-image", is_translated=is_translated)
            else:
                logger.warning("未找到封面图片文件 (cover_images.json)")
        except Exception as e:
            logger.warning(f"无法加载封面图片: {e}")
        return ""

    def generate_html(
        self,
        df: pd.DataFrame,
        pdf_name: str = None,
        is_translated: bool = False,
        output_path: str = None,
        cache_dir: str = None,
        progress_manager = None,
        generate_pdf_docx: bool = True
    ) -> str:
        from pathlib import Path

        def safe_str(value, default=''):
            try:
                if pd.isna(value):
                    return default
                return str(value) if not isinstance(value, str) else value
            except (TypeError, ValueError):
                return default

        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            if not pdf_name:
                raise ValueError("当output_path为None时，pdf_name参数是必需的")
            
            output_dir = Path("output/html")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if is_translated:
                filename = f"(译文) {pdf_name}.html"
            else:
                filename = f"{pdf_name}.html"
            
            output_file = output_dir / filename
        
        
        html_type = "译文" if is_translated else "原文"
        
        if cache_dir and progress_manager:
            cached_count = progress_manager.count_html_fragments(cache_dir, is_translated=is_translated)
            if cached_count > 0:
                ConsoleOutput.section(f"🌐 生成HTML（{html_type}）: {output_file.name}（检测到{cached_count}篇缓存）")
            else:
                ConsoleOutput.section(f"🌐 生成HTML（{html_type}）: {output_file.name}（启用文章级断点）")
        else:
            ConsoleOutput.section(f"🌐 生成HTML（{html_type}）: {output_file.name}")
        
        articles_with_content = []
        not_in_toc_count = 0

        for idx, row in df.iterrows():
            content = row.get('content', '') or ''
            content = safe_str(content, '')
            not_in_toc = row.get('not_in_toc', False)

            if len(content.strip()) > 0:
                articles_with_content.append((idx, row))
                if not_in_toc:
                    not_in_toc_count += 1

        ConsoleOutput.info(f"目录内文章: {len(articles_with_content) - not_in_toc_count} 篇", 2)
        ConsoleOutput.info(f"目录外文章: {not_in_toc_count} 篇（将统一显示）", 2)

        if articles_with_content:
            df_with_content = df.iloc[[idx for idx, _ in articles_with_content]].reset_index(drop=True)
            html_list = self.generate_all_articles_html(
                df_with_content,
                show_progress=True,
                is_translated=is_translated,
                cache_dir=cache_dir,
                progress_manager=progress_manager,
                html_output_file=output_file
            )

            if len(html_list) != len(articles_with_content):
                ConsoleOutput.warning(f"HTML生成数量 ({len(html_list)}) 与文章数量 ({len(articles_with_content)}) 不匹配", 2)
                while len(html_list) < len(articles_with_content):
                    html_list.append("<p>（HTML生成失败）</p>")
        else:
            html_list = []
        
        lang = "zh-CN" if is_translated else "en"
        
        magazine_name = pdf_name
        issue_number = ''
        
        try:
            import json
            outline_file = Path(cache_dir) / "outline" / "journal_outline.json" if cache_dir else None
            if outline_file and outline_file.exists():
                with open(outline_file, 'r', encoding='utf-8') as f:
                    outline_data = json.load(f)
                    magazine_name = outline_data.get('journal_name', pdf_name)
                    issue_number = outline_data.get('issue_number', '')

                    if magazine_name == pdf_name or re.match(r'^\d+[-_]', magazine_name):
                        logger.warning(f"检测到journal_name为文件名格式: {magazine_name}，尝试清理...")
                        cleaned_name = re.sub(r'^\d+[-_]', '', magazine_name)
                        cleaned_name = re.sub(r'-[^-]*$', '', cleaned_name)
                        if cleaned_name and len(cleaned_name) > 5:
                            magazine_name = cleaned_name
                            logger.info(f"使用清理后的期刊名: {magazine_name}")
                        else:
                            magazine_name = pdf_name
                            logger.warning(f"清理失败，使用默认名称: {magazine_name}")
        except Exception as e:
            pass

        if issue_number:
            page_title = f"{magazine_name} {issue_number}"
        else:
            page_title = magazine_name

        template_manager = HTMLTemplateManager()
        try:
            template_html = template_manager.get_template(self.template_name)
        except Exception as e:
            logger.warning(f"加载模板 {self.template_name} 失败: {e}，使用默认模板")
            template_html = template_manager.get_template("default")

        sidebar_html = f"""    <!-- 移动端菜单按钮 -->
    <button class="menu-toggle" onclick="toggleSidebar()">☰</button>

    <!-- 左侧边栏 -->
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h1>{page_title}</h1>
            <div class="subtitle" style="text-align: center;">共 {len(articles_with_content)} 篇文章</div>
        </div>
        <nav class="table-of-contents">
            <div class="toc-section-title">📑 目录</div>
            <ul class="toc-list">
"""

        for idx, (_, row) in enumerate(articles_with_content, 1):
            if is_translated:
                title = row.get('title_zh', '') or row.get('title', '无标题')
            else:
                title = row.get('title', '无标题')

            title = safe_str(title, '无标题')
            display_title = title if len(title) <= 50 else title[:47] + "..."

            not_in_toc = row.get('not_in_toc', False)
            icon = '📌 ' if not_in_toc else ''
            extra_class = ' toc-item-not-in-toc' if not_in_toc else ''

            sidebar_html += f"""                <li class="toc-item{extra_class}">
                    <a href="#article-{idx}" onclick="closeSidebarOnMobile()">
                        <span class="toc-number">{icon}{idx}</span>
                        <span class="toc-title">{display_title}</span>
                    </a>
                </li>
"""

        sidebar_html += """            </ul>
        </nav>
    </aside>
"""

        main_content_html = """    <!-- 主内容区域 -->
    <main class="main-content">
        <div class="container">
"""
        
        

        cover_images_html = self._load_cover_images_html(pdf_name, cache_dir, is_translated)

        if cover_images_html:
            main_content_html += f"""
        <!-- 第一页：封面页（标题 + 封面图片） -->
        <div class="cover-page" style="page-break-after: always;">
            <h1 style="text-align: center; font-size: 2.8em; margin-bottom: 30px; color: #333; border-bottom: 3px solid #667eea; padding-bottom: 20px;">
                {page_title}
            </h1>
            <!-- 封面图片区域 -->
            <div class="cover-images-section" style="text-align: center;">
                <h2 style="font-size: 1.5em; margin-bottom: 20px; color: #667eea;">📸 Cover Images / 封面图片</h2>
                {cover_images_html}
            </div>
        </div>
        <!-- 封面页结束，强制分页 -->
"""
        else:
            main_content_html += f"""
        <!-- 第一页：标题页 -->
        <div style="page-break-after: always; padding: 60px 0;">
            <h1 style="text-align: center; font-size: 2.8em; margin-bottom: 30px; color: #333; border-bottom: 3px solid #667eea; padding-bottom: 20px;">
                {page_title}
            </h1>
        </div>
        <!-- 标题页结束，强制分页 -->
"""

        main_content_html += """
        <!-- 第二页：目录页（统计信息 + 目录表格） -->
        <div class="table-of-contents-page" style="margin-bottom: 60px; page-break-after: always;">
            <h2 style="text-align: center; font-size: 2em; margin-bottom: 30px; color: #333; border-bottom: 3px solid #667eea; padding-bottom: 15px;">
                📑 目录
            </h2>
"""

        main_content_html += f"""
            <div style="text-align: center; font-size: 1.2em; margin-bottom: 30px; color: #333;">
                <p style="margin: 8px 0;"><strong>总计：{len(articles_with_content)} 篇文章</strong></p>
            </div>

            <!-- 使用表格格式（DOCX转换效果最佳） -->
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 1.05em;">
                <thead>
                    <tr style="background-color: #667eea; color: white;">
                        <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 60px;">No.</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Article Title / 文章标题</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 30%;">Authors / 作者</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        for idx, (_, row) in enumerate(articles_with_content, 1):
            if is_translated:
                title = row.get('title_zh', '') or row.get('title', '无标题')
                subtitle = row.get('subtitle_zh', '') or row.get('subtitle', '')
                authors = row.get('authors_zh', '') or row.get('authors', '—')
            else:
                title = row.get('title', '无标题')
                subtitle = row.get('subtitle', '')
                authors = row.get('authors', '—')

            title = safe_str(title, '无标题')
            subtitle = safe_str(subtitle, '')
            authors = safe_str(authors, '—')

            title_with_subtitle = title
            if subtitle and subtitle.strip() and subtitle.lower() != 'null':
                title_with_subtitle = f"{title}<br/><em style='font-size: 0.9em; color: #666;'>{subtitle}</em>"

            not_in_toc = row.get('not_in_toc', False)
            not_in_toc_marker = ' 📌' if not_in_toc else ''

            row_bg = "#f9f9f9" if idx % 2 == 0 else "#ffffff"

            main_content_html += f"""
                    <tr style="background-color: {row_bg};">
                        <td style="padding: 12px; text-align: center; border: 1px solid #ddd; font-weight: bold; color: #667eea;">
                            {idx}{not_in_toc_marker}
                        </td>
                        <td style="padding: 12px; border: 1px solid #ddd; line-height: 1.6;">
                            {title_with_subtitle}
                        </td>
                        <td style="padding: 12px; border: 1px solid #ddd; font-style: italic; color: #555;">
                            {authors}
                        </td>
                    </tr>
"""
        
        main_content_html += """
                </tbody>
            </table>
"""
        

        main_content_html += """
        </div>
        <!-- 目录页结束 -->
"""
        
        for idx, (html_content, (_, article_data)) in enumerate(zip(html_list, articles_with_content), 1):
            if is_translated:
                title = article_data.get('title_zh', '') or article_data.get('title', '无标题')
                subtitle = article_data.get('subtitle_zh', '') or article_data.get('subtitle', '')
                authors = article_data.get('authors_zh', '') or article_data.get('authors', '')
            else:
                title = article_data.get('title', '无标题')
                subtitle = article_data.get('subtitle', '')
                authors = article_data.get('authors', '')

            title = safe_str(title, '无标题')
            subtitle = safe_str(subtitle, '')
            authors = safe_str(authors, '')

            not_in_toc = article_data.get('not_in_toc', False)
            data_attr = ' data-not-in-toc="true"' if not_in_toc else ''

            main_content_html += f"""
        <div class="article" id="article-{idx}"{data_attr}>
            <div class="article-number">Article / 文章 {idx}</div>
            <h2>{title}</h2>
"""
            if subtitle and subtitle.strip() and subtitle.lower() != 'null':
                main_content_html += f"            <h3 style='color: #666; font-weight: normal; margin-top: 5px;'>{subtitle}</h3>\n"
            if authors:
                main_content_html += f"            <p style='color: #999; font-style: italic; margin-top: 0px; margin-bottom: 20px;'>{authors}</p>\n"
            
            formatted_content = html_content.replace('</div>', '</div>\n').replace('</section>', '</section>\n')
            
            main_content_html += f"""
            <div class="article-content">
                {formatted_content}
            </div>
        </div>
"""
        main_content_html += """
        </div>
    </main>
"""

        full_html = template_html.format(
            lang=lang,
            page_title=page_title,
            sidebar_content=sidebar_html,
            main_content=main_content_html
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        ConsoleOutput.success(f"HTML已保存: {output_file}", 1)
        logger.info(f"HTML文件已生成: {output_file}")

        self.print_failure_stats()

        if generate_pdf_docx:
            ConsoleOutput.section("HTML后处理")
            try:
                from generators.html_postprocessor import HTMLPostProcessor
                processor = HTMLPostProcessor(output_file)
                processor.process()
            except Exception as e:
                logger.error(f"后处理失败: {e}")
                ConsoleOutput.warning(f"后处理失败: {e}", 1)
        else:
            ConsoleOutput.info("[INFO] 跳过HTML后处理（PDF/DOCX生成）", 1)

        return str(output_file)

