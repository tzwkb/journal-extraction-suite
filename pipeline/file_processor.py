
import time
import json
import sys
import hashlib
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future, as_completed, TimeoutError, wait
from threading import Semaphore, Lock
from contextlib import contextmanager
from typing import Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime

import pandas as pd

from config import Constants, UserConfig
from core.logger import get_logger
from core.logger import JSONLWriter
from core.pdf_utils import TableExtractor

logger = get_logger("batch_processor")

class ThreadSafeLogger:
    
    def __init__(self):
        self.print_lock = Lock()
        self.progress_lock = Lock()
        self.progress_info = {}
        
        self.log_buffer = []
        self.buffer_lock = Lock()
        self.buffer_max_size = UserConfig.LOG_BUFFER_MAX_SIZE
        self.last_flush_time = time.time()
        self.flush_interval = UserConfig.LOG_FLUSH_INTERVAL
        self.err_last_print_time_by_key = {}
        self.err_suppressed_counts = {}
        self.err_rate_limit_seconds = UserConfig.LOG_ERROR_RATE_LIMIT_SECONDS
    
    def safe_print(self, *args, **kwargs):
        message = ' '.join(str(arg) for arg in args)
        
        with self.buffer_lock:
            self.log_buffer.append((message, time.time()))
            
            should_flush = (
                len(self.log_buffer) >= self.buffer_max_size or
                (time.time() - self.last_flush_time) > self.flush_interval
            )
        
        if should_flush:
            self.flush_buffer()
    
    def flush_buffer(self):
        with self.print_lock:
            with self.buffer_lock:
                if not self.log_buffer:
                    return
                
                messages = self.log_buffer
                self.log_buffer = []
                self.last_flush_time = time.time()
            counts = {}
            order = []
            error_groups = {}
            error_examples = {}
            error_key_counts = {}
            error_key_order = []
            total_error_msgs = 0
            for msg, timestamp in messages:
                if msg in counts:
                    counts[msg] += 1
                else:
                    counts[msg] = 1
                    order.append(msg)
                if self._is_error_message(msg):
                    total_error_msgs += 1
                    key = self._normalize_error_key(msg)
                    error_groups[key] = error_groups.get(key, 0) + 1
                    if key not in error_examples:
                        error_examples[key] = msg
                    if key in error_key_counts:
                        error_key_counts[key] += 1
                    else:
                        error_key_counts[key] = 1
                        error_key_order.append(key)
            for msg in order:
                if not self._is_error_message(msg):
                    cnt = counts[msg]
                    if cnt <= 1:
                        print(msg)
                    else:
                        print(f"{msg} (x{cnt})")
            now_ts = time.time()
            for key in error_key_order:
                total_cnt = error_key_counts.get(key, 0)
                example = error_examples.get(key, '')
                last_ts = self.err_last_print_time_by_key.get(key, 0)
                if (now_ts - last_ts) >= self.err_rate_limit_seconds:
                    if total_cnt <= 1:
                        print(example)
                    else:
                        print(f"{example} (x{total_cnt})")
                    self.err_last_print_time_by_key[key] = now_ts
                else:
                    self.err_suppressed_counts[key] = self.err_suppressed_counts.get(key, 0) + total_cnt
            if total_error_msgs >= 3 or len(error_groups) >= 2 or len(self.err_suppressed_counts) > 0:
                print('─' * 80)
                print('🧾 错误摘要（本次批量）')
                sorted_items = sorted(error_groups.items(), key=lambda kv: kv[1], reverse=True)
                for key, cnt in sorted_items[:10]:
                    example = error_examples.get(key, '')
                    marker = '❌' if ('❌' in example or 'error' in example.lower() or 'failed' in example.lower() or '失败' in example) else '⚠️'
                    suppressed = self.err_suppressed_counts.get(key, 0)
                    if suppressed > 0:
                        print(f"  {marker} {example} (x{cnt})｜过去 {self.err_rate_limit_seconds}s 抑制 x{suppressed}")
                    else:
                        print(f"  {marker} {example} (x{cnt})")
                print('─' * 80)
                self.err_suppressed_counts = {}
            sys.stdout.flush()

    def _is_error_message(self, msg: str) -> bool:
        m = msg.lower()
        if '❌' in msg or '⚠️' in msg:
            return True
        keywords = (
            'error', 'failed', '异常', '失败', '超时', 'timeout', '429', '5xx', 'httperror', 'connecttimeout', 'rate limit', '限流'
        )
        return any(k in m for k in keywords)

    def _normalize_error_key(self, msg: str) -> str:
        normalized = ''.join('{n}' if ch.isdigit() else ch for ch in msg)
        normalized = ' '.join(normalized.split())
        cut = normalized.rfind(' (x')
        if cut != -1 and normalized.endswith(')'):
            normalized = normalized[:cut]
        return normalized
    
    def update_progress(self, file_idx: int, status: str, filename: str):
        with self.progress_lock:
            self.progress_info[file_idx] = {
                'status': status,
                'filename': filename,
                'time': datetime.now()
            }
    
    def print_progress_panel(self, completed: int, total: int):
        with self.print_lock:
            print(f"\n{'─' * 80}")
            print(f"📊 总进度: {completed}/{total} ({completed/total*100:.1f}%)")
            
            processing = [v for v in self.progress_info.values() if v['status'] == 'processing']
            if processing:
                print(f"🔄 正在处理 ({len(processing)}个):")
                for info in processing[:5]:
                    print(f"   • {info['filename']}")
                if len(processing) > 5:
                    print(f"   ... 还有 {len(processing) - 5} 个")
            
            print(f"{'─' * 80}\n")
            sys.stdout.flush()

def _filter_ads_from_df(df, ad_keywords):
    if df is None or len(df) == 0:
        return df, 0, []
    if not ad_keywords:
        return df, 0, []
    removed_indices = []
    removed_titles = []
    for idx, row in df.iterrows():
        title = str(row.get('title', ''))
        for keyword in ad_keywords:
            if keyword.lower() in title.lower():
                removed_indices.append(idx)
                removed_titles.append((str(row.get('title', 'N/A'))[:60], f"title contains '{keyword}'"))
                break
    if removed_indices:
        return df.drop(removed_indices).reset_index(drop=True), len(removed_indices), removed_titles
    return df, 0, []

def get_output_path_with_structure(base_dir: str, filename: str, input_file: str, input_structure: Dict) -> str:
    normalized_input = input_file.replace('\\', '/')
    relative_folder = input_structure.get(normalized_input, "")
    output_dir = Path(base_dir)
    if relative_folder:
        output_dir = output_dir / relative_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / filename)

