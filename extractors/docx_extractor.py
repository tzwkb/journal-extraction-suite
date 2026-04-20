
import os
import json
import base64
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from tqdm import tqdm
from core.logger import JSONLWriter

from config import get_prompts, Constants, UserConfig, DOCXExtractionPrompts
from core.pdf_utils import JSONParser, clean_articles_list
from core.logger import get_logger, HeartbeatMonitor, ConsoleOutput, NetworkErrorHandler, UnifiedRetryPolicy

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

logger = get_logger("docx_extractor", level=getattr(__import__('logging'), UserConfig.LOG_LEVEL))

class DOCXArticleExtractor:
    
    def __init__(
        self,
        api_key: str,
        api_url: str = None,
        model: str = None,
        max_retries: int = None,
        retry_delay: int = None,
        request_interval: int = None,
        prompts: Dict[str, str] = None,
        source_language: str = "English"
    ):
        self.api_key = api_key
        self.api_url = (api_url or UserConfig.PDF_API_BASE_URL).rstrip('/').replace('/v1', '')
        self.model = model or UserConfig.PDF_API_MODEL
        self.chat_endpoint = f"{self.api_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        self.max_retries = max_retries or UserConfig.MAX_RETRIES
        self.retry_delay = retry_delay or UserConfig.RETRY_DELAY
        self.request_interval = request_interval or UserConfig.REQUEST_INTERVAL
        self.source_language = source_language

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

        self.prompts = get_prompts(source_language)
        if prompts:
            self.prompts.update(prompts)
        
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
    
    def _call_llm_with_docx_bytes(
        self,
        docx_bytes: bytes,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = None,
        log_file: Optional[Path] = None
    ) -> str:
        if max_tokens is None:
            max_tokens = UserConfig.DOCX_MAX_TOKENS
        headers = {
            "Content-Type": "application/json"
        }
        
        docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')
        
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": DOCXExtractionPrompts.SYSTEM_PROMPT
                    }
                ]
            },
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        },
                        {
                            "inlineData": {
                                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                "data": docx_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    self.chat_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=UserConfig.PDF_API_TIMEOUT
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if log_file:
                        log_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(log_file, 'w', encoding='utf-8') as f:
                            json.dump(result, f, ensure_ascii=False, indent=2)

                    from logger import APIResponseValidator

                    is_valid, response_data, error_msg = APIResponseValidator.validate_and_extract(
                        result,
                        max_tokens,
                        api_type="gemini"
                    )

                    if not is_valid:
                        self.failure_stats['truncation_error'] += 1
                        logger.warning(f"⚠️ {error_msg}")
                        raise ValueError(error_msg)

                    text = response_data["content"]
                    finish_reason = response_data["finish_reason"]
                    usage = response_data["usage"]

                    if log_file:
                        from logger import UnifiedLLMLogger
                        docx_size_mb = len(docx_bytes) / (1024 * 1024)
                        request_log = {
                            "endpoint": self.api_url,
                            "model": self.model,
                            "prompt": prompt,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "system_instruction": DOCXExtractionPrompts.SYSTEM_PROMPT
                        }
                        response_log = {
                            "content": text,
                            "content_length": len(text),
                            "finish_reason": finish_reason,
                            "usage": usage,
                            "full_response": result
                        }
                        context_log = {
                            "prompt_length": len(prompt),
                            "docx_size_mb": docx_size_mb
                        }
                        UnifiedLLMLogger.log_success(
                            log_file,
                            request_log,
                            response_log,
                            context_log,
                            metadata={
                                "stage": "docx_extraction",
                                "status": "success"
                            }
                        )
                        logger.debug(f"✅ 已保存DOCX成功日志到: {log_file.name}")

                    return text
                
                elif response.status_code in Constants.RETRYABLE_STATUS_CODES:
                    error_type = f"HTTP {response.status_code}"
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt - 1,
                        base_delay=self.retry_delay
                    )
                    logger.warning(f"⚠️ API返回{response.status_code}，{wait_time:.0f}秒后重试 ({attempt}/{self.max_retries})...")
                    if attempt < self.max_retries:
                        time.sleep(wait_time)
                        continue
                    else:
                        error_msg = f"API调用失败（状态码{response.status_code}）: {response.text[:200]}"
                        logger.error(f"❌ {error_msg}")
                        
                        if response.status_code == 429:
                            self.failure_stats['rate_limit'] += 1
                        elif response.status_code >= 500:
                            self.failure_stats['server_error'] += 1
                        
                        raise RuntimeError(error_msg)
                
                else:
                    error_msg = f"API调用失败（状态码{response.status_code}）: {response.text[:200]}"
                    logger.error(f"❌ {error_msg}")
                    
                    if response.status_code in [401, 403]:
                        self.failure_stats['auth_error'] += 1
                    elif response.status_code in [400, 404]:
                        self.failure_stats['client_error'] += 1
                    else:
                        self.failure_stats['other'] += 1
                    
                    raise RuntimeError(error_msg)
            
            except Exception as e:
                from logger import NetworkErrorHandler

                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)
                error_detail = str(e)[:200]

                if 'timeout' in error_detail.lower():
                    self.failure_stats['timeout_error'] += 1
                elif isinstance(e, requests.exceptions.RequestException):
                    self.failure_stats['network_error'] += 1
                else:
                    self.failure_stats['other'] += 1

                if log_file:
                    error_log_file = log_file.parent / f"{log_file.stem}_errors.jsonl"
                    docx_size_mb = len(docx_bytes) / (1024 * 1024)
                    from logger import UnifiedLLMLogger
                    request_log = {
                        "endpoint": self.api_url,
                        "model": self.model,
                        "prompt": prompt,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "system_instruction": DOCXExtractionPrompts.SYSTEM_PROMPT
                    }
                    error_log = {
                        "type": error_type,
                        "detail": error_detail,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                        "should_retry": should_retry
                    }
                    context_log = {
                        "prompt_length": len(prompt),
                        "docx_size_mb": docx_size_mb
                    }
                    UnifiedLLMLogger.log_error(
                        error_log_file,
                        request_log,
                        error_log,
                        context_log,
                        metadata={
                            "stage": "docx_extraction",
                            "status": "retry_error"
                        }
                    )
                    logger.debug(f"已保存DOCX错误日志到: {error_log_file.name}")

                if should_retry and attempt < self.max_retries:
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt - 1,
                        base_delay=self.retry_delay
                    )
                    logger.warning(f"⏳ {error_type}，{wait_time:.0f}秒后重试（第{attempt}/{self.max_retries}次）")
                    logger.warning(f"   详情: {error_detail}")
                    time.sleep(wait_time)
                    continue
                else:
                    if not should_retry:
                        logger.error(f"❌ {error_type}（不可重试）")
                    else:
                        logger.error(f"❌ 达到最大重试次数")
                    logger.error(f"   详情: {error_detail}")
                    raise
        
        raise RuntimeError(f"API调用失败，已重试{self.max_retries}次")
    
    def _generate_journal_outline(self, docx_path: str, json_output_dir: Path = None) -> Dict[str, Any]:
        logger.info("\n" + "="*80)
        logger.info("📖 第1步: 生成期刊大纲和内容摘要（处理整个DOCX）")
        logger.info("="*80)
        
        with open(docx_path, 'rb') as f:
            docx_bytes = f.read()

        ConsoleOutput.info(f"DOCX文件: {Path(docx_path).name}", 2)
        ConsoleOutput.info(f"文件大小: {len(docx_bytes) / 1024 / 1024:.2f} MB", 2)
        ConsoleOutput.info(f"开始时间: {time.strftime('%H:%M:%S')}", 2)
        
        if json_output_dir is None:
            outline_logs_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(docx_path).stem / Constants.OUTLINE_LOGS_SUBDIR
        else:
            outline_logs_dir = json_output_dir / Constants.OUTLINE_LOGS_SUBDIR
        outline_logs_dir.mkdir(parents=True, exist_ok=True)
        
        docx_filename = Path(docx_path).name
        
        prompt = DOCXExtractionPrompts.OUTLINE_EXTRACTION_PROMPT.format(
            docx_filename=docx_filename
        )
        
        log_file = outline_logs_dir / f"toc_full_document.json"

        ConsoleOutput.info(f"正在调用 {self.model}...", 2)
        response = self._call_llm_with_docx_bytes(
            docx_bytes=docx_bytes,
            prompt=prompt,
            temperature=UserConfig.PDF_TEMPERATURE,
            max_tokens=UserConfig.DOCX_MAX_TOKENS,
            log_file=log_file
        )
        ConsoleOutput.success(f"LLM响应成功", 2)

        outline = JSONParser.parse_and_fix_json(response, self._call_llm_with_docx_bytes, docx_bytes, prompt)

        if outline:
            ConsoleOutput.subsection("📊 期刊信息:")
            ConsoleOutput.info(f"期刊名: {outline.get('journal_name', 'N/A')}", 3)
            ConsoleOutput.info(f"卷期: Vol.{outline.get('volume', 'N/A')}, Issue {outline.get('issue', 'N/A')}", 3)
            ConsoleOutput.info(f"日期: {outline.get('date', 'N/A')}", 3)
            ConsoleOutput.info(f"类型: {outline.get('journal_type', 'N/A')}", 3)

            toc = outline.get('table_of_contents', [])
            ConsoleOutput.subsection(f"📑 目录 (共 {len(toc)} 篇文章):")
            for i, item in enumerate(toc[:5], 1):
                ConsoleOutput.info(f"{i}. {item.get('title', 'N/A')} (p.{item.get('page', 'N/A')})", 3)
            if len(toc) > 5:
                ConsoleOutput.info(f"... 还有 {len(toc) - 5} 篇", 3)
            
            return outline
        else:
            logger.warning("⚠️ 大纲提取失败")
            return {}
    
    def extract_articles(
        self,
        docx_path: str,
        journal_outline: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        logger.info("\n" + "="*80)
        logger.info("📚 第2步: 提取所有文章内容（混合策略）")
        logger.info("="*80)
        
        toc = journal_outline.get('table_of_contents', []) if journal_outline else []
        expected_count = len(toc)
        
        ConsoleOutput.info(f"[策略1/3] 尝试整文件提取...", 2)
        articles = self._extract_whole_file(docx_path, journal_outline)
        actual_count = len(articles)

        if expected_count > 0:
            completeness = actual_count / expected_count
            ConsoleOutput.info(f"提取完整性: {actual_count}/{expected_count} ({completeness*100:.1f}%)", 2)

            if completeness >= 0.9:
                ConsoleOutput.success(f"整文件提取成功！", 2)
                return clean_articles_list(articles)
            else:
                ConsoleOutput.warning(f"输出不完整，切换到分批提取...", 2)
        else:
            if actual_count > 0:
                last_article = articles[-1]
                content = last_article.get('content', '')
                if len(content) > 100:
                    ConsoleOutput.success(f"整文件提取完成（{actual_count}篇）", 2)
                    return clean_articles_list(articles)
                else:
                    ConsoleOutput.warning(f"最后一篇可能被截断，切换到分批提取...", 2)

        if toc and len(toc) > 0:
            ConsoleOutput.info(f"[策略2/3] 按目录分批提取（{len(toc)}篇）...", 2)
            articles = self._extract_by_toc(docx_path, journal_outline)
        else:
            ConsoleOutput.info(f"[策略3/3] 无目录，使用智能分段提取...", 2)
            articles = self._extract_by_intelligent_segments(docx_path, journal_outline)

        ConsoleOutput.success(f"分批提取完成，共 {len(articles)} 篇文章", 2)
        return clean_articles_list(articles)
    
    def _extract_whole_file(
        self,
        docx_path: str,
        journal_outline: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        with open(docx_path, 'rb') as f:
            docx_bytes = f.read()
        
        context_info = self._build_context_info(journal_outline)
        
        docx_filename = Path(docx_path).name
        
        if self.source_language == "Russian":
            article_prompt_template = DOCXExtractionPrompts.ARTICLE_EXTRACTION_RU
        else:
            article_prompt_template = DOCXExtractionPrompts.ARTICLE_EXTRACTION_EN
        
        prompt = article_prompt_template.format(
            docx_filename=docx_filename,
            context_info=context_info
        )
        
        json_output_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(docx_path).stem
        json_output_dir.mkdir(parents=True, exist_ok=True)
        log_file = json_output_dir / f"whole_file_extraction.json"
        
        try:
            response = self._call_llm_with_docx_bytes(
                docx_bytes=docx_bytes,
                prompt=prompt,
                temperature=UserConfig.PDF_TEMPERATURE,
                max_tokens=UserConfig.DOCX_MAX_TOKENS,
                log_file=log_file
            )
            
            articles = JSONParser.parse_and_fix_json(response, self._call_llm_with_docx_bytes, docx_bytes, prompt)
            
            if not articles or not isinstance(articles, list):
                return []
            
            return articles
        except Exception as e:
            logger.error(f"整文件提取失败: {e}")
            return []
    
    def _extract_by_toc(
        self,
        docx_path: str,
        journal_outline: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        toc = journal_outline.get('table_of_contents', [])
        if not toc:
            logger.warning("⚠️ 无目录信息，无法按TOC分批")
            return []
        
        with open(docx_path, 'rb') as f:
            docx_bytes = f.read()
        
        docx_filename = Path(docx_path).name
        json_output_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(docx_path).stem
        json_output_dir.mkdir(parents=True, exist_ok=True)
        
        futures_map = {}
        with ThreadPoolExecutor(max_workers=min(UserConfig.MAX_WORKERS, len(toc))) as executor:
            for idx, toc_item in enumerate(toc, 1):
                title = toc_item.get('title', f'Article {idx}')
                prompt = f"""Extract ONLY the article titled "{title}" from this DOCX document.

FILE: {docx_filename}

**TASK**: Find and extract the complete content of the article titled "{title}".

Return ONLY valid JSON array with ONE article:
```json
[
  {{
    "title": "{title}",
    "subtitle": "subtitle if any, or null",
    "authors": "author names, or null",
    "content": "complete article content in original language"
  }}
]
```

**CRITICAL**:
- Extract ONLY this ONE article
- Do NOT include other articles
- Keep original language
- Include complete content
"""
                log_file = json_output_dir / f"article_{idx:03d}_{title[:30]}.json"
                future = executor.submit(
                    self._call_llm_with_docx_bytes,
                    docx_bytes, prompt,
                    UserConfig.PDF_TEMPERATURE, UserConfig.DOCX_MAX_TOKENS, log_file
                )
                futures_map[future] = (idx, title, len(toc), docx_bytes)

        ConsoleOutput.info(f"并发提取 {len(toc)} 篇文章...", 2)
        return self._run_parallel_extraction("DOCX提取(按目录)", futures_map)
    
    def _extract_by_intelligent_segments(
        self,
        docx_path: str,
        journal_outline: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        with open(docx_path, 'rb') as f:
            docx_bytes = f.read()
        
        docx_filename = Path(docx_path).name
        json_output_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(docx_path).stem
        json_output_dir.mkdir(parents=True, exist_ok=True)
        
        ConsoleOutput.info(f"[1/2] 识别文章边界...", 2)
        context_info = self._build_context_info(journal_outline)
        
        identification_prompt = f"""Analyze this DOCX document and identify all articles.

FILE: {docx_filename}

{context_info}

**TASK**: Identify ALL articles in this document. For each article, provide:
1. Estimated article number (1, 2, 3, ...)
2. Article title (or "Untitled Article N" if no clear title)
3. Brief description (2-3 sentences about what this article is about)

Return ONLY valid JSON array:
```json
[
  {{
    "article_number": 1,
    "title": "Article title or 'Untitled Article 1'",
    "description": "Brief 2-3 sentence description"
  }}
]
```

**IMPORTANT**: Include ALL articles, even small ones."""
        
        log_file = json_output_dir / f"article_identification.json"
        
        try:
            response = self._call_llm_with_docx_bytes(
                docx_bytes,
                identification_prompt,
                UserConfig.PDF_TEMPERATURE,
                UserConfig.DOCX_MAX_TOKENS,
                log_file
            )
            
            identified_articles = JSONParser.parse_and_fix_json(
                response,
                self._call_llm_with_docx_bytes,
                docx_bytes,
                identification_prompt
            )
            
            if not identified_articles or not isinstance(identified_articles, list):
                logger.warning("   ⚠️ 文章识别失败，回退到整文件提取")
                return self._extract_whole_file(docx_path, journal_outline)

            ConsoleOutput.success(f"识别到 {len(identified_articles)} 篇文章", 2)
        except Exception as e:
            logger.error(f"   ❌ 文章识别失败: {e}")
            logger.warning("   ⚠️ 回退到整文件提取")
            return self._extract_whole_file(docx_path, journal_outline)
        
        ConsoleOutput.info(f"[2/2] 按识别的文章逐篇提取...", 2)
        futures_map = {}
        with ThreadPoolExecutor(max_workers=min(UserConfig.MAX_WORKERS, len(identified_articles))) as executor:
            for identified in identified_articles:
                article_num = identified.get('article_number', 0)
                title = identified.get('title', f'Article {article_num}')
                description = identified.get('description', '')
                prompt = f"""Extract the complete article from this DOCX document.

FILE: {docx_filename}

**TARGET ARTICLE**:
- Number: {article_num}
- Title: {title}
- Description: {description}

**TASK**: Extract the COMPLETE content of this specific article.

Return ONLY valid JSON array with ONE article:
```json
[
  {{
    "title": "{title}",
    "subtitle": "subtitle if any, or null",
    "authors": "author names, or null",
    "content": "complete article content in original language"
  }}
]
```

Use the description to locate the correct article. Extract ONLY this ONE article."""
                log_file = json_output_dir / f"segment_{article_num:03d}_{title[:30]}.json"
                future = executor.submit(
                    self._call_llm_with_docx_bytes,
                    docx_bytes, prompt,
                    UserConfig.PDF_TEMPERATURE, UserConfig.DOCX_MAX_TOKENS, log_file
                )
                futures_map[future] = (article_num, title, len(identified_articles), docx_bytes)

        return self._run_parallel_extraction("DOCX提取(智能分段)", futures_map)
    
    def _run_parallel_extraction(self, task_name: str, futures_map: dict) -> List[Dict[str, Any]]:
        total = len(futures_map)
        all_articles = []
        heartbeat_monitor = HeartbeatMonitor(task_name=task_name, total=total, interval_seconds=30)
        heartbeat_monitor.start()
        completed_count = 0
        for future in tqdm(as_completed(futures_map), total=total, desc="   提取进度"):
            idx, title, total_count, docx_bytes = futures_map[future]
            completed_count += 1
            heartbeat_monitor.update(completed_count)
            try:
                response = future.result()
                article_list = JSONParser.parse_and_fix_json(
                    response, self._call_llm_with_docx_bytes, docx_bytes, f"Extract article: {title}"
                )
                if article_list and isinstance(article_list, list):
                    all_articles.extend(article_list)
                    logger.info(f"   ✅ [{idx}/{total_count}] {title}")
                else:
                    logger.warning(f"   ⚠️ [{idx}/{total_count}] {title} - 提取失败")
            except Exception as e:
                logger.error(f"   ❌ [{idx}/{total_count}] {title}: {str(e)[:100]}")
                self.failure_stats['other'] += 1
        heartbeat_monitor.stop()
        return all_articles

    def _build_context_info(self, journal_outline: Optional[Dict[str, Any]]) -> str:
        context_info = ""
        
        if not journal_outline:
            return context_info
        
        content_summary = journal_outline.get('content_summary', '')
        journal_type = journal_outline.get('journal_type', '')
        
        if content_summary:
            context_info += f"""**GLOBAL CONTEXT SUMMARY**:
{content_summary}

"""
        
        if journal_type:
            context_info += f"""**JOURNAL TYPE**: {journal_type}

"""
        
        toc = journal_outline.get('table_of_contents', [])
        if toc:
            context_info += f"""**COMPLETE TABLE OF CONTENTS**:
"""
            for idx, item in enumerate(toc, 1):
                title = item.get('title', 'N/A')
                page = item.get('page', 'N/A')
                context_info += f"{idx}. {title} (Page {page})\n"
            context_info += "\n"
        
        return context_info
    
    def extract_to_dataframe(self, docx_path: str, json_output_dir: str = None) -> pd.DataFrame:
        logger.info("\n" + "🎯"*40)
        logger.info(f"开始处理DOCX: {docx_path}")
        logger.info("🎯"*40)
        
        start_time = time.time()
        
        if json_output_dir is None:
            json_output_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(docx_path).stem
        else:
            json_output_dir = Path(json_output_dir)
        
        json_output_dir.mkdir(parents=True, exist_ok=True)
        
        journal_outline = self._generate_journal_outline(docx_path, json_output_dir)
        
        articles = self.extract_articles(docx_path, journal_outline)
        
        if not articles:
            logger.warning("⚠️ 未提取到任何文章，返回空DataFrame")
            return pd.DataFrame()
        
        df = pd.DataFrame(articles)
        
        if journal_outline:
            df['journal_name'] = journal_outline.get('journal_name', '')
            df['volume'] = journal_outline.get('volume', '')
            df['issue'] = journal_outline.get('issue', '')
            df['date'] = journal_outline.get('date', '')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_json_path = json_output_dir / Constants.FINAL_ARTICLES_FILENAME_TEMPLATE.format(timestamp=timestamp)
        with open(final_json_path, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n✅ 最终JSON已保存: {final_json_path}")
        
        elapsed = time.time() - start_time
        logger.info(f"\n⏱️ 总耗时: {elapsed:.1f}秒")
        logger.info(f"📊 提取文章数: {len(articles)}")
        
        return df

