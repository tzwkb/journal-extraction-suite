
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

from config import get_prompts, Constants, UserConfig, PDFExtractionPrompts
from core.pdf_utils import JSONParser, clean_articles_list
from core.pdf_utils import PDFBatchManager, ArticleMerger, PDFPreprocessor
from core.logger import get_logger, HeartbeatMonitor, ConsoleOutput, NetworkErrorHandler, UnifiedRetryPolicy
from core.logger import JSONLWriter

from processors.image_processor import ImageExtractor, ImageCleaner
from core.pdf_utils import TableExtractor
from processors.vision_processor import VisionImageProcessor, VisionLLMClient
from processors.image_processor import (
    RuleBasedCoverSelector,
    RuleBasedImageMatcher
)

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

logger = get_logger("pdf_extractor", level=getattr(__import__('logging'), UserConfig.LOG_LEVEL))

try:
    import fitz
except ImportError:
    logger.error("⚠️ 警告: 未安装 PyMuPDF，请运行: pip install pymupdf")
    fitz = None


def _assign_images_to_articles(batch_images, articles):
    for article in articles:
        if 'images' not in article:
            article['images'] = []
    matched_count = 0
    for img in batch_images:
        if img.get('is_meaningful', True):
            belongs_to = img.get('belongs_to_article')
            if belongs_to:
                for article in articles:
                    if article.get('title') == belongs_to:
                        article['images'].append(img)
                        matched_count += 1
                        break
    return matched_count