class BatchFileProcessor:
    
    def __init__(
        self,
        extractor,
        excel_generator,
        html_generator,
        pdf_generator,
        docx_generator,
        translator,
        input_structure: Dict,
        generate_pdf: bool,
        generate_docx: bool,
        generate_translation: bool,
        output_language_mode: str = "both",
        docx_extractor=None,
        progress_manager=None
    ):
        self.extractor = extractor
        self.docx_extractor = docx_extractor
        self.excel_generator = excel_generator
        self.html_generator = html_generator
        self.pdf_generator = pdf_generator
        self.docx_generator = docx_generator
        self.translator = translator
        self.input_structure = input_structure
        self.generate_pdf = generate_pdf
        self.generate_docx = generate_docx
        self.generate_translation = generate_translation
        self.output_language_mode = output_language_mode
        self.progress_manager = progress_manager

        self.lock = Lock()
        self.success_files = []
        self.partial_files = []
        self.failed_files = []
        self.completed_count = 0
        
        self.safe_logger = ThreadSafeLogger()
    
    def get_output_path_with_structure(self, base_dir: str, filename: str, input_file: str) -> str:
        return get_output_path_with_structure(base_dir, filename, input_file, self.input_structure)
    
    def process_single_file(self, input_file: str, file_idx: int, total_files: int) -> Dict:
        file_start_time = time.time()
        file_name = Path(input_file).stem
        file_short_name = Path(input_file).name[:40]
        file_ext = Path(input_file).suffix.lower()
        issues = []
        cache_checked = False
        
        prefix = f"[#{file_idx:02d} {file_short_name}]"
        
        try:
            self.safe_logger.update_progress(file_idx, 'processing', Path(input_file).name)
            
            if self.progress_manager:
                self.progress_manager.mark_file_started(input_file)
            
            self.safe_logger.safe_print(f"\n{'=' * 80}")
            self.safe_logger.safe_print(f"{prefix} 开始处理...")
            self.safe_logger.safe_print(f"{'=' * 80}")
            
            file_progress = None
            if self.progress_manager:
                file_progress = self.progress_manager.get_file_progress(input_file)
                
                all_files_in_session = self.progress_manager.progress_data.get('files', [])
                if all_files_in_session and file_progress is None:
                    normalized_input = input_file.replace('\\', '/')
                    error_msg = (
                        f"\n{'='*80}\n"
                        f"❌ 严重错误：断点恢复失败！\n"
                        f"{'='*80}\n"
                        f"文件路径不匹配，无法读取进度数据！\n\n"
                        f"查找的路径: {normalized_input}\n"
                        f"会话中的路径示例: {all_files_in_session[0] if all_files_in_session else 'N/A'}\n\n"
                        f"⚠️ 如果继续处理，将从头开始，重复调用API，浪费配额！\n\n"
                        f"解决方案：\n"
                        f"  1. 停止程序（已为您停止）\n"
                        f"  2. 路径标准化已在最新代码中修复\n"
                        f"  3. 重新运行程序，断点恢复将正常工作\n"
                        f"{'='*80}\n"
                    )
                    self.safe_logger.safe_print(error_msg)
                    raise RuntimeError("断点恢复路径不匹配，已停止处理以防重复调用API")
                
                if file_progress and file_idx == 0:
                    stages = file_progress.get('stages', {})
                    completed_stages = [k for k, v in stages.items() if v == 'completed']
                    pending_stages = [k for k, v in stages.items() if v == 'pending']
                    
                    self.safe_logger.safe_print(f"{prefix} [断点] 文件进度状态:")
                    self.safe_logger.safe_print(f"{prefix}    已完成阶段: {', '.join(completed_stages) if completed_stages else '无'}")
                    self.safe_logger.safe_print(f"{prefix}    待处理阶段: {', '.join(pending_stages) if pending_stages else '无'}")
                    
                    if not completed_stages and all_files_in_session:
                        self.safe_logger.safe_print(f"{prefix} ⚠️  所有阶段都未完成，将从头处理")
                    elif completed_stages:
                        self.safe_logger.safe_print(f"{prefix} ✅ 将跳过已完成阶段")
            
            df = None
            
            relative_folder = self.input_structure.get(input_file.replace('\\', '/'), "")
            json_base_dir = Path(Constants.OUTPUT_JSON_DIR)
            if relative_folder:
                json_output_dir = json_base_dir / relative_folder / file_name
            else:
                json_output_dir = json_base_dir / file_name

            final_json = None
            articles_dir = json_output_dir / Constants.ARTICLES_SUBDIR
            if articles_dir.exists():
                for json_file in articles_dir.glob("final_articles_*.json"):
                    final_json = json_file
                    break
                
                if not final_json:
                    for json_file in articles_dir.glob("merged_articles_*.json"):
                        final_json = json_file
                        break
            
            if final_json and final_json.exists():
                self.safe_logger.safe_print(f"{prefix} [1/6] 检测到最终文章JSON，从缓存加载...")
                self.safe_logger.safe_print(f"{prefix} [缓存] 文件: {final_json.name}")
                self.safe_logger.safe_print(f"{prefix} [缓存] 大小: {final_json.stat().st_size / 1024:.2f} KB")
                self.safe_logger.safe_print(f"{prefix} [缓存] 修改时间: {datetime.fromtimestamp(final_json.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    with open(final_json, 'r', encoding='utf-8') as f:
                        articles = json.load(f)
                    
                    if not articles or len(articles) == 0:
                        raise ValueError("缓存文件为空")
                    
                    df = pd.DataFrame(articles)
                    
                    sample_titles = [a.get('title', 'N/A')[:30] + ('...' if len(a.get('title', '')) > 30 else '') 
                                    for a in articles[:3]]
                    
                    self.safe_logger.safe_print(f"{prefix} [缓存] ✅ 成功加载 {len(df)} 篇文章")
                    self.safe_logger.safe_print(f"{prefix} [缓存] 示例: {sample_titles}")
                    
                    time_saved = len(df) * 5
                    self.safe_logger.safe_print(f"{prefix} [跳过] 🚀 跳过PDF提取阶段，节省约 {time_saved} 秒")
                    
                    if self.progress_manager:
                        self.progress_manager.update_stage_progress(input_file, 'extraction', 'completed')

                        file_stem = Path(input_file).stem
                        
                        excel_original_path = self.get_output_path_with_structure("output/excel", f"{file_stem}.xlsx", input_file)
                        if Path(excel_original_path).exists():
                            self.progress_manager.update_stage_progress(input_file, 'excel_original', 'completed')
                        
                        html_original_path = self.get_output_path_with_structure("output/html", f"{file_stem}.html", input_file)
                        if Path(html_original_path).exists():
                            self.progress_manager.update_stage_progress(input_file, 'html_original', 'completed')
                        
                        if self.generate_pdf:
                            pdf_original_path = self.get_output_path_with_structure("output/pdf", f"{file_stem}.pdf", input_file)
                            if Path(pdf_original_path).exists():
                                self.progress_manager.update_stage_progress(input_file, 'pdf_original', 'completed')
                        
                        if self.generate_docx:
                            docx_original_path = self.get_output_path_with_structure("output/docx", f"{file_stem}.docx", input_file)
                            if Path(docx_original_path).exists():
                                self.progress_manager.update_stage_progress(input_file, 'docx_original', 'completed')
                        
                        excel_trans_path = self.get_output_path_with_structure("output/excel", f"(译文) {file_stem}.xlsx", input_file)
                        if Path(excel_trans_path).exists():
                            self.progress_manager.update_stage_progress(input_file, 'translation', 'completed')
                            self.progress_manager.update_stage_progress(input_file, 'excel_translated', 'completed')
                        
                        html_trans_path = self.get_output_path_with_structure("output/html", f"(译文) {file_stem}.html", input_file)
                        if Path(html_trans_path).exists():
                            self.progress_manager.update_stage_progress(input_file, 'html_translated', 'completed')
                        
                        if self.generate_pdf:
                            pdf_trans_path = self.get_output_path_with_structure("output/pdf", f"(译文) {file_stem}.pdf", input_file)
                            if Path(pdf_trans_path).exists():
                                self.progress_manager.update_stage_progress(input_file, 'pdf_translated', 'completed')
                        
                        if self.generate_docx:
                            docx_trans_path = self.get_output_path_with_structure("output/docx", f"(译文) {file_stem}.docx", input_file)
                            if Path(docx_trans_path).exists():
                                self.progress_manager.update_stage_progress(input_file, 'docx_translated', 'completed')
                    
                    outline_issues = self._check_outline_quality(json_output_dir, file_name, prefix)
                    issues.extend(outline_issues)
                    cache_checked = True
                    
                except json.JSONDecodeError as e:
                    self.safe_logger.safe_print(f"{prefix} [错误] ❌ JSON格式错误: {str(e)[:100]}")
                    self.safe_logger.safe_print(f"{prefix} [降级] 将重新提取PDF（预计 2-10 分钟）")
                    df = None
                    cache_checked = False
                except ValueError as e:
                    self.safe_logger.safe_print(f"{prefix} [错误] ❌ 数据验证失败: {str(e)}")
                    self.safe_logger.safe_print(f"{prefix} [降级] 将重新提取PDF")
                    df = None
                    cache_checked = False
                except Exception as e:
                    self.safe_logger.safe_print(f"{prefix} [错误] ❌ 缓存加载失败: {type(e).__name__}: {str(e)[:50]}")
                    self.safe_logger.safe_print(f"{prefix} [降级] 将重新提取PDF")
                    df = None
                    cache_checked = False
            else:
                pass
            
            if df is None:
                if file_ext == '.docx':
                    if not self.docx_extractor:
                        raise ValueError("DOCX提取器未初始化")
                    self.safe_logger.safe_print(f"{prefix} [1/6] 提取DOCX文章...")
                    self.safe_logger.safe_print(f"{prefix} [开始] 🔧 DOCX提取器开始工作（无缓存）...")
                    current_extractor = self.docx_extractor
                else:
                    self.safe_logger.safe_print(f"{prefix} [1/6] 提取PDF文章...")
                    self.safe_logger.safe_print(f"{prefix} [开始] 🔧 PDF提取器开始工作（无缓存）...")
                    current_extractor = self.extractor
                
                relative_folder = self.input_structure.get(input_file.replace('\\', '/'), "")
                json_base_dir = Path(Constants.OUTPUT_JSON_DIR)
                if relative_folder:
                    json_output_dir = json_base_dir / relative_folder / file_name
                else:
                    json_output_dir = json_base_dir / file_name
                
                df = current_extractor.extract_to_dataframe(input_file, str(json_output_dir))
                self.safe_logger.safe_print(f"{prefix} ✅ 文章提取完成")
                
                if self.progress_manager:
                    self.progress_manager.update_stage_progress(input_file, 'extraction', 'completed')
            
            if df is None or len(df) == 0:
                raise ValueError("❌ 提取失败：未能从PDF/DOCX中提取到任何文章内容")
            
            
            if not cache_checked:
                outline_issues = self._check_outline_quality(json_output_dir, file_name, prefix)
                issues.extend(outline_issues)

            original_article_count = len(df)
            df, removed_ads = self._filter_advertisements(df, prefix)

            if removed_ads > 0:
                self.safe_logger.safe_print(f"{prefix} [广告过滤] ✅ 已移除 {removed_ads} 篇广告文章")
                self.safe_logger.safe_print(f"{prefix} [广告过滤] 剩余 {len(df)} 篇正文文章")
                issues.append(f"📌 已过滤 {removed_ads} 篇广告")

            batches_dir = json_output_dir / Constants.BATCHES_SUBDIR
            existing_table_caches = list(batches_dir.glob("tables_batch_*.json")) if batches_dir.exists() else []
            if not existing_table_caches and file_ext == '.pdf':
                self.safe_logger.safe_print(f"{prefix} [表格] 📊 未检测到表格缓存，开始提取表格...")
                try:
                    input_path = Path(input_file)
                    pdf_bytes = input_path.read_bytes()
                    table_extractor = TableExtractor()

                    import re as _re
                    all_tables = []
                    batch_files = sorted(batches_dir.glob("batch_*_pages_*.json")) if batches_dir.exists() else []
                    if batch_files:
                        for batch_file in batch_files:
                            m = _re.match(r'batch_(\d+)_pages_(\d+)_(\d+)', batch_file.stem)
                            if not m:
                                continue
                            idx = int(m.group(1))
                            page_start = int(m.group(2))
                            page_end = int(m.group(3))
                            tables_meta_path = batches_dir / f"tables_batch_{idx:02d}.json"
                            if tables_meta_path.exists():
                                with open(tables_meta_path, 'r', encoding='utf-8') as f:
                                    all_tables.extend(json.load(f))
                                continue
                            try:
                                batch_tables = table_extractor.extract_tables_from_pdf(pdf_bytes, (page_start, page_end), full_pdf=True)
                                with open(tables_meta_path, 'w', encoding='utf-8') as f:
                                    json.dump(batch_tables, f, ensure_ascii=False, indent=2)
                                all_tables.extend(batch_tables)
                            except Exception as e:
                                logger.warning(f"批次 {idx} 表格提取失败: {e}")
                    else:
                        import fitz
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        total_pages = len(doc)
                        doc.close()
                        all_tables = table_extractor.extract_tables_from_pdf(pdf_bytes, (1, total_pages), full_pdf=True)
                        tables_meta_path = batches_dir / "tables_batch_01.json"
                        batches_dir.mkdir(parents=True, exist_ok=True)
                        with open(tables_meta_path, 'w', encoding='utf-8') as f:
                            json.dump(all_tables, f, ensure_ascii=False, indent=2)

                    if all_tables:
                        self.safe_logger.safe_print(f"{prefix} [表格] 共提取 {len(all_tables)} 个表格，开始匹配注入...")
                        articles = df.to_dict('records')
                        all_tables = table_extractor.match_tables_to_articles(all_tables, articles)
                        articles = table_extractor.inject_tables_into_articles(articles, all_tables)
                        injected = sum(1 for t in all_tables if t.get('inserted'))
                        df = pd.DataFrame(articles)
                        self.safe_logger.safe_print(f"{prefix} [表格] ✅ 注入完成: {injected}/{len(all_tables)} 个表格已插入")
                        if injected > 0 and self.progress_manager:
                            self.progress_manager.update_stage_progress(input_file, 'html_original', 'pending')
                            self.progress_manager.update_stage_progress(input_file, 'html_translated', 'pending')
                    else:
                        self.safe_logger.safe_print(f"{prefix} [表格] 未检测到表格，跳过")
                except Exception as tbl_err:
                    self.safe_logger.safe_print(f"{prefix} [表格] ⚠️ 表格提取失败（不影响主流程）: {str(tbl_err)[:100]}")
            elif existing_table_caches:
                self.safe_logger.safe_print(f"{prefix} [表格] 检测到表格缓存，检查是否已注入...")
                sample_content = str(df.iloc[0].get('content', '') if len(df) > 0 else '')
                already_injected = any('| --- |' in str(row.get('content', '')) for _, row in df.iterrows())
                if not already_injected:
                    try:
                        table_extractor = TableExtractor()
                        all_tables = []
                        for cache_file in sorted(existing_table_caches):
                            with open(cache_file, 'r', encoding='utf-8') as f:
                                all_tables.extend(json.load(f))
                        if all_tables:
                            articles = df.to_dict('records')
                            all_tables = table_extractor.match_tables_to_articles(all_tables, articles)
                            articles = table_extractor.inject_tables_into_articles(articles, all_tables)
                            injected = sum(1 for t in all_tables if t.get('inserted'))
                            df = pd.DataFrame(articles)
                            self.safe_logger.safe_print(f"{prefix} [表格] ✅ 从缓存注入: {injected}/{len(all_tables)} 个表格")
                            if injected > 0 and self.progress_manager:
                                self.progress_manager.update_stage_progress(input_file, 'html_original', 'pending')
                                self.progress_manager.update_stage_progress(input_file, 'html_translated', 'pending')
                    except Exception as tbl_err:
                        self.safe_logger.safe_print(f"{prefix} [表格] ⚠️ 缓存注入失败: {str(tbl_err)[:100]}")

            
            self.safe_logger.safe_print(f"{prefix} [2/6] 并行处理：Excel + HTML + 翻译...")

            llm_responses_dir = Path(Constants.LOGS_LLM_RESPONSES_DIR) / file_name
            llm_responses_dir.mkdir(parents=True, exist_ok=True)

            if self.html_generator:
                self.html_generator.log_dir = llm_responses_dir
            if self.translator:
                self.translator.log_dir = llm_responses_dir

            parallel_results = self._parallel_stage_group_A(
                df, file_name, input_file, prefix, json_output_dir
            )
            
            excel_original = parallel_results['excel']['path'] if (parallel_results.get('excel') or {}).get('success') else None
            html_original = parallel_results['html']['path'] if (parallel_results.get('html') or {}).get('success') else None
            df_translated = parallel_results['translation']['df'] if (parallel_results.get('translation') or {}).get('success') else None

            if df_translated is None and self.generate_translation and self.progress_manager:
                cache_dir = str(json_output_dir)
                cached_count = self.progress_manager.count_translations(cache_dir)
                if cached_count >= len(df):
                    self.safe_logger.safe_print(f"{prefix} [翻译] 检测到完整翻译缓存（{cached_count}篇），从缓存恢复...")
                    recovery = self._translate_articles(df, file_name, input_file, prefix, json_output_dir)
                    if recovery.get('success') and recovery.get('df') is not None:
                        df_translated = recovery['df']
                        parallel_results['issues'] = [i for i in parallel_results['issues']
                                                      if 'translation' not in i.lower() and '翻译' not in i]
                        self.safe_logger.safe_print(f"{prefix} [翻译] ✅ 缓存恢复成功")

            if not excel_original and parallel_results.get('excel') and not (parallel_results.get('excel') or {}).get('success'):
                issues.append("⚠️ Excel原文生成失败")
            if not html_original and parallel_results.get('html') and not (parallel_results.get('html') or {}).get('success'):
                issues.append("⚠️ HTML原文生成失败")
            
            issues.extend(parallel_results['issues'])
            
            
            if self.progress_manager and html_original:
                if self.generate_pdf:
                    self.progress_manager.update_stage_progress(input_file, 'pdf_original', 'completed')
                if self.generate_docx:
                    self.progress_manager.update_stage_progress(input_file, 'docx_original', 'completed')
            
            
            html_translated = None
            parallel_results_b = None
            if df_translated is not None:
                    parallel_results_b = self._parallel_stage_group_B(
                        df_translated, file_name, input_file, prefix, json_output_dir
                    )
                    
                    html_translated = parallel_results_b['html']['path'] if (parallel_results_b.get('html') or {}).get('success') else None
                    
                    if parallel_results_b:
                        excel_trans_result = parallel_results_b.get('excel') or {}
                        if not excel_trans_result.get('success'):
                            issues.append("⚠️ Excel译文生成失败")
                        if not html_translated and parallel_results_b.get('html') and not (parallel_results_b.get('html') or {}).get('success'):
                            issues.append("⚠️ HTML译文生成失败")
                        
                        issues.extend(parallel_results_b['issues'])
            else:
                if self.generate_translation:
                    issues.append("⚠️ 翻译失败")
                else:
                    pass
            
            
            if self.progress_manager and (html_translated or not self.generate_translation):
                if self.generate_pdf:
                    self.progress_manager.update_stage_progress(input_file, 'pdf_translated', 'completed')
                if self.generate_docx:
                    self.progress_manager.update_stage_progress(input_file, 'docx_translated', 'completed')
            
            file_elapsed = time.time() - file_start_time
            
            result = {
                'file': input_file,
                'name': Path(input_file).name,
                'issues': issues,
                'elapsed': file_elapsed,
                'status': 'partial' if issues else 'success'
            }
            
            with self.lock:
                self.completed_count += 1

                if issues:
                    self.partial_files.append(result)

                    try:
                        JSONLWriter.append(
                            Constants.FAILED_FILES_LOG,
                            {
                                'name': result['name'],
                                'file': result['file'],
                                'issues': result['issues']
                            },
                            metadata={
                                'status': 'partial',
                                'file_type': 'pdf',
                                'elapsed_minutes': round(file_elapsed/60, 1)
                            }
                        )
                        if self.progress_manager:
                            self.progress_manager.mark_file_completed(input_file, success=True, issues=issues)
                    except Exception as log_error:
                        self.safe_logger.safe_print(f"{prefix} ⚠️  记录失败日志出错: {log_error}")

                    self.safe_logger.safe_print(f"\n{prefix} ⚠️  完成（有问题）- 耗时: {file_elapsed/60:.1f}分钟")
                    for issue in issues:
                        self.safe_logger.safe_print(f"{prefix}    • {issue}")
                else:
                    self.success_files.append(result)
                    self.safe_logger.safe_print(f"\n{prefix} ✅ 完全成功 - 耗时: {file_elapsed/60:.1f}分钟")

                    if self.progress_manager:
                        try:
                            self.progress_manager.mark_file_completed(input_file, success=True)
                        except Exception as save_error:
                            self.safe_logger.safe_print(f"{prefix} ⚠️  保存进度失败: {save_error}")
                
                self.safe_logger.update_progress(file_idx, 'completed', Path(input_file).name)
                
                self.safe_logger.print_progress_panel(self.completed_count, total_files)
            
            return result
            
        except Exception as e:
            file_elapsed = time.time() - file_start_time
            error_msg = str(e)
            
            result = {
                'file': input_file,
                'name': Path(input_file).name,
                'error': error_msg,
                'elapsed': file_elapsed,
                'status': 'failed'
            }
            
            with self.lock:
                self.completed_count += 1
                self.failed_files.append(result)

                try:
                    JSONLWriter.append(
                        Constants.FAILED_FILES_LOG,
                        {
                            'name': result['name'],
                            'file': result['file'],
                            'error': result['error']
                        },
                        metadata={
                            'status': 'failed',
                            'file_type': 'pdf',
                            'elapsed_minutes': round(file_elapsed/60, 1)
                        }
                    )
                    if self.progress_manager:
                        self.progress_manager.mark_file_completed(input_file, success=False, error=error_msg)
                except Exception as log_error:
                    self.safe_logger.safe_print(f"{prefix} ⚠️  记录失败日志出错: {log_error}")

                self.safe_logger.safe_print(f"\n{prefix} ❌ 处理失败 - 耗时: {file_elapsed/60:.1f}分钟")
                self.safe_logger.safe_print(f"{prefix}    错误: {error_msg[:100]}")
                
                self.safe_logger.update_progress(file_idx, 'failed', Path(input_file).name)
                self.safe_logger.print_progress_panel(self.completed_count, total_files)
            
            return result
    
    def process_files(self, input_files: List[str], max_workers: int) -> Tuple[List, List, List]:
        total_files = len(input_files)
        
        self.safe_logger.safe_print(f"\n{'=' * 80}")
        self.safe_logger.safe_print(f"🚀 启动并发处理模式")
        self.safe_logger.safe_print(f"{'=' * 80}")
        self.safe_logger.safe_print(f"   总文件数: {total_files} 个")
        self.safe_logger.safe_print(f"   最大并发: {max_workers} 个文件同时处理")
        self.safe_logger.safe_print(f"   开始时间: {datetime.now().strftime('%H:%M:%S')}")
        self.safe_logger.safe_print(f"{'=' * 80}\n")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, input_file in enumerate(input_files, 1):
                future = executor.submit(self.process_single_file, input_file, idx, total_files)
                futures[future] = (idx, input_file)
                
                self.safe_logger.update_progress(idx, 'queued', Path(input_file).name)
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=600)
                except TimeoutError:
                    idx, input_file = futures[future]
                    logger.error(f"处理文件 {input_file} 超时（600秒），强制跳过")
                    future.cancel()
                    continue
                except Exception as e:
                    idx, input_file = futures[future]
                    logger.error(f"处理文件 {input_file} 时发生未捕获的异常: {e}")

                    error_msg = f"未捕获的异常: {type(e).__name__}: {str(e)}"
                    failed_result = {
                        'file': input_file,
                        'name': Path(input_file).name,
                        'error': error_msg,
                        'elapsed': 0,
                        'status': 'failed'
                    }

                    with self.lock:
                        self.completed_count += 1
                        self.failed_files.append(failed_result)

                        try:
                            JSONLWriter.append(
                                Constants.FAILED_FILES_LOG,
                                {
                                    'name': failed_result['name'],
                                    'file': failed_result['file'],
                                    'error': failed_result['error']
                                },
                                metadata={
                                    'status': 'failed',
                                    'file_type': 'pdf',
                                    'context': 'timeout_in_process_files'
                                }
                            )
                        except Exception as log_error:
                            logger.error(f"记录失败日志出错: {log_error}")

                        if self.progress_manager:
                            try:
                                self.progress_manager.mark_file_completed(input_file, success=False, error=error_msg)
                            except Exception as save_error:
                                logger.error(f"保存进度失败: {save_error}")

                    self.safe_logger.update_progress(idx, 'failed', Path(input_file).name)
                    self.safe_logger.print_progress_panel(self.completed_count, total_files)
        
        processed_count = len(self.success_files) + len(self.partial_files) + len(self.failed_files)
        if processed_count != total_files:
            warning_msg = (
                f"\n{'='*80}\n"
                f"⚠️  警告：文件数量不匹配！\n"
                f"{'='*80}\n"
                f"预期处理: {total_files} 个文件\n"
                f"实际处理: {processed_count} 个文件\n"
            )
            self.safe_logger.safe_print(warning_msg)

        if self.progress_manager and self.progress_manager.progress_data:
            summary = self.progress_manager.get_summary()
            saved_completed = summary.get('completed_files', 0)
            saved_incomplete = summary.get('incomplete_files', 0)
            saved_failed = summary.get('failed_files', 0)
            saved_total = saved_completed + saved_incomplete + saved_failed

            if saved_total != processed_count:
                delta = processed_count - saved_total
                if delta > 0:
                    detail_line = f"未保存: {delta} 个文件的进度\n\n⚠️  这些文件的进度未保存到断点文件！\n⚠️  下次恢复时将重新处理这些文件！\n"
                else:
                    detail_line = f"断点记录多出 {abs(delta)} 条（可能来自历史会话或并发保存），建议稍后再次保存以同步。\n\n"
                warning_msg = (
                    f"\n{'='*80}\n"
                    f"⚠️  警告：断点文件记录不一致！\n"
                    f"{'='*80}\n"
                    f"内存中处理: {processed_count} 个文件\n"
                    f"断点中记录: {saved_total} 个文件\n"
                    f"  - 完全成功: {saved_completed}\n"
                    f"  - 未完成: {saved_incomplete}\n"
                    f"  - 失败: {saved_failed}\n"
                    f"{detail_line}"
                    f"{'='*80}\n"
                )
                self.safe_logger.safe_print(warning_msg)
        
        return self.success_files, self.partial_files, self.failed_files
    
    def _check_outline_quality(self, json_output_dir, file_name, prefix):
        issues = []
        
        outline_file = Path(json_output_dir) / "outline" / "journal_outline.json"
        if not outline_file.exists():
            issues.append("⚠️ 缺少期刊大纲文件（journal_outline.json）")
            return issues
        
        try:
            with open(outline_file, 'r', encoding='utf-8') as f:
                outline_data = json.load(f)
            
            journal_name = outline_data.get('journal_name', '')
            content_summary = outline_data.get('content_summary', '')
            journal_type = outline_data.get('journal_type', 'unknown')
            
            if not journal_name or not journal_name.strip():
                issues.append("❌ 大纲提取失败：期刊名称为空")
                self.safe_logger.safe_print(f"{prefix} [检查] ❌ 期刊名称为空")
            
            error_markers = [
                'Outline extraction failed',
                'Outline validation failed',
                'No context summary available',
                'Process each batch independently',
                'returned empty content'
            ]
            
            if any(marker in content_summary for marker in error_markers):
                issues.append(f"⚠️ 大纲提取失败：内容摘要包含错误标记")
                self.safe_logger.safe_print(f"{prefix} [检查] ⚠️ 内容摘要包含错误标记")
            
            if journal_type == 'unknown':
                issues.append("⚠️ 期刊类型未识别（unknown）")
                self.safe_logger.safe_print(f"{prefix} [检查] ⚠️ 期刊类型未识别")
            
            if issues:
                self.safe_logger.safe_print(f"{prefix} [检查] 大纲质量问题:")
                for issue in issues:
                    self.safe_logger.safe_print(f"{prefix}         {issue}")
            else:
                self.safe_logger.safe_print(f"{prefix} [检查] ✅ 大纲质量良好: {journal_name}")
        
        except Exception as e:
            error_msg = f"⚠️ 大纲文件读取失败: {str(e)[:50]}"
            issues.append(error_msg)
            self.safe_logger.safe_print(f"{prefix} [检查] {error_msg}")
        
        return issues

    def _filter_advertisements(self, df, prefix):
        ad_keywords = UserConfig.AD_KEYWORDS
        if not ad_keywords:
            self.safe_logger.safe_print(f"{prefix} [广告过滤] 未配置AD_KEYWORDS，仅使用not_in_toc字段")
        df_filtered, count, removed_titles = _filter_ads_from_df(df, ad_keywords)
        if count:
            self.safe_logger.safe_print(f"{prefix} [广告过滤] 检测到 {count} 篇广告:")
            for i, (title, reason) in enumerate(removed_titles[:5], 1):
                self.safe_logger.safe_print(f"{prefix}              {i}. {title}... ({reason})")
            if len(removed_titles) > 5:
                self.safe_logger.safe_print(f"{prefix}              ... 还有 {len(removed_titles) - 5} 篇")
        else:
            self.safe_logger.safe_print(f"{prefix} [广告过滤] 未检测到广告文章")
        return df_filtered, count

    
    def _generate_excel(self, df, file_name, input_file, prefix, *, is_translated: bool):
        try:
            if is_translated:
                excel_filename = f"(译文) {file_name}.xlsx"
                stage = 'excel_translated'
                label = 'Excel译文'
                err_prefix = '译文Excel'
            else:
                excel_filename = f"{file_name}.xlsx"
                stage = 'excel_original'
                label = 'Excel原文'
                err_prefix = 'Excel'
            excel_output_path = self.get_output_path_with_structure("output/excel", excel_filename, input_file)

            file_progress = self.progress_manager.get_file_progress(input_file) if self.progress_manager else None
            if Path(excel_output_path).exists() and file_progress and self.progress_manager.is_stage_completed(input_file, stage):
                self.safe_logger.safe_print(f"{prefix} [{label}] 已存在，跳过")
                return {'success': True, 'path': excel_output_path, 'error': None, 'skipped': True}

            self.safe_logger.safe_print(f"{prefix} [{label}] 开始生成...")
            excel_path = self.excel_generator.generate_excel_with_path(df, excel_output_path, is_translated=is_translated)
            self.safe_logger.safe_print(f"{prefix} [{label}] ✅ 完成")

            if self.progress_manager:
                self.progress_manager.update_stage_progress(input_file, stage, 'completed')

            return {'success': True, 'path': excel_path, 'error': None, 'skipped': False}

        except Exception as e:
            error_msg = f"{err_prefix}生成失败: {str(e)}"
            self.safe_logger.safe_print(f"{prefix} [{label}] ❌ {str(e)[:50]}")
            return {'success': False, 'path': None, 'error': error_msg, 'skipped': False}
    
    def _generate_html(self, df, file_name, input_file, prefix, json_output_dir, is_translated: bool):
        label = "HTML译文" if is_translated else "HTML原文"
        stage = "html_translated" if is_translated else "html_original"
        filename_prefix = "(译文) " if is_translated else ""
        fragments_subdir = "html_fragments_translated" if is_translated else "html_fragments"
        generate_pdf_docx = True if is_translated else (self.output_language_mode != "translated_only")

        try:
            html_filename = f"{filename_prefix}{file_name}.html"
            html_output_path = self.get_output_path_with_structure("output/html", html_filename, input_file)

            file_progress = self.progress_manager.get_file_progress(input_file) if self.progress_manager else None
            if Path(html_output_path).exists() and file_progress and self.progress_manager.is_stage_completed(input_file, stage):
                html_mtime = Path(html_output_path).stat().st_mtime
                fragments_dir = Path(json_output_dir) / '.cache' / fragments_subdir
                stale = False
                if fragments_dir.exists():
                    for frag in fragments_dir.glob('article_*.json'):
                        if frag.stat().st_mtime > html_mtime + 5:
                            stale = True
                            break
                if not stale:
                    self.safe_logger.safe_print(f"{prefix} [{label}] 已存在，跳过")
                    return {'success': True, 'path': html_output_path, 'error': None, 'skipped': True}
                else:
                    self.safe_logger.safe_print(f"{prefix} [{label}] 检测到更新的fragment缓存，重新生成...")

            self.safe_logger.safe_print(f"{prefix} [{label}] 开始生成...")
            html_path = self.html_generator.generate_html(
                df,
                pdf_name=file_name,
                output_path=html_output_path,
                is_translated=is_translated,
                cache_dir=str(json_output_dir),
                progress_manager=self.progress_manager,
                generate_pdf_docx=generate_pdf_docx
            )

            placeholder_count = 0
            if html_path:
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                        if '（此文章的HTML生成失败' in html_content:
                            placeholder_count = html_content.count('（此文章的HTML生成失败')
                except Exception:
                    pass

            if placeholder_count > 0:
                self.safe_logger.safe_print(f"{prefix} [{label}] ⚠️  完成但{placeholder_count}篇失败")
            else:
                self.safe_logger.safe_print(f"{prefix} [{label}] ✅ 完成")

            if self.progress_manager:
                self.progress_manager.update_stage_progress(input_file, stage, 'completed')

            return {'success': True, 'path': html_path, 'error': None, 'skipped': False, 'placeholder_count': placeholder_count}

        except Exception as e:
            error_msg = f"{'译文' if is_translated else ''}HTML生成失败: {str(e)}"
            self.safe_logger.safe_print(f"{prefix} [{label}] ❌ {str(e)[:50]}")
            return {'success': False, 'path': None, 'error': error_msg, 'skipped': False}

    def _translate_articles(self, df, file_name, input_file, prefix, json_output_dir):
        try:
            if not self.generate_translation or not self.translator:
                return {'success': True, 'df': None, 'error': None, 'skipped': True}

            file_signature = self._compute_file_signature(input_file)
            
            excel_trans_filename = f"(译文) {file_name}.xlsx"
            excel_trans_output_path = self.get_output_path_with_structure("output/excel", excel_trans_filename, input_file)
            
            file_progress = self.progress_manager.get_file_progress(input_file) if self.progress_manager else None
            need_retranslate = False
            df_translated = None
            if Path(excel_trans_output_path).exists() and file_progress and self.progress_manager.is_stage_completed(input_file, 'translation'):
                self.safe_logger.safe_print(f"{prefix} [翻译] 检测到翻译已完成，从Excel译文加载...")
                try:
                    df_translated = pd.read_excel(excel_trans_output_path)
                    self.safe_logger.safe_print(f"{prefix} [翻译] ✅ 已从Excel译文加载 {len(df_translated)} 篇文章")
                    invalid_count = 0
                    if df_translated is not None and 'content_zh' in df_translated.columns:
                        for _, row in df_translated.iterrows():
                            content_zh = str(row.get('content_zh', ''))
                            if content_zh.startswith('[翻译失败:') or content_zh.startswith('[验证失败') or content_zh.startswith('[需人工检查'):
                                invalid_count += 1
                    if invalid_count > 0:
                        self.safe_logger.safe_print(f"{prefix} [翻译] ⚠️  Excel译文中发现 {invalid_count} 篇占位/失败条目，触发差量重译...")
                        need_retranslate = True
                        df_translated = None
                    else:
                        return {'success': True, 'df': df_translated, 'error': None, 'skipped': True}
                except Exception as e:
                    self.safe_logger.safe_print(f"{prefix} [翻译] ⚠️  恢复失败，重新翻译")
                    need_retranslate = True
            
            if df_translated is None:
                self.safe_logger.safe_print(f"{prefix} [翻译] 开始翻译...")
            
            outline_file = Path(json_output_dir) / "outline" / "journal_outline.json"
            if outline_file.exists():
                try:
                    with open(outline_file, 'r', encoding='utf-8') as f:
                        journal_outline = json.load(f)
                    self.translator.set_journal_outline(journal_outline)
                except Exception:
                    pass
            
            if df_translated is None:
                df_translated = self.translator.translate_dataframe(
                    df,
                    cache_dir=str(json_output_dir),
                    progress_manager=self.progress_manager,
                    file_signature=file_signature,
                    source_file=input_file
                )
            
            translation_failed_count = 0
            if df_translated is not None and 'content_zh' in df_translated.columns:
                for idx, row in df_translated.iterrows():
                    content_zh = str(row.get('content_zh', ''))
                    if content_zh.startswith('[翻译失败:') or content_zh.startswith('[验证失败') or content_zh.startswith('[需人工检查'):
                        translation_failed_count += 1
            
            if translation_failed_count > 0:
                error_msg = f"翻译失败 {translation_failed_count}/{len(df)} 篇，已跳过译文生成"
                self.safe_logger.safe_print(f"{prefix} [翻译] ⚠️  {error_msg}")
                
                if self.progress_manager:
                    self.progress_manager.update_stage_progress(input_file, 'translation', 'failed')
                
                return {'success': False, 'df': None, 'error': error_msg, 'skipped': False}
            else:
                self.safe_logger.safe_print(f"{prefix} [翻译] ✅ 完成（{len(df)}/{len(df)} 篇成功）")

            try:
                self.translator.translate_cover_images(file_name)
            except Exception as e:
                self.safe_logger.safe_print(f"{prefix} [翻译] ⚠️  封面图翻译失败: {str(e)[:50]}")

            if self.progress_manager:
                self.progress_manager.update_stage_progress(input_file, 'translation', 'completed')

            return {'success': True, 'df': df_translated, 'error': None, 'skipped': False}
        
        except Exception as e:
            error_msg = f"翻译失败: {str(e)}"
            self.safe_logger.safe_print(f"{prefix} [翻译] ❌ {str(e)[:50]}")
            return {'success': False, 'df': None, 'error': error_msg, 'skipped': False}

    @staticmethod
    def _compute_file_signature(input_file: str) -> str:
        try:
            path = Path(input_file)
            if not path.exists():
                return None
            stat = path.stat()
            raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime}"
            return hashlib.sha1(raw.encode('utf-8')).hexdigest()
        except Exception:
            return None
    


    def _parallel_stage_group_A(self, df, file_name, input_file, prefix, json_output_dir):
        self.safe_logger.safe_print(f"{prefix} [并行] 🚀 启动并行A组（Excel原文 + HTML原文 + 翻译）")

        html_concurrent = UserConfig.HTML_CONCURRENT_REQUESTS if self.html_generator else 0
        translation_concurrent = UserConfig.TRANSLATION_MAX_WORKERS if (self.generate_translation and self.translator) else 0
        total_concurrent = 1 + html_concurrent + translation_concurrent

        self.safe_logger.safe_print(f"{prefix} [并发监控] 预计总并发数: {total_concurrent}")
        self.safe_logger.safe_print(f"{prefix} [并发监控]   ├─ Excel: 1 线程")
        self.safe_logger.safe_print(f"{prefix} [并发监控]   ├─ HTML: {html_concurrent} 线程")
        self.safe_logger.safe_print(f"{prefix} [并发监控]   └─ 翻译: {translation_concurrent} 线程")

        if total_concurrent > 8:
            self.safe_logger.safe_print(f"{prefix} [并发监控] ⚠️ 总并发数较高（{total_concurrent}），注意资源使用")

        start_time = time.time()
        
        results = {
            'excel': None,
            'html': None,
            'translation': None,
            'issues': []
        }
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            self.safe_logger.safe_print(f"{prefix} [并行]    ├─ 线程1: Excel原文")
            futures['excel'] = executor.submit(
                self._generate_excel,
                df, file_name, input_file, prefix, is_translated=False
            )

            if self.output_language_mode != "translated_only":
                self.safe_logger.safe_print(f"{prefix} [并行]    ├─ 线程2: HTML原文")
                futures['html'] = executor.submit(
                    self._generate_html,
                    df, file_name, input_file, prefix, json_output_dir, is_translated=False
                )
            else:
                self.safe_logger.safe_print(f"{prefix} [并行]    ├─ 线程2: HTML原文（仅译文模式，跳过）")
                results['html'] = {'success': True, 'path': None, 'error': None, 'skipped': True, 'placeholder_count': 0}

            if self.generate_translation and self.translator:
                self.safe_logger.safe_print(f"{prefix} [并行]    └─ 线程3: 翻译")
                futures['translation'] = executor.submit(
                    self._translate_articles,
                    df, file_name, input_file, prefix, json_output_dir
                )
            
            self.safe_logger.flush_buffer()

            try:
                done, not_done = wait(futures.values(), timeout=600)

                if not_done:
                    timeout_tasks = [name for name, fut in futures.items() if fut in not_done]
                    error_msg = f"以下任务超时（>600秒）: {', '.join(timeout_tasks)}"
                    self.safe_logger.safe_print(f"{prefix} [并行] ⏰ {error_msg}")
                    results['issues'].append(error_msg)

                    for task_name in timeout_tasks:
                        results[task_name] = {'success': False, 'path': None, 'error': f'{task_name}超时'}

                for task_name, future in futures.items():
                    if future in done:
                        try:
                            result = future.result(timeout=0)
                            results[task_name] = result

                            if not result['success'] and result['error']:
                                results['issues'].append(result['error'])

                            if task_name == 'html' and result.get('placeholder_count', 0) > 0:
                                results['issues'].append(f"HTML生成有{result['placeholder_count']}篇文章失败")
                        except Exception as e:
                            error_msg = f"{task_name}任务异常: {str(e)}"
                            self.safe_logger.safe_print(f"{prefix} [并行] ❌ {error_msg}")
                            results['issues'].append(error_msg)
                            results[task_name] = {'success': False, 'path': None, 'error': error_msg}

            except Exception as wait_error:
                error_msg = f"并发等待异常: {str(wait_error)}"
                self.safe_logger.safe_print(f"{prefix} [并行] ❌ {error_msg}")
                results['issues'].append(error_msg)

        elapsed = time.time() - start_time
        self.safe_logger.safe_print(f"{prefix} [并行] ✅ A组完成（耗时 {elapsed:.1f} 秒）")
        self.safe_logger.flush_buffer()
        
        return results
    
    def _parallel_stage_group_B(self, df_translated, file_name, input_file, prefix, json_output_dir):
        self.safe_logger.safe_print(f"{prefix} [并行] 🚀 启动并行B组（Excel译文 + HTML译文）")
        start_time = time.time()
        
        results = {
            'excel': None,
            'html': None,
            'issues': []
        }
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            self.safe_logger.safe_print(f"{prefix} [并行]    ├─ 线程1: Excel译文")
            futures['excel'] = executor.submit(
                self._generate_excel,
                df_translated, file_name, input_file, prefix, is_translated=True
            )
            
            self.safe_logger.safe_print(f"{prefix} [并行]    └─ 线程2: HTML译文")
            futures['html'] = executor.submit(
                self._generate_html,
                df_translated, file_name, input_file, prefix, json_output_dir, is_translated=True
            )

            self.safe_logger.flush_buffer()

            try:
                done, not_done = wait(futures.values(), timeout=600)

                if not_done:
                    timeout_tasks = [name for name, fut in futures.items() if fut in not_done]
                    error_msg = f"以下任务超时（>600秒）: {', '.join(timeout_tasks)}"
                    self.safe_logger.safe_print(f"{prefix} [并行] ⏰ {error_msg}")
                    results['issues'].append(error_msg)

                    for task_name in timeout_tasks:
                        results[task_name] = {'success': False, 'path': None, 'error': f'{task_name}超时'}

                for task_name, future in futures.items():
                    if future in done:
                        try:
                            result = future.result(timeout=0)
                            results[task_name] = result

                            if not result['success'] and result['error']:
                                results['issues'].append(result['error'])

                            if task_name == 'html' and result.get('placeholder_count', 0) > 0:
                                results['issues'].append(f"译文HTML生成有{result['placeholder_count']}篇文章失败")
                        except Exception as e:
                            error_msg = f"{task_name}任务异常: {str(e)}"
                            self.safe_logger.safe_print(f"{prefix} [并行] ❌ {error_msg}")
                            results['issues'].append(error_msg)
                            results[task_name] = {'success': False, 'path': None, 'error': error_msg}

            except Exception as wait_error:
                error_msg = f"并发等待异常: {str(wait_error)}"
                self.safe_logger.safe_print(f"{prefix} [并行] ❌ {error_msg}")
                results['issues'].append(error_msg)

        elapsed = time.time() - start_time
        self.safe_logger.safe_print(f"{prefix} [并行] ✅ B组完成（耗时 {elapsed:.1f} 秒）")
        self.safe_logger.flush_buffer()
        
        return results

class BoundedThreadPoolExecutor:

    def __init__(self, max_workers: int, max_queue_size: int, name: str = "BoundedExecutor"):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.name = name

        self._semaphore = Semaphore(max_workers + max_queue_size)

        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=name)

        self._stats = {
            'submitted': 0,
            'completed': 0,
            'failed': 0,
            'blocked_count': 0,
        }
        self._stats_lock = Lock()

        logger.debug(f"[{name}] 初始化: max_workers={max_workers}, max_queue_size={max_queue_size}")

    def _wrapper(self, fn: Callable, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)

            with self._stats_lock:
                self._stats['completed'] += 1

            return result

        except Exception as e:
            with self._stats_lock:
                self._stats['failed'] += 1

            logger.error(f"[{self.name}] 任务执行失败: {e}")
            raise

        finally:
            self._semaphore.release()

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        acquired = self._semaphore.acquire(blocking=True, timeout=None)

        if not acquired:
            raise RuntimeError(f"[{self.name}] 无法获取信号量槽位")

        with self._stats_lock:
            self._stats['submitted'] += 1

            queue_free_slots = self._semaphore._value
            if queue_free_slots <= 5:
                self._stats['blocked_count'] += 1

        future = self._executor.submit(self._wrapper, fn, *args, **kwargs)

        return future

    def shutdown(self, wait: bool = True):
        logger.debug(f"[{self.name}] 关闭线程池: wait={wait}")
        self._executor.shutdown(wait=wait)

    def get_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            return self._stats.copy()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)
        return False