class PDFArticleExtractor:
    
    def __init__(
        self,
        api_key: str,
        api_url: str = None,
        model: str = None,
        pages_per_batch: int = None,
        overlap_pages: int = None,
        max_retries: int = None,
        retry_delay: int = None,
        request_interval: int = None,
        max_workers: int = None,
        outline_pages_per_segment: int = None,
        prompts: Dict[str, str] = None,
        source_language: str = "English",
        progress_manager = None,
        api_semaphore = None
    ):
        self.progress_manager = progress_manager
        self.current_pdf_path = None
        self.api_semaphore = api_semaphore

        self.api_key = api_key
        self.api_url = (api_url or UserConfig.PDF_API_BASE_URL).rstrip('/').replace('/v1', '')
        self.model = model or UserConfig.PDF_API_MODEL
        self.chat_endpoint = f"{self.api_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        self.pages_per_batch = pages_per_batch or UserConfig.PAGES_PER_BATCH
        self.overlap_pages = overlap_pages or UserConfig.OVERLAP_PAGES
        self.max_retries = max_retries or UserConfig.MAX_RETRIES
        self.retry_delay = retry_delay or UserConfig.RETRY_DELAY
        self.request_interval = request_interval or UserConfig.REQUEST_INTERVAL
        self.max_workers = max_workers or UserConfig.MAX_WORKERS
        self.outline_pages_per_segment = outline_pages_per_segment or UserConfig.OUTLINE_PAGES_PER_SEGMENT
        self.source_language = source_language

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

        self.prompts = get_prompts(source_language)
        if prompts:
            self.prompts.update(prompts)

        self.batch_manager = PDFBatchManager(pages_per_batch, overlap_pages)
        self.article_merger = ArticleMerger()

        self.image_extractor = ImageExtractor()
        self.table_extractor = TableExtractor()
        self.image_cleaner = ImageCleaner(config=None)
        
        self.failure_stats = {
            'network_error': 0,
            'json_error': 0,
            'rate_limit': 0,
            'server_error': 0,
            'auth_error': 0,
            'client_error': 0,
            'timeout_error': 0,
            'other': 0
        }
        
        if fitz is None:
            raise ImportError("需要安装 PyMuPDF: pip install pymupdf")
    
    def _generate_journal_outline(self, pdf_path: str, json_output_dir: Path = None) -> Dict[str, Any]:
        logger.info("\n" + "="*80)
        logger.info("📖 第1步: 生成期刊大纲和内容摘要（分析前50页）")
        logger.info("="*80)
        logger.info("💡 处理前50页，提取目录 + 生成全局上下文摘要")
        
        doc = fitz.open(pdf_path)
        
        try:
            total_pages = doc.page_count
            
            outline_pages = min(50, total_pages)

            ConsoleOutput.info(f"📄 PDF总页数: {total_pages}", 2)
            ConsoleOutput.info(f"📋 提取目录页数: 前 {outline_pages} 页", 2)
            ConsoleOutput.info(f"⏰ 开始时间: {time.strftime('%H:%M:%S')}", 2)

            if json_output_dir is None:
                outline_dir = Path(Constants.OUTPUT_JSON_DIR) / Path(pdf_path).stem / Constants.OUTLINE_SUBDIR
            else:
                outline_dir = json_output_dir / Constants.OUTLINE_SUBDIR
            outline_dir.mkdir(parents=True, exist_ok=True)
            toc_doc = fitz.open()
            toc_doc.insert_pdf(doc, from_page=0, to_page=outline_pages - 1)
            pdf_bytes = toc_doc.write()
            toc_doc.close()

            ConsoleOutput.info(f"📦 PDF大小: {len(pdf_bytes) / 1024 / 1024:.2f} MB", 2)
            
            prompt = PDFExtractionPrompts.OUTLINE_EXTRACTION_PROMPT.format(
                outline_pages=outline_pages,
                total_pages=total_pages
            )

            log_file = self.llm_log_dir / "outline.jsonl"

            ConsoleOutput.info(f"🤖 正在调用 {self.model}...", 2)
            response = None
            last_error = None

            try:
                ConsoleOutput.info("[1/3] 尝试原始PDF...", 3)
                response = self._call_llm_with_pdf_bytes(
                    pdf_bytes=pdf_bytes,
                    prompt=prompt,
                    temperature=UserConfig.PDF_TEMPERATURE,
                    max_tokens=UserConfig.PDF_MAX_TOKENS,
                    log_file=log_file
                )
                ConsoleOutput.success("原始PDF成功", 3)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                if "webp" in error_msg or "riff" in error_msg or "decode image" in error_msg:
                    ConsoleOutput.warning(f"检测到图像格式问题: {str(e)[:80]}", 3)

                    try:
                        ConsoleOutput.info("[2/3] 选择性删除可疑图像（保留正常图像）...", 3)

                        temp_dir = Path(pdf_path).parent / "temp_preprocessed"
                        temp_dir.mkdir(exist_ok=True)

                        temp_original = temp_dir / f"{Path(pdf_path).stem}_outline_temp.pdf"
                        with open(temp_original, 'wb') as f:
                            f.write(pdf_bytes)

                        temp_cleaned = temp_dir / f"{Path(pdf_path).stem}_outline_selective.pdf"
                        removed_count = PDFPreprocessor.remove_images(
                            str(temp_original),
                            str(temp_cleaned)
                        )
                        ConsoleOutput.info(f"已删除 {removed_count} 个WebP/损坏图像", 3)

                        with open(temp_cleaned, 'rb') as f:
                            cleaned_bytes = f.read()

                        response = self._call_llm_with_pdf_bytes(
                            pdf_bytes=cleaned_bytes,
                            prompt=prompt,
                            temperature=UserConfig.PDF_TEMPERATURE,
                            max_tokens=UserConfig.PDF_MAX_TOKENS,
                            log_file=log_file
                        )
                        ConsoleOutput.success("选择性删除成功", 3)

                    except Exception as e2:
                        last_error = e2
                        ConsoleOutput.warning(f"选择性删除后仍失败: {str(e2)[:80]}", 3)

                        try:
                            ConsoleOutput.info("[3/3] 删除所有图像（最后手段）...", 3)

                            temp_full_cleaned = temp_dir / f"{Path(pdf_path).stem}_outline_full_cleaned.pdf"
                            removed_count = PDFPreprocessor.remove_images(
                                str(temp_original),
                                str(temp_full_cleaned),
                                selective=False
                            )
                            ConsoleOutput.info(f"已删除全部 {removed_count} 个图像", 3)

                            with open(temp_full_cleaned, 'rb') as f:
                                fully_cleaned_bytes = f.read()

                            response = self._call_llm_with_pdf_bytes(
                                pdf_bytes=fully_cleaned_bytes,
                                prompt=prompt,
                                temperature=UserConfig.PDF_TEMPERATURE,
                                max_tokens=UserConfig.PDF_MAX_TOKENS,
                                log_file=log_file
                            )
                            ConsoleOutput.success("完全删除成功（仅大纲使用清理版，后续批次仍用原PDF）", 3)
                            ConsoleOutput.warning("注意：大纲提取已删除所有图像，但不影响后续内容提取", 3)

                        except Exception as e3:
                            last_error = e3
                            ConsoleOutput.error("三步预处理全部失败", 3)
                            raise Exception(f"PDF预处理失败，原始错误: {last_error}")
                else:
                    raise
            
            MAX_OUTLINE_RETRIES = UserConfig.MAX_RETRIES
            tech_retry_count = 0
            quality_retry_count = 0
            
            for retry_attempt in range(MAX_OUTLINE_RETRIES):
                ConsoleOutput.info(f"🧹 正在解析... (尝试 {retry_attempt + 1}/{MAX_OUTLINE_RETRIES})", 2)
                outline_data = JSONParser.parse_llm_response(response, expected_type='object')

                if outline_data is None or not outline_data:
                    quality_retry_count += 1
                    error_msg = f"大纲提取返回空内容 (质量错误 {quality_retry_count}/10): 重新调用AI"
                    ConsoleOutput.warning(error_msg, 2)
                    logger.warning(error_msg)

                    if quality_retry_count < 10:
                        ConsoleOutput.info("🔄 重新调用AI生成大纲...", 2)
                        ConsoleOutput.info(f"⏳ 立即重试（质量错误 {quality_retry_count}/10）...", 2)

                        try:
                            response = self._call_llm_with_pdf_bytes(
                                pdf_bytes=pdf_bytes,
                                prompt=prompt,
                                temperature=UserConfig.PDF_TEMPERATURE,
                                max_tokens=UserConfig.PDF_MAX_TOKENS,
                                log_file=log_file
                            )
                        except Exception as retry_error:
                            tech_retry_count += 1
                            logger.error(f"重试调用LLM失败（技术错误）: {str(retry_error)}")
                            ConsoleOutput.error("重试调用LLM失败", 2, str(retry_error)[:100])
                        continue
                    else:
                        final_error = f"大纲提取质量错误，已达重试上限 (10次)。返回空内容"
                        logger.error(final_error)
                        ConsoleOutput.error(final_error, 2)
                        ConsoleOutput.info("💡 将使用默认大纲（期刊名=PDF文件名）", 2)

                        return {
                            "journal_name": Path(pdf_path).stem,
                            "issue_number": "",
                            "language": "English",
                            "journal_type": "unknown",
                            "content_summary": "Outline extraction failed: returned empty content. Process each batch independently.",
                            "articles": []
                        }

                from logger import ResponseValidator
                is_valid, validation_error = ResponseValidator.validate_journal_outline(outline_data)

                if is_valid:
                    total_articles = len(outline_data.get('articles', []))
                    detected_language = outline_data.get('language', 'English')
                    journal_type = outline_data.get('journal_type', 'unknown')
                    content_summary = outline_data.get('content_summary', '')

                    ConsoleOutput.subsection("✅ 大纲提取成功！")
                    ConsoleOutput.info(f"📚 期刊名: {outline_data.get('journal_name', 'Unknown')}", 2)
                    ConsoleOutput.info(f"📅 刊号: {outline_data.get('issue_number', 'Unknown')}", 2)
                    ConsoleOutput.info(f"🌐 语言: {detected_language}", 2)
                    ConsoleOutput.info(f"📋 类型: {journal_type}", 2)
                    ConsoleOutput.info(f"📝 目录文章数: {total_articles}", 2)

                    if content_summary:
                        ConsoleOutput.subsection("📄 内容摘要（全局上下文）")
                        summary_preview = content_summary[:300] + "..." if len(content_summary) > 300 else content_summary
                        for line in summary_preview.split('\n'):
                            if line.strip():
                                ConsoleOutput.info(line, 3)

                    ConsoleOutput.info(f"⏰ 完成时间: {time.strftime('%H:%M:%S')}", 2)

                    if detected_language == "Russian":
                        ConsoleOutput.info("🔄 检测到俄文期刊，切换为俄文提取提示词", 2)
                        self.prompts = get_prompts("Russian")
                    elif detected_language == "English":
                        ConsoleOutput.info("🔄 检测到英文期刊，使用英文提取提示词", 2)
                        self.prompts = get_prompts("English")
                    else:
                        ConsoleOutput.warning("未识别语言或为中文，默认使用英文提取提示词", 2)

                    logger.info(f"大纲提取成功: {outline_data.get('journal_name', 'Unknown')}")
                    return outline_data
                else:
                    quality_retry_count += 1
                    error_msg = f"大纲验证失败 (质量错误 {quality_retry_count}/3): {validation_error}"
                    ConsoleOutput.warning(error_msg, 2)
                    logger.error(error_msg)
                    logger.error(f"大纲数据: {outline_data}")

                    if quality_retry_count < 3:
                        ConsoleOutput.info("🔄 重新调用AI生成大纲...", 2)
                        ConsoleOutput.info(f"⏳ 立即重试（质量错误 {quality_retry_count}/3）...", 2)

                        try:
                            response = self._call_llm_with_pdf_bytes(
                                pdf_bytes=pdf_bytes,
                                prompt=prompt,
                                temperature=UserConfig.PDF_TEMPERATURE,
                                max_tokens=UserConfig.PDF_MAX_TOKENS,
                                log_file=log_file
                            )
                        except Exception as retry_error:
                            tech_retry_count += 1
                            logger.error(f"重试调用LLM失败（技术错误）: {str(retry_error)}")
                            ConsoleOutput.error("重试调用LLM失败", 2, str(retry_error)[:100])
                    else:
                        final_error = f"大纲提取验证失败，已达最大重试次数 (3次)。最后错误: {validation_error}"
                        logger.error(final_error)
                        logger.error(f"最终大纲数据: {outline_data}")
                        ConsoleOutput.error(final_error, 2)
                        ConsoleOutput.info("💡 将使用默认大纲（期刊名=PDF文件名）", 2)

                        return {
                            "journal_name": Path(pdf_path).stem,
                            "issue_number": "",
                            "language": "English",
                            "journal_type": "unknown",
                            "content_summary": "Outline validation failed after retries. Process each batch independently.",
                            "articles": []
                        }

            ConsoleOutput.warning("未能提取到目录，返回默认结果", 2)
            logger.warning("JSON解析返回None，使用默认大纲")
            return {
                "journal_name": Path(pdf_path).stem,
                "issue_number": "",
                "language": "English",
                "journal_type": "unknown",
                "content_summary": "No context summary available. Process each batch independently.",
                "articles": []
            }

        except Exception as e:
            error_detail = str(e)
            logger.error(f"目录提取异常: {error_detail}")
            logger.exception("完整异常堆栈:")

            ConsoleOutput.warning(f"目录提取异常: {error_detail[:200]}", 2)
            
            return {
                "journal_name": Path(pdf_path).stem,
                "issue_number": "",
                "language": "English",
                "journal_type": "unknown",
                "content_summary": f"Outline extraction failed: {error_detail[:100]}. Process each batch independently.",
                "articles": []
            }
        
        finally:
            doc.close()
    
    def _call_llm_with_pdf_bytes(
        self,
        pdf_bytes: bytes,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = None,
        log_file: Optional[Path] = None,
        batch_idx: Optional[int] = None
    ) -> str:
        if max_tokens is None:
            max_tokens = UserConfig.PDF_MAX_TOKENS

        headers = {
            "Content-Type": "application/json"
        }

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": PDFExtractionPrompts.SYSTEM_PROMPT
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
                                "mimeType": "application/pdf",
                                "data": pdf_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseModalities": ["TEXT"]
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                pdf_size_mb = len(pdf_base64) / 1024 / 1024 * 0.75
                ConsoleOutput.info(f"📤 正在上传PDF到API (大小: {pdf_size_mb:.1f}MB)...", 3)

                if self.api_semaphore:
                    with self.api_semaphore:
                        response = self.session.post(
                            self.chat_endpoint,
                            headers=headers,
                            json=payload,
                            timeout=UserConfig.PDF_API_TIMEOUT,
                            stream=True
                        )
                else:
                    response = self.session.post(
                        self.chat_endpoint,
                        headers=headers,
                        json=payload,
                        timeout=UserConfig.PDF_API_TIMEOUT,
                        stream=True
                    )

                ConsoleOutput.success(f"已收到API响应 (状态码: {response.status_code})", 3)
                response.raise_for_status()

                response_text = response.text

                ConsoleOutput.info("🔍 正在解析JSON响应...", 3)
                result = response.json()

                from logger import APIResponseValidator

                is_valid, response_data, error_msg = APIResponseValidator.validate_and_extract(
                    result,
                    max_tokens,
                    api_type="auto"
                )

                if not is_valid:
                    if "截断" in error_msg or "truncated" in error_msg.lower():
                        ConsoleOutput.warning(f"输出被截断: 内容过长，超出token限制({max_tokens})", 3)
                        raise ValueError(f"PDF提取输出被截断: 内容过长，超出token限制({max_tokens})")

                    ConsoleOutput.error("API响应格式错误", 3, error_msg)
                    ConsoleOutput.info(f"📄 完整响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}", 3)

                    if log_file:
                        try:
                            from logger import UnifiedLLMLogger

                            error_log_file = log_file.parent / f"{log_file.stem}_errors.jsonl"

                            request_log = {
                                "endpoint": self.chat_endpoint.split('?')[0],
                                "model": self.model,
                                "prompt": prompt,
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                "system_instruction": PDFExtractionPrompts.SYSTEM_PROMPT
                            }

                            error_log = {
                                "type": "format_error",
                                "detail": error_msg,
                                "full_response": result
                            }

                            context_log = {
                                "prompt_length": len(prompt),
                                "pdf_size_mb": pdf_size_mb
                            }

                            UnifiedLLMLogger.log_error(
                                error_log_file,
                                request_log,
                                error_log,
                                context_log,
                                metadata={
                                    "stage": "extraction",
                                    "status": "format_error",
                                    "file": getattr(self, 'current_pdf_path', 'unknown'),
                                    "batch": batch_idx if batch_idx is not None else 'unknown'
                                }
                            )
                            ConsoleOutput.cache(f"已保存格式错误日志到: {error_log_file.name}", 3)
                        except Exception as e:
                            ConsoleOutput.warning(f"保存错误日志失败: {e}", 3)

                    raise Exception(f"API响应格式错误: {error_msg}")

                content = response_data["content"]
                finish_reason = response_data["finish_reason"]
                usage = response_data["usage"]

                ConsoleOutput.success(f"成功提取内容 (长度: {len(content)} 字符)", 3)

                if log_file:
                    try:
                        from logger import UnifiedLLMLogger

                        request_log = {
                            "endpoint": self.chat_endpoint.split('?')[0],
                            "model": self.model,
                            "prompt": prompt,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "system_instruction": PDFExtractionPrompts.SYSTEM_PROMPT,
                            "generation_config": payload["generationConfig"]
                        }

                        response_log = {
                            "content": content,
                            "content_length": len(content),
                            "finish_reason": finish_reason,
                            "usage": usage,
                            "full_response": result
                        }

                        context_log = {
                            "prompt_length": len(prompt),
                            "pdf_size_mb": pdf_size_mb
                        }

                        UnifiedLLMLogger.log_success(
                            log_file,
                            request_log,
                            response_log,
                            context_log,
                            metadata={
                                "stage": "extraction",
                                "status": "success",
                                "file": getattr(self, 'current_pdf_path', 'unknown'),
                                "batch": batch_idx if batch_idx is not None else 'unknown'
                            }
                        )
                        ConsoleOutput.cache(f"已保存成功日志到: {log_file.name}", 3)
                    except Exception as e:
                        ConsoleOutput.warning(f"保存成功日志失败: {e}", 3)

                return content

            except Exception as e:
                last_error = e

                from logger import NetworkErrorHandler

                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)
                error_detail = str(e)

                partial_response = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        status_code = e.response.status_code
                        response_text = e.response.text[:500] if e.response.text else ''
                        error_detail = f"{status_code} - {response_text}"
                        partial_response = response_text
                        self.failure_stats['http_error'] = self.failure_stats.get('http_error', 0) + 1
                    except Exception as extract_error:
                        logger.debug(f"无法提取响应内容: {extract_error}")
                elif 'response' in locals() and response is not None:
                    try:
                        partial_response = response.text[:500] if hasattr(response, 'text') else None
                        if partial_response:
                            ConsoleOutput.warning(f"超时但已接收部分响应: {len(partial_response)} 字符", 3)
                    except Exception as extract_error:
                        logger.debug(f"无法提取部分响应: {extract_error}")

                if partial_response is None:
                    if 'timeout' in error_detail.lower():
                        self.failure_stats['timeout_error'] += 1
                    else:
                        self.failure_stats['network_error'] += 1

                if log_file:
                    try:
                        from logger import UnifiedLLMLogger

                        error_log_file = log_file.parent / f"{log_file.stem}_errors.jsonl"

                        request_log = {
                            "endpoint": self.chat_endpoint.split('?')[0],
                            "model": self.model,
                            "prompt": prompt,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "system_instruction": PDFExtractionPrompts.SYSTEM_PROMPT[:200] + "...",
                            "generation_config": payload["generationConfig"]
                        }

                        error_log = {
                            "type": error_type,
                            "detail": error_detail,
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "should_retry": should_retry,
                            "partial_response": partial_response
                        }

                        context_log = {
                            "prompt_length": len(prompt),
                            "pdf_size_mb": pdf_size_mb
                        }

                        UnifiedLLMLogger.log_error(
                            error_log_file,
                            request_log,
                            error_log,
                            context_log,
                            metadata={
                                "stage": "extraction",
                                "status": "retry_error",
                                "file": getattr(self, 'current_pdf_path', 'unknown'),
                                "batch": batch_idx if batch_idx is not None else 'unknown'
                            }
                        )
                        ConsoleOutput.cache(f"已保存错误日志到: {error_log_file.name}", 3)
                    except Exception as log_e:
                        ConsoleOutput.warning(f"保存错误日志失败: {log_e}", 3)

                if should_retry and attempt < self.max_retries - 1:
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt,
                        base_delay=self.retry_delay
                    )
                    ConsoleOutput.retry(error_type, wait_time, attempt + 1, self.max_retries, 2)
                    ConsoleOutput.info(f"详情: {error_detail[:150]}", 3)
                    time.sleep(wait_time)
                    continue
                else:
                    if not should_retry:
                        ConsoleOutput.error(f"{error_type}（不可重试）", 2)
                        ConsoleOutput.info(f"详情: {error_detail[:150]}", 3)
                    break

        raise Exception(f"API调用失败: {str(last_error)}")
    
    def extract_articles_from_batch(
        self,
        pdf_bytes: bytes,
        page_range: str,
        journal_outline: Optional[Dict[str, Any]] = None,
        log_file: Optional[Path] = None,
        batch_pages: Optional[tuple] = None,
        batch_idx: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        context_info = ""

        if journal_outline:
            content_summary = journal_outline.get('content_summary', '')
            journal_type = journal_outline.get('journal_type', '')
            extraction_notes = journal_outline.get('extraction_notes', {})

            if content_summary:
                context_info += f"""**GLOBAL CONTEXT SUMMARY**:
{content_summary}

**Journal Type**: {journal_type}

"""

            if extraction_notes:
                context_info += f"""**EXTRACTION NOTES (从大纲分析获得的经验指导)**:
以下是分析前50页后总结的提取难点和注意事项，请仔细阅读以避免常见错误：

"""
                if extraction_notes.get('layout_challenges'):
                    challenges = extraction_notes['layout_challenges']
                    if isinstance(challenges, list):
                        context_info += "🎯 **布局挑战**:\n"
                        for challenge in challenges:
                            context_info += f"  - {challenge}\n"
                        context_info += "\n"
                    elif isinstance(challenges, str):
                        context_info += f"🎯 **布局挑战**: {challenges}\n\n"

                if extraction_notes.get('common_pitfalls'):
                    pitfalls = extraction_notes['common_pitfalls']
                    if isinstance(pitfalls, list):
                        context_info += "⚠️ **常见陷阱**:\n"
                        for pitfall in pitfalls:
                            context_info += f"  - {pitfall}\n"
                        context_info += "\n"
                    elif isinstance(pitfalls, str):
                        context_info += f"⚠️ **常见陷阱**: {pitfalls}\n\n"

                if extraction_notes.get('special_sections'):
                    sections = extraction_notes['special_sections']
                    if isinstance(sections, list):
                        context_info += "📌 **特殊板块**:\n"
                        for section in sections:
                            context_info += f"  - {section}\n"
                        context_info += "\n"
                    elif isinstance(sections, str):
                        context_info += f"📌 **特殊板块**: {sections}\n\n"

                if extraction_notes.get('image_patterns'):
                    patterns = extraction_notes['image_patterns']
                    if isinstance(patterns, list):
                        context_info += "🖼️ **图片模式**:\n"
                        for pattern in patterns:
                            context_info += f"  - {pattern}\n"
                        context_info += "\n"
                    elif isinstance(patterns, str):
                        context_info += f"🖼️ **图片模式**: {patterns}\n\n"

                if extraction_notes.get('recommendations'):
                    recommendations = extraction_notes['recommendations']
                    context_info += f"💡 **总体建议**:\n{recommendations}\n\n"

                context_info += "---\n\n"

        if journal_outline and journal_outline.get('articles'):
            articles_list = journal_outline.get('articles', [])
            total_articles = len(articles_list)
            
            toc_list = []
            for idx, art in enumerate(articles_list, 1):
                title = art.get('title', '')
                subtitle = art.get('subtitle', '')
                authors = art.get('authors', '')
                article_type = art.get('article_type', '')
                structure_notes = art.get('structure_notes', '')
                
                toc_entry = f"{idx}. {title}"
                if subtitle:
                    toc_entry += f" - {subtitle}"
                if authors:
                    toc_entry += f" (by {authors})"
                if article_type:
                    toc_entry += f" [{article_type}]"
                if structure_notes:
                    toc_entry += f"\n   Structure: {structure_notes}"
                toc_list.append(toc_entry)
            
            toc_text = "\n".join(toc_list)
            
            context_info += f"""**COMPLETE TABLE OF CONTENTS (REFERENCE)**:
This journal contains {total_articles} articles. Below is the complete Table of Contents:

{toc_text}

**CRITICAL INSTRUCTIONS**:
1. Extract content from these pages and MATCH it to the titles in the Table of Contents above
2. Every piece of content MUST be assigned to one of the titles above
3. DO NOT create articles without titles - match content to existing TOC entries
4. Use the EXACT titles from the Table of Contents
5. Pay attention to article_type and structure_notes - they tell you if section headings are part of a larger article
6. If you find content but cannot match it to any TOC entry, assign it to the most appropriate title
7. Preserve all content - do not omit anything

"""
        
        prompt = self.prompts['article_extraction'].format(
            page_range=page_range,
            context_info=context_info
        )

        try:
            ConsoleOutput.info(f"📋 正在调用LLM处理第 {page_range} 页...", 2)

            response = self._call_llm_with_pdf_bytes(
                pdf_bytes,
                prompt,
                temperature=UserConfig.PDF_TEMPERATURE,
                max_tokens=UserConfig.PDF_MAX_TOKENS,
                log_file=log_file,
                batch_idx=batch_idx
            )

            ConsoleOutput.info("🧹 正在解析响应...", 3)

            articles = None
            current_response = response
            fix_attempt = 0

            while fix_attempt < UserConfig.PDF_JSON_FIX_MAX_ATTEMPTS:
                try:
                    articles = JSONParser.parse_llm_response(current_response, expected_type='array')

                    if articles:
                        invalid_count = 0
                        valid_articles = []

                        for idx, article in enumerate(articles):
                            if not isinstance(article, dict):
                                invalid_count += 1
                                logger.warning(f"数组元素 {idx} 不是 dict，而是 {type(article).__name__}")
                                continue

                            title_value = article.get('title')
                            has_title = bool(title_value and str(title_value).strip())

                            content_value = article.get('content')
                            has_content = bool(content_value and str(content_value).strip())

                            if not has_title and not has_content:
                                invalid_count += 1
                                logger.warning(f"数组元素 {idx} 缺少 title 和 content 字段，可能不是文章对象: {list(article.keys())[:5]}")
                                continue

                            valid_articles.append(article)

                        if articles and not valid_articles:
                            raise ValueError(
                                f"[CONTENT_ERROR] 返回的数组不包含有效文章对象。"
                                f"数组中有 {len(articles)} 个元素，但都缺少必需字段（title 或 content）。"
                                f"示例元素字段: {list(articles[0].keys()) if articles else 'N/A'}"
                            )

                        if invalid_count > 0:
                            logger.warning(f"过滤了 {invalid_count} 个无效元素，保留 {len(valid_articles)} 篇有效文章")
                            ConsoleOutput.warning(f"过滤了 {invalid_count} 个无效元素（可能是图片或其他非文章对象）", 3)

                        articles = valid_articles

                    if fix_attempt > 0:
                        ConsoleOutput.success(f"JSON修复成功！(第{fix_attempt}次修复)", 3)
                    break

                except ValueError as e:
                    error_msg = str(e)
                    fix_attempt += 1

                    if fix_attempt == 1:
                        self.failure_stats['json_error'] += 1

                    is_content_error = '[CONTENT_ERROR]' in error_msg

                    if is_content_error:
                        ConsoleOutput.warning(f"内容结构错误(第{fix_attempt}次): {error_msg.replace('[CONTENT_ERROR]', '').strip()[:100]}", 3)
                        ConsoleOutput.info("🔄 LLM 可能误解了任务，将重新从 PDF 提取文章...", 3)

                        fix_prompt = f"""CRITICAL: Your previous response had incorrect data structure.

ERROR: {error_msg.replace('[CONTENT_ERROR]', '').strip()}

Your previous response was:
{current_response[:1000]}...

⚠️ **You returned incorrect data structure (not an article array).**

Please **RE-EXTRACT articles from the PDF** and return a valid JSON array.

REQUIRED OUTPUT FORMAT:
```json
[
  {{
    "title": "Article Title",
    "subtitle": "Optional subtitle",
    "authors": "Author name(s)",
    "content": "Full article text...",
    "not_in_toc": false,
    "images": []
  }},
  ...
]
```

**CRITICAL**:
- You MUST return an ARRAY of article objects: [...]
- Each article MUST have "title" and "content" fields
- DO NOT return a dict with "images" field only
- Extract ALL articles from the PDF pages provided

Re-extract articles from the PDF now:"""

                    else:
                        ConsoleOutput.warning(f"JSON格式错误(第{fix_attempt}次): {error_msg[:80]}", 3)
                        ConsoleOutput.info("🔧 正在请求LLM修复JSON语法...", 3)

                        fix_prompt = f"""Your previous JSON response has a syntax error:

ERROR: {error_msg}

Your previous response was:
{current_response[:2000]}...

Please fix the JSON syntax error and return ONLY the corrected JSON array.
Requirements:
1. Return ONLY valid JSON array format: [...]
2. Fix all syntax errors (missing commas, quotes, brackets, etc.)
3. Keep all the content from the original response
4. Use markdown code block: ```json ... ```

Return the corrected JSON now:"""

                    try:
                        current_response = self._call_llm_with_pdf_bytes(
                            pdf_bytes=pdf_bytes,
                            prompt=fix_prompt,
                            temperature=UserConfig.PDF_TEMPERATURE if is_content_error else 0.0,
                            max_tokens=UserConfig.PDF_MAX_TOKENS,
                            batch_idx=batch_idx
                        )

                        if is_content_error:
                            ConsoleOutput.info("📝 已重新提取，正在解析...", 3)
                        else:
                            ConsoleOutput.info("📝 已收到修复后的JSON，重新解析...", 3)

                    except Exception as fix_error:
                        ConsoleOutput.error("LLM修复请求失败", 3, str(fix_error)[:100])

                        if log_file:
                            try:
                                from logger import UnifiedLLMLogger

                                error_log_file = log_file.parent / f"{log_file.stem}_errors.jsonl"

                                request_log = {
                                    "endpoint": self.chat_endpoint.split('?')[0],
                                    "model": self.model,
                                    "prompt": fix_prompt[:500] + "...",
                                    "temperature": UserConfig.PDF_TEMPERATURE if is_content_error else 0.0,
                                    "max_tokens": UserConfig.PDF_MAX_TOKENS,
                                    "system_instruction": PDFExtractionPrompts.SYSTEM_PROMPT
                                }

                                error_log = {
                                    "type": "json_fix_failed",
                                    "detail": str(fix_error)[:200],
                                    "fix_attempt": fix_attempt,
                                    "max_attempts": UserConfig.PDF_JSON_FIX_MAX_ATTEMPTS,
                                    "original_error": error_msg[:200]
                                }

                                context_log = {
                                    "batch_idx": batch_idx,
                                    "page_range": page_range
                                }

                                UnifiedLLMLogger.log_error(
                                    error_log_file,
                                    request_log,
                                    error_log,
                                    context_log,
                                    metadata={
                                        "stage": "extraction",
                                        "status": "json_fix_failed",
                                        "batch": batch_idx if batch_idx is not None else 'unknown'
                                    }
                                )
                            except Exception as log_e:
                                ConsoleOutput.warning(f"记录JSON修复失败日志失败: {log_e}", 3)

                        ConsoleOutput.warning("无法继续修复JSON，返回空数组", 3)
                        ConsoleOutput.info("💡 提示：外部保护机制会检查并保留现有数据（如果存在）", 3)
                        return []

            if not articles and fix_attempt >= UserConfig.PDF_JSON_FIX_MAX_ATTEMPTS:
                ConsoleOutput.error(f"JSON修复达到最大尝试次数({UserConfig.PDF_JSON_FIX_MAX_ATTEMPTS})，仍未成功", 3)

                if log_file:
                    try:
                        from logger import UnifiedLLMLogger

                        error_log_file = log_file.parent / f"{log_file.stem}_errors.jsonl"

                        request_log = {
                            "endpoint": self.chat_endpoint.split('?')[0],
                            "model": self.model,
                            "temperature": UserConfig.PDF_TEMPERATURE,
                            "max_tokens": UserConfig.PDF_MAX_TOKENS
                        }

                        error_log = {
                            "type": "json_fix_max_attempts_exceeded",
                            "detail": f"达到最大修复次数({UserConfig.PDF_JSON_FIX_MAX_ATTEMPTS})，JSON仍然无效",
                            "fix_attempts": fix_attempt,
                            "last_response_preview": current_response[:500] if current_response else "N/A"
                        }

                        context_log = {
                            "batch_idx": batch_idx,
                            "page_range": page_range
                        }

                        UnifiedLLMLogger.log_error(
                            error_log_file,
                            request_log,
                            error_log,
                            context_log,
                            metadata={
                                "stage": "extraction",
                                "status": "json_fix_exhausted",
                                "batch": batch_idx if batch_idx is not None else 'unknown'
                            }
                        )
                    except Exception as log_e:
                        ConsoleOutput.warning(f"记录JSON修复超限日志失败: {log_e}", 3)

            if not articles:
                return []

            article_count = len(articles) if articles else 0

            if batch_pages:
                start_page, end_page = batch_pages
                for article in articles:
                    if 'start_page' not in article:
                        article['start_page'] = start_page
                    if 'end_page' not in article:
                        article['end_page'] = end_page

            if articles:
                total_content_length = sum(len(str(a.get('content', ''))) for a in articles)
                avg_content_length = total_content_length / len(articles) if articles else 0
                ConsoleOutput.success(f"成功提取 {article_count} 篇文章/片段 (总计 {total_content_length:,} 字符，平均 {avg_content_length:.0f} 字符/篇)", 3)
            else:
                ConsoleOutput.success(f"成功提取 {article_count} 篇文章/片段", 3)

            return articles if articles else []

        except json.JSONDecodeError as e:
            self.failure_stats['json_error'] += 1
            ConsoleOutput.error("JSON解析失败", 3, str(e)[:100])
            ConsoleOutput.info(f"📄 响应内容预览: {response[:500] if 'response' in locals() else 'N/A'}", 3)
            return []
        except Exception as e:
            ConsoleOutput.error("提取失败", 3, str(e))
            return []

    def extract_to_dataframe(self, pdf_path: str, json_output_dir: str = None) -> pd.DataFrame:
        self.current_pdf_path = pdf_path

        pdf_name = Path(pdf_path).stem
        ConsoleOutput.section(f"📄 处理PDF: {pdf_name}")

        if json_output_dir is None:
            json_output_dir = Path(Constants.OUTPUT_JSON_DIR) / pdf_name
        else:
            json_output_dir = Path(json_output_dir)
        json_output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ConsoleOutput.info(f"💾 JSON中间文件将保存到: {json_output_dir}", 1)

        llm_log_dir = Path(Constants.LOGS_LLM_RESPONSES_DIR) / pdf_name
        llm_log_dir.mkdir(parents=True, exist_ok=True)
        self.llm_log_dir = llm_log_dir
        ConsoleOutput.info(f"📝 LLM日志将保存到: {llm_log_dir}", 1)

        outline_dir = json_output_dir / Constants.OUTLINE_SUBDIR
        outline_dir.mkdir(parents=True, exist_ok=True)

        try:
            if self.progress_manager and self.current_pdf_path:
                self.progress_manager.update_stage_progress(
                    self.current_pdf_path,
                    'extraction',
                    'in_progress'
                )

            outline_file = outline_dir / "journal_outline.json"

            if outline_file.exists():
                try:
                    with open(outline_file, 'r', encoding='utf-8') as f:
                        journal_outline = json.load(f)
                    if journal_outline and 'journal_name' in journal_outline and 'content_summary' in journal_outline:
                        ConsoleOutput.cache("期刊大纲已存在，跳过生成", 1)
                        ConsoleOutput.info(f"📚 期刊名: {journal_outline.get('journal_name', 'Unknown')}", 2)
                        ConsoleOutput.info(f"📅 刊号: {journal_outline.get('issue_number', 'Unknown')}", 2)
                        ConsoleOutput.info(f"🌐 语言: {journal_outline.get('language', 'English')}", 2)
                        ConsoleOutput.info(f"📝 目录文章数: {len(journal_outline.get('articles', []))}", 2)
                    else:
                        ConsoleOutput.warning("[缓存] 大纲数据不完整，重新生成...", 1)
                        journal_outline = self._generate_journal_outline(pdf_path, json_output_dir)
                        with open(outline_file, 'w', encoding='utf-8') as f:
                            json.dump(journal_outline, f, ensure_ascii=False, indent=2)
                        ConsoleOutput.cache(f"期刊大纲已保存: {outline_file}", 1)
                except Exception as e:
                    ConsoleOutput.warning(f"[缓存] 加载大纲失败: {e}，重新生成...", 1)
                    journal_outline = self._generate_journal_outline(pdf_path, json_output_dir)
                    with open(outline_file, 'w', encoding='utf-8') as f:
                        json.dump(journal_outline, f, ensure_ascii=False, indent=2)
                    ConsoleOutput.cache(f"期刊大纲已保存: {outline_file}", 1)
            else:
                journal_outline = self._generate_journal_outline(pdf_path, json_output_dir)
                try:
                    with open(outline_file, 'w', encoding='utf-8') as f:
                        json.dump(journal_outline, f, ensure_ascii=False, indent=2)
                    ConsoleOutput.cache(f"期刊大纲已保存: {outline_file}", 1)
                except Exception as e:
                    ConsoleOutput.warning(f"保存期刊大纲失败: {e}", 1)

            ConsoleOutput.section("📄 第2步: 分割PDF为批次")
            batches = self.batch_manager.split_to_batches(pdf_path)

            json_base = Path(Constants.OUTPUT_JSON_DIR)
            try:
                relative_path = json_output_dir.relative_to(json_base)
                image_base_dir = Path(Constants.IMAGE_OUTPUT_DIR) / relative_path
            except ValueError:
                image_base_dir = Path(Constants.IMAGE_OUTPUT_DIR) / Path(pdf_path).stem

            vision_processor = None
            rule_based_matcher = None
            rule_based_cover_selector = None

            if UserConfig.ENABLE_VISION_API:
                vision_log_dir = self.llm_log_dir
                vision_client = VisionLLMClient(
                    self.api_key,
                    self.api_url,
                    self.model,
                    log_dir=str(vision_log_dir),
                    api_semaphore=self.api_semaphore
                )
                vision_temp_dir = image_base_dir / "temp_pages"
                vision_processor = VisionImageProcessor(vision_client, pdf_path, temp_dir=str(vision_temp_dir))
                logger.info(f"✅ Vision AI处理器已初始化（临时目录: {vision_temp_dir}，日志目录: {vision_log_dir}）")
            else:
                rule_based_matcher = RuleBasedImageMatcher()
                rule_based_cover_selector = RuleBasedCoverSelector()
                logger.info(f"✅ 规则图片处理器已初始化（非AI模式）")

            ConsoleOutput.section("📝 第3步: 并发提取文章信息")
            ConsoleOutput.step("🔍 并发提取文章信息...", 1)
            ConsoleOutput.step("💡 多层重试机制（不轻易放弃）:", 1)
            ConsoleOutput.step(f"API级别: 失败自动重试最多 {self.max_retries} 次", 2)
            ConsoleOutput.step(f"批次级别: 失败立即重试最多 5 次（1-3秒快速重试", 2)
            ConsoleOutput.step(f"全局重试: 第一轮完成后，失败批次统一再次重试", 2)
            ConsoleOutput.step(f"⚡ 并发设置: {self.max_workers} 个并发线程同时工作", 1)
            ConsoleOutput.step(f"⏱️  速率控制: 每 {self.request_interval} 秒提交 1 个新任务", 1)
            ConsoleOutput.step(f"📊 共 {len(batches)} 批", 1)
            all_batch_results = [None] * len(batches)
            failed_count = 0
            total_batches = len(batches)
            overall_start_time = time.time()

            heartbeat_monitor = HeartbeatMonitor(
                task_name="PDF提取",
                total=total_batches,
                interval_seconds=30
            )
            heartbeat_monitor.start()

            if self.progress_manager and self.current_pdf_path:
                self.progress_manager.update_stage_progress(
                    self.current_pdf_path,
                    'extraction',
                    'in_progress',
                    completed_count=0,
                    total_count=total_batches
                )

            def process_single_batch(idx, batch, max_batch_retries=None):
                if max_batch_retries is None:
                    max_batch_retries = UserConfig.PDF_BATCH_RETRIES

                use_vision = UserConfig.ENABLE_VISION_API

                page_range = batch['page_range']
                pdf_bytes = batch['pdf_bytes']

                batches_dir = json_output_dir / Constants.BATCHES_SUBDIR
                batches_dir.mkdir(parents=True, exist_ok=True)
                batch_json_file = batches_dir / f"batch_{idx:02d}_pages_{page_range.replace('-', '_')}.json"

                cached_articles = None
                need_vision_fix = False

                if batch_json_file.exists():
                    try:
                        with open(batch_json_file, 'r', encoding='utf-8') as f:
                            cached_articles = json.load(f)

                        if cached_articles:
                            has_images_field = any('images' in article for article in cached_articles)

                            if has_images_field:
                                images_meta_path = batches_dir / f"images_batch_{idx:02d}.json"

                                if images_meta_path.exists():
                                    try:
                                        with open(images_meta_path, 'r', encoding='utf-8') as f:
                                            cached_images = json.load(f)

                                        has_vision_results = any(
                                            img.get('description') and img.get('belongs_to_article') is not None
                                            for img in cached_images
                                            if isinstance(img, dict)
                                        )
                                        has_rule_results = any(
                                            'insert_position' in img and 'description' not in img
                                            for img in cached_images
                                            if isinstance(img, dict)
                                        )

                                        if has_vision_results or has_rule_results:
                                            articles_have_images = any(
                                                'images' in article and article['images']
                                                for article in cached_articles
                                                if isinstance(article, dict)
                                            )

                                            if articles_have_images or has_vision_results:
                                                mode = "Vision" if has_vision_results else "规则"
                                                ConsoleOutput.cache(f"第 {idx}/{total_batches} 批已存在（文章+图片{mode}处理完整），跳过处理", 1)
                                                return idx, cached_articles, None
                                            else:
                                                ConsoleOutput.warning(f"[智能修复] 第 {idx} 批：检测到旧版缓存（图片有规则结果，但文章缺少images字段），将重新匹配...", 1)
                                                need_vision_fix = True
                                        else:
                                            ConsoleOutput.warning(f"[智能修复] 第 {idx} 批：文章缓存有效，但图片缺少Vision处理，将自动补全...", 1)
                                            need_vision_fix = True
                                    except Exception as img_error:
                                        ConsoleOutput.warning(f"[缓存] 读取图片元数据失败: {img_error}，将重新处理", 1)
                                        cached_articles = None
                                else:
                                    ConsoleOutput.warning(f"[智能修复] 第 {idx} 批：文章缓存有效，但图片元数据缺失，将自动补全...", 1)
                                    need_vision_fix = True

                            else:
                                ConsoleOutput.warning(f"[缓存] 第 {idx} 批为旧格式（无图片描述），将重新处理...", 1)
                                cached_articles = None
                    except Exception as e:
                        ConsoleOutput.warning(f"[缓存] 加载第 {idx} 批失败: {e}，将重新处理", 1)
                        cached_articles = None

                if need_vision_fix and cached_articles:
                    try:
                        ConsoleOutput.section("")
                        ConsoleOutput.subsection(f"🔧 [智能修复] 处理第 {idx}/{total_batches} 批 (第 {page_range} 页) - 仅补全图片Vision处理")
                        ConsoleOutput.info(f"使用缓存的 {len(cached_articles)} 篇文章", 2)
                        ConsoleOutput.info(f"⏰ 开始时间: {time.strftime('%H:%M:%S')}", 2)

                        batch_start_time = time.time()

                        json_base = Path(Constants.OUTPUT_JSON_DIR)
                        try:
                            relative_path = json_output_dir.relative_to(json_base)
                            batch_image_dir = Path(Constants.IMAGE_OUTPUT_DIR) / relative_path / f"batch_{idx:02d}"
                        except ValueError:
                            pdf_identifier = json_output_dir.name
                            batch_image_dir = Path(Constants.IMAGE_OUTPUT_DIR) / pdf_identifier / f"batch_{idx:02d}"
                        images_meta_path = batches_dir / f"images_batch_{idx:02d}.json"

                        batch_images = self.image_extractor.extract_batch_with_cache(
                            pdf_bytes,
                            batch['pages'],
                            batch_image_dir,
                            images_meta_path,
                            self.image_cleaner
                        )

                        if batch_images and use_vision and vision_processor:
                            ConsoleOutput.vision_start(len(batch_images), len(cached_articles), page_range, 3)
                            batch_images = vision_processor.annotate_and_match_images_for_batch(
                                pdf_bytes=pdf_bytes,
                                images=batch_images,
                                page_range=page_range,
                                articles=cached_articles
                            )

                            matched_count = _assign_images_to_articles(batch_images, cached_articles)

                            self.image_extractor.save_metadata(batch_images, images_meta_path)

                            with open(batch_json_file, 'w', encoding='utf-8') as f:
                                json.dump(cached_articles, f, ensure_ascii=False, indent=2)

                            ConsoleOutput.info(f"批次 {idx} Vision处理完成，已将 {matched_count} 张图片分配到文章", 3)
                            ConsoleOutput.cache(f"已保存批次 {idx} 的图片Vision处理结果到缓存", 3)
                        elif batch_images and not use_vision and rule_based_matcher:
                            ConsoleOutput.info(f"批次 {idx} 使用规则模式处理 {len(batch_images)} 张图片", 3)

                            for article in cached_articles:
                                if 'images' not in article:
                                    article['images'] = []

                            matches = rule_based_matcher.match_images_to_articles(
                                batch_images,
                                cached_articles,
                                UserConfig
                            )

                            for article_idx, matched_images in matches.items():
                                if article_idx < len(cached_articles):
                                    cached_articles[article_idx]['images'] = matched_images

                            self.image_extractor.save_metadata(batch_images, images_meta_path)

                            with open(batch_json_file, 'w', encoding='utf-8') as f:
                                json.dump(cached_articles, f, ensure_ascii=False, indent=2)

                            ConsoleOutput.info(f"批次 {idx} 规则处理完成，已匹配 {sum(len(imgs) for imgs in matches.values())} 张图片", 3)
                        else:
                            ConsoleOutput.info(f"批次 {idx} 未提取到图片", 3)

                        batch_elapsed = time.time() - batch_start_time
                        ConsoleOutput.success(f"[线程{idx}] 图片Vision处理完成", 2)
                        ConsoleOutput.timing(f"[线程{idx}] 本批耗时", batch_elapsed, 2)

                        return idx, cached_articles, None

                    except Exception as fix_error:
                        error_msg = str(fix_error)
                        ConsoleOutput.error(f"[线程{idx}] 智能修复失败", 1, error_msg[:100])
                        ConsoleOutput.info("将进行完整重新处理...", 2)
                        cached_articles = None
                        need_vision_fix = False

                technical_retry_count = 0
                quality_retry_count = 0
                last_error = None

                while technical_retry_count < max_batch_retries or quality_retry_count < max_batch_retries:
                    try:
                        if technical_retry_count > 0 or quality_retry_count > 0:
                            ConsoleOutput.batch_start(idx, total_batches, page_range)
                            ConsoleOutput.step(f"🔄 重试 [线程{idx}]", 2)
                            ConsoleOutput.step(f"技术错误重试: {technical_retry_count}/{max_batch_retries}", 2)
                            ConsoleOutput.step(f"质量问题重试: {quality_retry_count}/{max_batch_retries}", 2)
                        else:
                            ConsoleOutput.batch_start(idx, total_batches, page_range)
                        ConsoleOutput.step(f"PDF大小: {len(pdf_bytes) / 1024:.1f} KB", 2)
                        ConsoleOutput.step(f"⏰ 开始时间: {time.strftime('%H:%M:%S')}", 2)

                        batch_start_time = time.time()

                        llm_log_file = self.llm_log_dir / "extraction.jsonl"

                        json_base = Path(Constants.OUTPUT_JSON_DIR)
                        try:
                            relative_path = json_output_dir.relative_to(json_base)
                            batch_image_dir = Path(Constants.IMAGE_OUTPUT_DIR) / relative_path / f"batch_{idx:02d}"
                        except ValueError:
                            pdf_identifier = json_output_dir.name
                            batch_image_dir = Path(Constants.IMAGE_OUTPUT_DIR) / pdf_identifier / f"batch_{idx:02d}"
                        images_meta_path = batches_dir / f"images_batch_{idx:02d}.json"

                        batch_images = self.image_extractor.extract_batch_with_cache(
                            pdf_bytes,
                            batch['pages'],
                            batch_image_dir,
                            images_meta_path,
                            self.image_cleaner
                        )

                        tables_meta_path = batches_dir / f"tables_batch_{idx:02d}.json"
                        if tables_meta_path.exists():
                            try:
                                with open(tables_meta_path, 'r', encoding='utf-8') as f:
                                    batch_tables = json.load(f)
                                ConsoleOutput.cache(f"批次 {idx} 表格缓存命中 ({len(batch_tables)} 个)", 3)
                            except Exception:
                                batch_tables = self.table_extractor.extract_tables_from_pdf(
                                    pdf_bytes, batch['pages']
                                )
                                with open(tables_meta_path, 'w', encoding='utf-8') as f:
                                    json.dump(batch_tables, f, ensure_ascii=False, indent=2)
                        else:
                            batch_tables = self.table_extractor.extract_tables_from_pdf(
                                pdf_bytes, batch['pages']
                            )
                            with open(tables_meta_path, 'w', encoding='utf-8') as f:
                                json.dump(batch_tables, f, ensure_ascii=False, indent=2)
                            if batch_tables:
                                ConsoleOutput.info(f"批次 {idx} 提取到 {len(batch_tables)} 个表格", 3)

                        articles = self.extract_articles_from_batch(
                            pdf_bytes,
                            page_range,
                            journal_outline=journal_outline,
                            log_file=llm_log_file,
                            batch_pages=batch['pages'],
                            batch_idx=idx
                        )

                        if not use_vision and articles:
                            for article in articles:
                                if 'images' not in article:
                                    article['images'] = []

                        if batch_images:
                            has_vision_results = any(
                                img.get('description') and img.get('anchor_text') is not None
                                for img in batch_images
                                if isinstance(img, dict)
                            )
                            has_rule_results = any(
                                'insert_position' in img and 'description' not in img
                                for img in batch_images
                                if isinstance(img, dict)
                            )

                            if has_vision_results:
                                ConsoleOutput.cache(f"批次 {idx} 的 {len(batch_images)} 张图片已有Vision处理结果（描述+匹配），跳过", 3)
                            elif has_rule_results and use_vision:
                                ConsoleOutput.cache(f"批次 {idx} 的 {len(batch_images)} 张图片已有规则处理结果，跳过", 3)
                            elif not use_vision and rule_based_matcher:
                                ConsoleOutput.info(f"批次 {idx} 使用规则模式处理 {len(batch_images)} 张图片", 3)

                                if articles:
                                    for article in articles:
                                        if 'images' not in article:
                                            article['images'] = []

                                    matches = rule_based_matcher.match_images_to_articles(
                                        batch_images,
                                        articles,
                                        UserConfig
                                    )

                                    for article_idx, matched_images in matches.items():
                                        if article_idx < len(articles):
                                            articles[article_idx]['images'] = matched_images

                                    self.image_extractor.save_metadata(batch_images, images_meta_path)
                                    ConsoleOutput.info(f"批次 {idx} 规则处理完成，已匹配 {sum(len(imgs) for imgs in matches.values())} 张图片", 3)
                                else:
                                    ConsoleOutput.warning(f"批次 {idx} 未提取到文章，跳过图片处理", 3)
                            elif not use_vision:
                                ConsoleOutput.warning(f"批次 {idx} 规则处理器未初始化，跳过图片处理", 3)
                            else:
                                try:
                                    if articles:
                                        ConsoleOutput.vision_start(len(batch_images), len(articles), page_range, 3)
                                        batch_images = vision_processor.annotate_and_match_images_for_batch(
                                            pdf_bytes=pdf_bytes,
                                            images=batch_images,
                                            page_range=page_range,
                                            articles=articles
                                        )

                                        matched_count = _assign_images_to_articles(batch_images, articles)

                                        self.image_extractor.save_metadata(batch_images, images_meta_path)
                                        ConsoleOutput.info(f"批次 {idx} Vision处理完成，已将 {matched_count} 张图片分配到文章", 3)
                                        ConsoleOutput.cache(f"已保存批次 {idx} 的图片Vision处理结果到缓存", 3)
                                    else:
                                        ConsoleOutput.warning(f"批次 {idx} 未提取到文章，跳过图片处理", 3)
                                except Exception as vision_error:
                                    logger.warning(f"批次 {idx} Vision处理失败: {vision_error}")
                                    ConsoleOutput.warning(f"Vision处理失败: {str(vision_error)[:100]}", 3)
                                    ConsoleOutput.info("将继续使用未处理的图片", 3)

                        if not articles and batch_json_file.exists():
                            try:
                                with open(batch_json_file, 'r', encoding='utf-8') as f:
                                    existing_data = json.load(f)
                                if existing_data:
                                    ConsoleOutput.warning(f"[线程{idx}] 警告：提取结果为空，但已存在非空batch文件", 2)
                                    ConsoleOutput.info(f"[线程{idx}] 保护机制：保留现有文件，不覆盖", 2)
                                    articles = existing_data
                                else:
                                    with open(batch_json_file, 'w', encoding='utf-8') as f:
                                        json.dump(articles, f, ensure_ascii=False, indent=2)
                            except Exception as e:
                                ConsoleOutput.warning(f"[线程{idx}] 读取现有batch文件失败: {e}", 2)
                                with open(batch_json_file, 'w', encoding='utf-8') as f:
                                    json.dump(articles, f, ensure_ascii=False, indent=2)
                        else:
                            with open(batch_json_file, 'w', encoding='utf-8') as f:
                                json.dump(articles, f, ensure_ascii=False, indent=2)
                        
                        batch_elapsed = time.time() - batch_start_time

                        if articles:
                            ConsoleOutput.success(f"[线程{idx}] 第 {idx} 批处理成功，提取到 {len(articles)} 篇文章/片段", 2)
                            ConsoleOutput.cache(f"已保存: {batch_json_file.name}", 2)
                        else:
                            ConsoleOutput.warning(f"[线程{idx}] 第 {idx} 批未提取到文章", 2)
                            ConsoleOutput.cache(f"已保存空结果: {batch_json_file.name}", 2)

                        ConsoleOutput.timing(f"[线程{idx}] 本批耗时", batch_elapsed, 2)

                        if self.progress_manager and self.current_pdf_path:
                            self.progress_manager.update_stage_progress(
                                self.current_pdf_path,
                                'extraction',
                                'in_progress'
                            )

                        return idx, articles, None
                        
                    except Exception as e:
                        from logger import NetworkErrorHandler
                        should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

                        error_msg = str(e)
                        ConsoleOutput.error(f"[线程{idx}] 第{page_range}页处理失败", 2, f"({error_type}): {error_msg[:100]}")
                        last_error = error_msg

                        if should_retry:
                            technical_retry_count += 1
                            if technical_retry_count < max_batch_retries:
                                retry_wait = min(UserConfig.PDF_BATCH_RETRY_WAIT_MAX,
                                               UserConfig.PDF_BATCH_RETRY_WAIT_MIN + technical_retry_count - 1)
                                ConsoleOutput.retry(f"[线程{idx}] 技术错误", retry_wait, technical_retry_count, max_batch_retries, 2)
                                time.sleep(retry_wait)
                            else:
                                ConsoleOutput.error(f"[线程{idx}] 技术错误重试已达上限（{max_batch_retries}次）", 2)
                                break
                        else:
                            quality_retry_count += 1
                            if quality_retry_count < max_batch_retries:
                                retry_wait = min(UserConfig.PDF_BATCH_RETRY_WAIT_MAX,
                                               UserConfig.PDF_BATCH_RETRY_WAIT_MIN + quality_retry_count - 1)
                                ConsoleOutput.retry(f"[线程{idx}] 质量问题", retry_wait, quality_retry_count, max_batch_retries, 2)
                                time.sleep(retry_wait)
                            else:
                                ConsoleOutput.error(f"[线程{idx}] 质量问题重试已达上限（{max_batch_retries}次）", 2)
                                break

                ConsoleOutput.error(f"[线程{idx}] 已达最大重试次数，暂时放弃该批次", 2)
                return idx, [], last_error
            
            completed_count = 0
            failed_batches = []

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for idx, batch in enumerate(batches, 1):
                    future = executor.submit(process_single_batch, idx, batch)
                    futures[future] = idx
                
                with tqdm(total=total_batches, desc="第一轮提取") as pbar:
                    for future in as_completed(futures):
                        idx, articles, error = future.result()
                        all_batch_results[idx - 1] = articles

                        completed_count += 1
                        pbar.update(1)

                        heartbeat_monitor.update(completed_count)

                        elapsed_time = time.time() - overall_start_time
                        avg_time = elapsed_time / completed_count
                        remaining_time = avg_time * (total_batches - completed_count)
                        success_count = completed_count - failed_count
                        ConsoleOutput.progress_summary(completed_count, total_batches, success_count, failed_count, 2)

                        if not articles or len(articles) == 0:
                            failed_count += 1
                            failed_batches.append((idx, batches[idx - 1]))
                            ConsoleOutput.error(f"批次 {idx} 失败（未提取到文章），已记录待重试", 2)

            ConsoleOutput.section("")
            if failed_batches:
                ConsoleOutput.subsection(f"🔄 第一轮完成，发现 {len(failed_batches)} 个失败批次，开始重试...")

                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    retry_futures = {}
                    for idx, batch in failed_batches:
                        future = executor.submit(process_single_batch, idx, batch,
                                               max_batch_retries=UserConfig.PDF_GLOBAL_RETRY_COUNT)
                        retry_futures[future] = idx

                    with tqdm(total=len(failed_batches), desc="重试失败批次") as pbar:
                        retry_success = 0
                        retry_failed = 0
                        for future in as_completed(retry_futures):
                            idx, articles, error = future.result()
                            if articles and len(articles) > 0:
                                all_batch_results[idx - 1] = articles
                                retry_success += 1
                                ConsoleOutput.success(f"批次 {idx} 重试成功！提取到 {len(articles)} 篇", 2)
                            else:
                                retry_failed += 1
                                ConsoleOutput.error(f"批次 {idx} 重试仍然失败", 2)
                            pbar.update(1)

                        ConsoleOutput.subsection(f"📊 重试结果: 成功 {retry_success}/{len(failed_batches)} 个批次")
                        if retry_failed > 0:
                            ConsoleOutput.warning(f"仍有 {retry_failed} 个批次失败，建议稍后手动重试", 2)
            else:
                ConsoleOutput.subsection("✅ 第一轮提取全部成功！无需重试")

            print()

            heartbeat_monitor.stop()

            all_batch_results = [batch for batch in all_batch_results if batch is not None]
            ConsoleOutput.subsection("📊 最终各批次提取统计")
            total_fragments = 0
            success_count = 0
            fail_count = 0
            for idx, batch_articles in enumerate(all_batch_results, 1):
                count = len(batch_articles) if batch_articles else 0
                total_fragments += count
                if count > 0:
                    status = "✅"
                    success_count += 1
                else:
                    status = "❌"
                    fail_count += 1
                ConsoleOutput.info(f"{status} 第 {idx} 批: {count} 篇文章/片段", 2)
            ConsoleOutput.info(f"📦 总计: {total_fragments} 篇文章/片段", 2)
            ConsoleOutput.success(f"成功批次: {success_count}/{len(all_batch_results)}", 2)
            if fail_count > 0:
                ConsoleOutput.error(f"失败批次: {fail_count}/{len(all_batch_results)}", 2)
            print()
            
            batches_dir = json_output_dir / Constants.BATCHES_SUBDIR
            batches_dir.mkdir(parents=True, exist_ok=True)
            all_batches_file = batches_dir / Constants.ALL_BATCHES_FILENAME_TEMPLATE.format(timestamp=timestamp)
            with open(all_batches_file, 'w', encoding='utf-8') as f:
                json.dump(all_batch_results, f, ensure_ascii=False, indent=2)
            ConsoleOutput.cache(f"已保存所有批次原始数据: {all_batches_file.name}", 1)

            merged_articles = self.article_merger.merge_fragments(all_batch_results)
            merged_articles = self.article_merger.deduplicate(merged_articles)

            if merged_articles:
                ConsoleOutput.subsection(f"📄 最终文章列表 (共 {len(merged_articles)} 篇)")
                for idx, article in enumerate(merged_articles, 1):
                    title = (article.get('title') or '').strip() or '（无标题）'
                    content_len = len(article.get('content') or '')
                    ConsoleOutput.info(f"{idx}. {title[:80]} ({content_len} 字符)", 2)
            print()
            
            magazine_name = journal_outline.get('journal_name', Path(pdf_path).stem) if journal_outline else Path(pdf_path).stem
            issue_number = journal_outline.get('issue_number', '') if journal_outline else ''
            for article in merged_articles:
                article['magazine_name'] = magazine_name
                article['issue_number'] = issue_number

            if self.progress_manager and self.current_pdf_path:
                self.progress_manager.update_stage_progress(
                    self.current_pdf_path,
                    'extraction',
                    'completed'
                )
                ConsoleOutput.success("文章提取阶段已完成", 2)

            ConsoleOutput.section("📊  第3.5步: 提取和注入表格")
            try:
                all_tables = []
                for idx, batch in enumerate(batches, 1):
                    tables_meta_path = batches_dir / f"tables_batch_{idx:02d}.json"
                    if tables_meta_path.exists():
                        try:
                            with open(tables_meta_path, 'r', encoding='utf-8') as f:
                                all_tables.extend(json.load(f))
                        except Exception as e:
                            logger.warning(f"读取表格缓存失败 batch_{idx:02d}: {e}")

                if all_tables:
                    ConsoleOutput.info(f"共收集到 {len(all_tables)} 个表格，开始匹配...", 1)
                    all_tables = self.table_extractor.match_tables_to_articles(all_tables, merged_articles)
                    merged_articles = self.table_extractor.inject_tables_into_articles(merged_articles, all_tables)
                    injected = sum(1 for t in all_tables if t.get('inserted'))
                    ConsoleOutput.success(f"表格注入完成: {injected}/{len(all_tables)} 个已插入", 1)
                else:
                    ConsoleOutput.info("未检测到表格，跳过", 1)
            except Exception as tbl_error:
                logger.warning(f"表格注入失败（不影响主流程）: {tbl_error}")
                ConsoleOutput.warning(f"表格注入失败: {str(tbl_error)[:100]}", 1)

            ConsoleOutput.section("🖼️  第4步: 提取和处理图片")

            if self.progress_manager and self.current_pdf_path:
                self.progress_manager.update_stage_progress(
                    self.current_pdf_path,
                    'image_processing',
                    'in_progress'
                )

            image_base_dir.mkdir(parents=True, exist_ok=True)

            try:
                all_images = ImageExtractor.collect_all_images(
                    batches,
                    json_output_dir,
                    self.image_cleaner,
                    image_base_dir
                )

                try:
                    page_1_images = [img for img in all_images if img.get('page') == 1]

                    if page_1_images:
                        if UserConfig.ENABLE_VISION_API and vision_processor:
                            ConsoleOutput.info(f"📸 第1页发现 {len(page_1_images)} 张候选封面图片，使用AI智能选择...", 1)
                            best_cover = vision_processor.select_cover_image(page_1_images)

                            if best_cover:
                                cover_images = [best_cover]
                                outline_dir = json_output_dir / Constants.OUTLINE_SUBDIR
                                outline_dir.mkdir(parents=True, exist_ok=True)
                                cover_images_path = outline_dir / "cover_images.json"
                                with open(cover_images_path, 'w', encoding='utf-8') as f:
                                    json.dump(cover_images, f, ensure_ascii=False, indent=2)

                                confidence = best_cover.get('cover_metadata', {}).get('confidence', 0)
                                reason = best_cover.get('cover_metadata', {}).get('reason', 'N/A')
                                ConsoleOutput.success(f"封面选择成功: 1 张 (置信度: {confidence:.2f})", 1)
                                ConsoleOutput.info(f"理由: {reason}", 2)
                            else:
                                ConsoleOutput.warning("AI未找到合适的封面图片（参见日志了解详情）", 1)

                        elif rule_based_cover_selector:
                            ConsoleOutput.info(f"📸 第1页发现 {len(page_1_images)} 张候选封面图片，使用规则选择...", 1)
                            best_cover = rule_based_cover_selector.select_cover(page_1_images, UserConfig)

                            if best_cover:
                                cover_images = [best_cover]
                                outline_dir = json_output_dir / Constants.OUTLINE_SUBDIR
                                outline_dir.mkdir(parents=True, exist_ok=True)
                                cover_images_path = outline_dir / "cover_images.json"
                                with open(cover_images_path, 'w', encoding='utf-8') as f:
                                    json.dump(cover_images, f, ensure_ascii=False, indent=2)

                                strategy = UserConfig.IMAGE_RULE_BASED_CONFIG.get('cover_selection', 'unknown')
                                ConsoleOutput.success(f"封面选择成功: 1 张 (策略: {strategy})", 1)
                            else:
                                ConsoleOutput.warning("规则未找到合适的封面图片", 1)
                        else:
                            ConsoleOutput.warning("封面处理器未初始化，跳过封面提取", 1)
                    else:
                        ConsoleOutput.warning("第1页未检测到图片，跳过封面提取", 1)

                except Exception as cover_error:
                    error_msg = f"封面图片提取失败: {str(cover_error)}"
                    logger.error(error_msg)
                    logger.exception("详细错误信息:")
                    ConsoleOutput.warning(f"{error_msg}，继续处理内容图片...", 1)

                try:
                    ConsoleOutput.info("正在应用批处理阶段的图片匹配结果...", 1)

                    content_images = [img for img in all_images if img.get('page') != 1]

                    if not content_images:
                        ConsoleOutput.warning("无内容图片需要匹配", 1)
                    else:
                        ConsoleOutput.info(f"共 {len(content_images)} 张内容图片...", 2)

                        ConsoleOutput.info("🧹 执行宽松过滤（去除明显无用图片）...", 2)
                        content_images, loose_stats = self.image_cleaner.loose_filter_low_quality_images(content_images)
                        ConsoleOutput.success(f"宽松过滤完成: 保留 {loose_stats['passed']}/{loose_stats['total']} 张", 2)

                        if not content_images:
                            ConsoleOutput.warning("宽松过滤后无剩余图片", 1)
                        else:
                            matched_count = 0
                            unmatched_count = 0

                            for img in content_images:
                                if img.get('belongs_to_article') is not None:
                                    article_title = img.get('belongs_to_article')
                                    for article in merged_articles:
                                        if article.get('title') == article_title:
                                            if 'images' not in article:
                                                article['images'] = []
                                            article['images'].append(img)
                                            matched_count += 1
                                            break
                                else:
                                    unmatched_count += 1

                            ConsoleOutput.subsection("图片匹配完成")
                            ConsoleOutput.success(f"已匹配: {matched_count} 张", 2)
                            if unmatched_count > 0:
                                ConsoleOutput.info(f"未匹配: {unmatched_count} 张 (AI判断不属于任何文章)", 2)

                except Exception as match_error:
                    error_msg = f"图片匹配失败: {str(match_error)}"
                    logger.error(error_msg)
                    logger.exception("详细错误信息:")
                    ConsoleOutput.warning(f"{error_msg}，文章将不包含图片...", 1)

            except Exception as img_error:
                error_msg = f"图片处理失败: {str(img_error)}"
                ConsoleOutput.error(error_msg, 1)
                logger.error(error_msg)
                logger.exception("图片处理完整错误堆栈:")

                if self.progress_manager and self.current_pdf_path:
                    self.progress_manager.update_stage_progress(
                        self.current_pdf_path,
                        'image_processing',
                        'failed'
                    )

                raise

            if self.progress_manager and self.current_pdf_path:
                self.progress_manager.update_stage_progress(
                    self.current_pdf_path,
                    'image_processing',
                    'completed'
                )
                ConsoleOutput.success("图片处理阶段已完成", 2)

            ConsoleOutput.section("")

            if not merged_articles:
                ConsoleOutput.warning("警告: 未提取到任何文章", 1)
                df = pd.DataFrame(columns=['title', 'subtitle', 'authors', 'content', 'magazine_name', 'issue_number'])
            else:
                df = pd.DataFrame(merged_articles)
                base_columns = ['title', 'subtitle', 'authors', 'content', 'magazine_name', 'issue_number']
                other_columns = [col for col in df.columns if col not in base_columns]
                df = df[base_columns + other_columns]
            
            articles_dir = json_output_dir / Constants.ARTICLES_SUBDIR
            articles_dir.mkdir(parents=True, exist_ok=True)
            final_file = articles_dir / Constants.FINAL_ARTICLES_FILENAME_TEMPLATE.format(timestamp=timestamp)
            final_data = df.to_dict('records')
            
            final_data = clean_articles_list(final_data)

            missing_description_count = 0
            missing_images_info = []
            for article in final_data:
                images = article.get('images', [])
                if isinstance(images, list):
                    for img in images:
                        if isinstance(img, dict):
                            if 'description' not in img or not img.get('description'):
                                missing_description_count += 1
                                img_info = {
                                    'article_title': article.get('title', 'Unknown'),
                                    'page': img.get('page', 'Unknown'),
                                    'path': img.get('path', 'Unknown')
                                }
                                missing_images_info.append(img_info)

            if missing_description_count > 0:
                logger.warning(f"⚠️  发现 {missing_description_count} 张图片缺少AI描述")
                logger.warning(f"   请检查以下批次的图片注释是否成功：")
                pages_with_missing = set(img['page'] for img in missing_images_info)
                logger.warning(f"   受影响页码: {sorted(pages_with_missing)}")

            with open(final_file, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)

            ConsoleOutput.success(f"成功提取 {len(df)} 篇文章", 1)
            ConsoleOutput.cache(f"已保存最终结果: {final_file.name}", 1)
            ConsoleOutput.info(f"📂 所有JSON文件位置: {json_output_dir}", 1)
            ConsoleOutput.section("")

            return df

        except Exception as e:
            ConsoleOutput.error(f"错误: {str(e)}", 1)
            import traceback
            traceback.print_exc()
            raise