class GlobalResourceManager:

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        self.global_api_concurrency = config['global_api_concurrency']
        self.api_semaphore = Semaphore(self.global_api_concurrency)

        self.file_min_api_guarantee = config['file_min_api_guarantee']

        self.file_semaphores: Dict[str, Semaphore] = {}
        self.file_semaphores_lock = Lock()

        self._stats = {
            'api_calls_total': 0,
            'api_calls_active': 0,
            'api_calls_completed': 0,
            'api_wait_count': 0,
        }
        self._stats_lock = Lock()

        logger.info(f"[GlobalResourceManager] 初始化: "
                   f"global_api={self.global_api_concurrency}, "
                   f"file_min_guarantee={self.file_min_api_guarantee}")

    def register_file(self, file_id: str):
        with self.file_semaphores_lock:
            if file_id not in self.file_semaphores:
                self.file_semaphores[file_id] = Semaphore(self.file_min_api_guarantee)
                logger.debug(f"[GlobalResourceManager] 注册文件: {file_id}, "
                           f"保障槽位: {self.file_min_api_guarantee}")

    def unregister_file(self, file_id: str):
        with self.file_semaphores_lock:
            if file_id in self.file_semaphores:
                del self.file_semaphores[file_id]
                logger.debug(f"[GlobalResourceManager] 注销文件: {file_id}")

    @contextmanager
    def acquire_api_slot(self, file_id: Optional[str] = None):
        start_time = time.time()

        used_file_slot = False
        if file_id:
            with self.file_semaphores_lock:
                file_sem = self.file_semaphores.get(file_id)

            if file_sem:
                used_file_slot = file_sem.acquire(blocking=False)
                if used_file_slot:
                    logger.debug(f"[GlobalResourceManager] 使用文件专属槽位: {file_id}")

        if not used_file_slot:
            if self.api_semaphore._value == 0:
                with self._stats_lock:
                    self._stats['api_wait_count'] += 1
                logger.debug(f"[GlobalResourceManager] API 槽位已满，等待中...")

            self.api_semaphore.acquire()

        with self._stats_lock:
            self._stats['api_calls_total'] += 1
            self._stats['api_calls_active'] += 1

        try:
            yield

            with self._stats_lock:
                self._stats['api_calls_completed'] += 1

        finally:
            if used_file_slot:
                if file_id:
                    with self.file_semaphores_lock:
                        file_sem = self.file_semaphores.get(file_id)
                    if file_sem:
                        file_sem.release()
                    else:
                        self.api_semaphore.release()
                else:
                    self.api_semaphore.release()
            else:
                self.api_semaphore.release()

            with self._stats_lock:
                self._stats['api_calls_active'] -= 1

            elapsed = time.time() - start_time
            if elapsed > 30:
                logger.warning(f"[GlobalResourceManager] API 调用耗时过长: {elapsed:.2f}s")

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = self._stats.copy()

        stats['api_available_slots'] = self.api_semaphore._value
        stats['active_files'] = len(self.file_semaphores)

        return stats

class SequentialFileProcessor:

    ALL_STAGES = [
        'extraction',
        'image_processing',
        'excel_original',
        'html_original',
        'pdf_original',
        'docx_original',
        'translation',
        'excel_translated',
        'html_translated',
        'pdf_translated',
        'docx_translated',
    ]

    def __init__(
        self,
        extractor,
        excel_generator,
        html_generator,
        pdf_generator,
        docx_generator,
        translator,
        input_structure: Dict,
        generate_pdf: bool,
        generate_docx: bool,
        generate_translation: bool,
        output_language_mode: str = "both",
        docx_extractor=None,
        progress_manager=None,
        config: Optional[Dict[str, Any]] = None
    ):
        if config is None:
            config = UserConfig.SEQUENTIAL_EXECUTOR_CONFIG

        self.config = config
        self.progress_manager = progress_manager

        self.extractor = extractor
        self.docx_extractor = docx_extractor
        self.excel_generator = excel_generator
        self.html_generator = html_generator
        self.pdf_generator = pdf_generator
        self.docx_generator = docx_generator
        self.translator = translator
        self.input_structure = input_structure
        self.generate_pdf = generate_pdf
        self.generate_docx = generate_docx
        self.generate_translation = generate_translation
        self.output_language_mode = output_language_mode

        self.resource_manager = GlobalResourceManager(config)

        max_files = config['max_concurrent_files']
        queue_size = config['global_task_queue_size']
        self.file_executor = BoundedThreadPoolExecutor(
            max_workers=max_files,
            max_queue_size=queue_size,
            name="FileExecutor"
        )

        self._stats = {
            'files_total': 0,
            'files_completed': 0,
            'files_failed': 0,
            'start_time': None,
            'end_time': None,
        }
        self._stats_lock = Lock()

        logger.info(f"[SequentialFileProcessor] 初始化完成")
        logger.info(f"  - 文件并发数: {max_files}")
        logger.info(f"  - 全局 API 并发: {config['global_api_concurrency']}")
        logger.info(f"  - 每文件 worker 数: {config['per_file_max_workers']}")
        logger.info(f"  - 任务队列大小: {queue_size}")

    def process_files(self, input_files: List[str], max_workers: int = None) -> tuple:
        logger.info(f"[SequentialFileProcessor] 开始处理 {len(input_files)} 个文件")

        input_paths = [Path(f) for f in input_files]

        with self._stats_lock:
            self._stats['files_total'] = len(input_paths)
            self._stats['start_time'] = datetime.now()

        success_files = []
        partial_files = []
        failed_files = []

        futures = {}
        for idx, input_file in enumerate(input_paths, start=1):
            file_id = input_file.stem

            self.resource_manager.register_file(file_id)

            future = self.file_executor.submit(
                self._process_single_file,
                input_file,
                idx,
                len(input_paths)
            )
            futures[future] = (idx, input_file)

        from concurrent.futures import as_completed
        for future in as_completed(futures):
            idx, input_file = futures[future]
            file_id = input_file.stem
            file_path_str = str(input_file)

            try:
                result = future.result()

                if result['success']:
                    if result.get('has_issues', False):
                        partial_files.append(file_path_str)
                        logger.info(f"[文件 {idx}/{len(input_paths)}] 部分完成（有问题）: {input_file.name}")
                    else:
                        success_files.append(file_path_str)
                        logger.info(f"[文件 {idx}/{len(input_paths)}] 完成: {input_file.name}")

                    with self._stats_lock:
                        self._stats['files_completed'] += 1
                else:
                    failed_files.append(file_path_str)
                    logger.error(f"[文件 {idx}/{len(input_paths)}] 失败: {input_file.name} - {result.get('error', 'Unknown')}")

                    with self._stats_lock:
                        self._stats['files_failed'] += 1

            except Exception as e:
                logger.error(f"[文件 {idx}/{len(input_paths)}] 异常: {input_file.name} - {e}")
                failed_files.append(file_path_str)

                with self._stats_lock:
                    self._stats['files_failed'] += 1

            finally:
                self.resource_manager.unregister_file(file_id)

        with self._stats_lock:
            self._stats['end_time'] = datetime.now()

        logger.info(f"[SequentialFileProcessor] 处理完成")
        logger.info(f"  - 成功: {len(success_files)}")
        logger.info(f"  - 部分成功: {len(partial_files)}")
        logger.info(f"  - 失败: {len(failed_files)}")

        return (success_files, partial_files, failed_files)

    def _process_single_file(
        self,
        input_file: Path,
        file_idx: int,
        total_files: int
    ) -> Dict[str, Any]:
        file_id = input_file.stem
        file_name = input_file.name
        result = {'success': False, 'has_issues': False, 'stages_completed': [], 'error': None}

        logger.info(f"[{file_id}] 开始处理（{file_idx}/{total_files}）")

        try:
            file_progress = None
            if self.progress_manager:
                file_progress = self.progress_manager.get_file_progress(str(input_file))

            for stage in self.ALL_STAGES:
                if file_progress:
                    stage_status = file_progress.get('stages', {}).get(stage, 'pending')
                    if stage_status == 'completed':
                        logger.debug(f"[{file_id}] Stage {stage}: 已完成，跳过")
                        result['stages_completed'].append(stage)
                        continue

                if self._check_cache_and_skip(input_file, stage):
                    if self.progress_manager:
                        self.progress_manager.update_stage_progress(
                            str(input_file), stage, 'completed'
                        )
                    result['stages_completed'].append(stage)
                    logger.info(f"[{file_id}] Stage {stage}: 缓存命中，跳过")
                    continue

                logger.info(f"[{file_id}] Stage {stage}: 开始")

                if self.progress_manager:
                    self.progress_manager.update_stage_progress(
                        str(input_file), stage, 'in_progress'
                    )

                try:
                    self._execute_stage_with_retry(input_file, stage)

                    if self.progress_manager:
                        self.progress_manager.update_stage_progress(
                            str(input_file), stage, 'completed'
                        )

                    result['stages_completed'].append(stage)
                    logger.info(f"[{file_id}] Stage {stage}: 完成")

                except Exception as e:
                    logger.error(f"[{file_id}] Stage {stage}: 失败 - {e}")

                    if self.progress_manager:
                        self.progress_manager.update_stage_progress(
                            str(input_file), stage, 'failed'
                        )

                    result['has_issues'] = True
                    logger.warning(f"[{file_id}] Stage {stage}: 跳过后续相关阶段")

            result['success'] = True
            logger.info(f"[{file_id}] 所有阶段完成")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"[{file_id}] 处理失败: {e}")

        return result

    def _check_cache_and_skip(self, input_file: Path, stage: str) -> bool:
        file_name = input_file.stem
        json_base_dir = Path(Constants.OUTPUT_JSON_DIR) / file_name

        if stage == 'extraction':
            outline_path = json_base_dir / Constants.OUTLINE_SUBDIR / "journal_outline.json"
            if outline_path.exists():
                logger.debug(f"[{file_name}] L1 Cache 命中: {outline_path}")
                return True

        if stage == 'extraction':
            articles_dir = json_base_dir / Constants.ARTICLES_SUBDIR
            if articles_dir.exists():
                for json_file in articles_dir.glob("final_articles_*.json"):
                    logger.debug(f"[{file_name}] L2 Cache 命中: {json_file.name}")
                    return True

        if stage == 'image_processing':
            extraction_completed = file_progress and file_progress.get('stages', {}).get('extraction') == 'completed'
            if extraction_completed:
                logger.debug(f"[{file_name}] 图片处理已在extraction阶段完成，自动跳过")
                return True
            return False

        if stage == 'translation':
            pass

        if stage in ['excel_original', 'html_original', 'pdf_original', 'docx_original',
                     'excel_translated', 'html_translated', 'pdf_translated', 'docx_translated']:
            output_file = self._get_output_path(input_file, stage)
            if output_file and output_file.exists():
                logger.debug(f"[{file_name}] L5 Cache 命中: {output_file.name}")
                return True

        return False

    def _get_output_path(self, input_file: Path, stage: str) -> Optional[Path]:
        file_stem = input_file.stem

        if stage == 'excel_original':
            return Path(Constants.OUTPUT_EXCEL_DIR) / f"{file_stem}.xlsx"
        elif stage == 'excel_translated':
            return Path(Constants.OUTPUT_EXCEL_DIR) / f"(译文) {file_stem}.xlsx"

        elif stage == 'html_original':
            return Path(Constants.OUTPUT_HTML_DIR) / f"{file_stem}.html"
        elif stage == 'html_translated':
            return Path(Constants.OUTPUT_HTML_DIR) / f"(译文) {file_stem}.html"

        elif stage == 'pdf_original':
            return Path("output/pdf") / f"{file_stem}.pdf"
        elif stage == 'pdf_translated':
            return Path("output/pdf") / f"(译文) {file_stem}.pdf"

        elif stage == 'docx_original':
            return Path("output/docx") / f"{file_stem}.docx"
        elif stage == 'docx_translated':
            return Path("output/docx") / f"(译文) {file_stem}.docx"

        return None

    def _execute_stage_with_retry(
        self,
        input_file: Path,
        stage: str,
        max_retries: int = 10
    ):
        from logger import NetworkErrorHandler

        retry_delay = UserConfig.RETRY_DELAY

        for attempt in range(max_retries):
            try:
                self._execute_stage(input_file, stage)
                return

            except Exception as e:
                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)

                if not should_retry:
                    logger.error(f"[{stage}] {error_type}，不可重试")
                    raise

                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(f"[{stage}] {error_type}，第 {attempt+1}/{max_retries} 次重试，等待 {wait_time}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"[{stage}] {error_type}，重试次数耗尽")
                    raise

    def _execute_stage(self, input_file: Path, stage: str):
        file_id = input_file.stem
        file_name = input_file.name
        file_ext = input_file.suffix.lower()

        relative_folder = self.input_structure.get(str(input_file).replace('\\', '/'), "")
        json_base_dir = Path(Constants.OUTPUT_JSON_DIR)
        if relative_folder:
            json_output_dir = json_base_dir / relative_folder / file_id
        else:
            json_output_dir = json_base_dir / file_id

        if stage == 'extraction':
            logger.info(f"[{file_id}] 开始 PDF/DOCX 提取")

            if file_ext in ['.pdf']:
                df = self.extractor.extract_to_dataframe(str(input_file), str(json_output_dir))
            elif file_ext in ['.docx', '.doc']:
                if self.docx_extractor:
                    df = self.docx_extractor.extract_to_dataframe(str(input_file), str(json_output_dir))
                else:
                    raise RuntimeError("DOCX 提取器未初始化")
            else:
                raise ValueError(f"不支持的文件类型: {file_ext}")

            logger.info(f"[{file_id}] 提取完成：{len(df)} 篇文章")

            original_count = len(df)
            df, removed_ads = self._filter_advertisements(df, file_id)

            if removed_ads > 0:
                logger.info(f"[{file_id}] 广告过滤：移除 {removed_ads} 篇广告，剩余 {len(df)} 篇正文")

                articles_dir = json_output_dir / Constants.ARTICLES_SUBDIR
                articles_dir.mkdir(parents=True, exist_ok=True)
                filtered_json_path = articles_dir / f"final_articles_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                with open(filtered_json_path, 'w', encoding='utf-8') as f:
                    json.dump(df.to_dict('records'), f, ensure_ascii=False, indent=2)

                logger.info(f"[{file_id}] 已保存过滤后的文章到: {filtered_json_path.name}")
            else:
                logger.info(f"[{file_id}] 广告过滤：未检测到广告文章")

            return

        elif stage == 'image_processing':
            logger.info(f"[{file_id}] 开始图片处理")

            logger.info(f"[{file_id}] 图片处理完成（已在提取阶段处理）")
            return

        elif stage in ['excel_original', 'html_original', 'pdf_original', 'docx_original']:
            logger.info(f"[{file_id}] 开始生成{stage}")

            df = self._load_dataframe_from_cache(input_file)
            if df is None or len(df) == 0:
                raise RuntimeError(f"{stage} 失败：无法加载文章数据")

            if stage == 'excel_original':
                output_path = get_output_path_with_structure("output/excel", f"{file_id}.xlsx", str(input_file), self.input_structure)
                self.excel_generator.generate_excel_with_path(df, output_path, is_translated=False)

            elif stage == 'html_original':
                output_path = get_output_path_with_structure("output/html", f"{file_id}.html", str(input_file), self.input_structure)
                should_generate_pdf_docx = (self.output_language_mode in ['both', 'original_only'])

                self.html_generator.generate_html(
                    df,
                    pdf_name=file_id,
                    output_path=output_path,
                    is_translated=False,
                    cache_dir=str(json_output_dir),
                    progress_manager=self.progress_manager,
                    generate_pdf_docx=should_generate_pdf_docx
                )

            elif stage in ['pdf_original', 'docx_original']:
                logger.info(f"[{file_id}] {stage} 由 HTML 生成器处理，跳过")

            logger.info(f"[{file_id}] {stage} 完成")
            return

        elif stage == 'translation':
            if not self.generate_translation or not self.translator:
                logger.info(f"[{file_id}] 跳过翻译（未启用）")
                return

            logger.info(f"[{file_id}] 开始翻译")

            df = self._load_dataframe_from_cache(input_file)
            if df is None or len(df) == 0:
                raise RuntimeError("翻译失败：无法加载文章数据")

            outline_path = json_output_dir / Constants.OUTLINE_SUBDIR / "journal_outline.json"
            if outline_path.exists():
                try:
                    with open(outline_path, 'r', encoding='utf-8') as f:
                        journal_outline = json.load(f)
                    self.translator.set_journal_outline(journal_outline)
                except Exception as e:
                    logger.warning(f"[{file_id}] 加载 journal_outline 失败: {e}")

            file_signature = hashlib.md5(str(input_file).encode()).hexdigest()[:8]

            df_translated = self.translator.translate_dataframe(
                df,
                cache_dir=str(json_output_dir),
                progress_manager=self.progress_manager,
                file_signature=file_signature,
                source_file=str(input_file)
            )

            translated_json_path = json_output_dir / Constants.ARTICLES_SUBDIR / f"final_articles_translated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            translated_json_path.parent.mkdir(parents=True, exist_ok=True)

            with open(translated_json_path, 'w', encoding='utf-8') as f:
                json.dump(df_translated.to_dict('records'), f, ensure_ascii=False, indent=2)

            logger.info(f"[{file_id}] 翻译完成：{len(df_translated)} 篇文章")
            return

        elif stage in ['excel_translated', 'html_translated', 'pdf_translated', 'docx_translated']:
            if not self.generate_translation:
                logger.info(f"[{file_id}] 跳过{stage}（未启用翻译）")
                return

            logger.info(f"[{file_id}] 开始生成{stage}")

            df_translated = self._load_dataframe_from_cache(input_file, translated=True)
            if df_translated is None or len(df_translated) == 0:
                raise RuntimeError(f"{stage} 失败：无法加载翻译数据")

            if stage == 'excel_translated':
                output_path = get_output_path_with_structure("output/excel", f"(译文) {file_id}.xlsx", str(input_file), self.input_structure)
                self.excel_generator.generate_excel_with_path(df_translated, output_path, is_translated=True)

            elif stage == 'html_translated':
                output_path = get_output_path_with_structure("output/html", f"(译文) {file_id}.html", str(input_file), self.input_structure)
                should_generate_pdf_docx = (self.output_language_mode in ['both', 'translated_only'])

                self.html_generator.generate_html(
                    df_translated,
                    pdf_name=file_id,
                    output_path=output_path,
                    is_translated=True,
                    cache_dir=str(json_output_dir),
                    progress_manager=self.progress_manager,
                    generate_pdf_docx=should_generate_pdf_docx
                )

            elif stage in ['pdf_translated', 'docx_translated']:
                logger.info(f"[{file_id}] {stage} 由 HTML 生成器处理，跳过")

            logger.info(f"[{file_id}] {stage} 完成")
            return

        else:
            raise ValueError(f"未知阶段: {stage}")

    def _filter_advertisements(self, df, file_id):
        ad_keywords = UserConfig.AD_KEYWORDS
        if not ad_keywords:
            logger.debug(f"[{file_id}] 广告过滤：未配置AD_KEYWORDS，仅使用not_in_toc字段")
        df_filtered, count, removed_titles = _filter_ads_from_df(df, ad_keywords)
        if count:
            logger.info(f"[{file_id}] 广告过滤：检测到 {count} 篇广告:")
            for i, (title, reason) in enumerate(removed_titles[:5], 1):
                logger.info(f"[{file_id}]     {i}. {title}... ({reason})")
            if len(removed_titles) > 5:
                logger.info(f"[{file_id}]     ... 还有 {len(removed_titles) - 5} 篇")
        else:
            logger.debug(f"[{file_id}] 广告过滤：未检测到广告文章")
        return df_filtered, count

    def _load_dataframe_from_cache(self, input_file: Path, translated: bool = False) -> Optional[pd.DataFrame]:
        file_id = input_file.stem
        relative_folder = self.input_structure.get(str(input_file).replace('\\', '/'), "")
        json_base_dir = Path(Constants.OUTPUT_JSON_DIR)

        if relative_folder:
            json_output_dir = json_base_dir / relative_folder / file_id
        else:
            json_output_dir = json_base_dir / file_id

        articles_dir = json_output_dir / Constants.ARTICLES_SUBDIR
        if not articles_dir.exists():
            logger.error(f"[{file_id}] articles 目录不存在: {articles_dir}")
            return None

        if translated:
            for json_file in articles_dir.glob("final_articles_translated_*.json"):
                logger.debug(f"[{file_id}] 加载翻译缓存: {json_file.name}")
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        articles = json.load(f)
                    return pd.DataFrame(articles)
                except Exception as e:
                    logger.warning(f"[{file_id}] 加载 {json_file.name} 失败: {e}")
            logger.error(f"[{file_id}] 未找到翻译缓存 JSON")
            return None

        for json_file in articles_dir.glob("final_articles_*.json"):
            logger.debug(f"[{file_id}] 加载缓存: {json_file.name}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                return pd.DataFrame(articles)
            except Exception as e:
                logger.warning(f"[{file_id}] 加载 {json_file.name} 失败: {e}")

        for json_file in articles_dir.glob("merged_articles_*.json"):
            logger.debug(f"[{file_id}] 加载缓存: {json_file.name}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                return pd.DataFrame(articles)
            except Exception as e:
                logger.warning(f"[{file_id}] 加载 {json_file.name} 失败: {e}")

        logger.error(f"[{file_id}] 未找到 final_articles 或 merged_articles JSON")
        return None


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file_executor.shutdown(wait=True)

        logger.info(f"[SequentialFileProcessor] 已关闭")
        return False

if __name__ == "__main__":
    print("=== BoundedThreadPoolExecutor 测试 ===")

    def test_task(task_id: int):
        time.sleep(0.1)
        return f"Task {task_id} completed"

    with BoundedThreadPoolExecutor(max_workers=2, max_queue_size=3, name="TestExecutor") as executor:
        futures = []
        for i in range(10):
            print(f"提交任务 {i}")
            future = executor.submit(test_task, i)
            futures.append(future)

        for future in as_completed(futures):
            print(future.result())

        print("统计信息:", executor.get_stats())

    print("\n=== GlobalResourceManager 测试 ===")

    config = UserConfig.SEQUENTIAL_EXECUTOR_CONFIG
    manager = GlobalResourceManager(config)

    manager.register_file("file1")
    manager.register_file("file2")

    with manager.acquire_api_slot("file1"):
        print("执行 file1 的 API 调用")
        time.sleep(0.1)

    print("统计信息:", manager.get_stats())

    print("\n测试完成！")
