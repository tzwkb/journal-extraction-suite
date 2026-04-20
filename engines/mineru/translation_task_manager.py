"""
翻译任务管理模块
负责收集翻译任务、执行批量翻译、分配结果和管理失败文本重试
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from article_translator import ArticleTranslator


class TranslationTaskManager:
    """翻译任务管理器 - 收集任务、执行翻译、分配结果"""

    def __init__(self, logger, config):
        """
        初始化翻译任务管理器

        Args:
            logger: 日志记录器
            config: 配置字典
        """
        self.logger = logger
        self.config = config
        self.failed_texts_log = Path("logs/total_issue_files.jsonl")

    def is_garbage_text(self, text: str) -> bool:
        """
        检测文本是否为OCR识别错误产生的乱码（控制字符垃圾文本）

        Args:
            text: 待检测文本

        Returns:
            True表示是垃圾文本，False表示正常文本
        """
        if not text or len(text) < 10:
            return False

        # 统计控制字符数量（排除常见的换行、制表符）
        control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\t\r')

        # 如果控制字符占比超过80%，认为是垃圾文本（更保守的阈值）
        return control_chars / len(text) > 0.8

    def load_failed_cache(self) -> Dict:
        """
        加载失败文本缓存

        Returns:
            失败文本缓存字典 {text_id: record}
        """
        failed_texts_cache = {}
        if self.failed_texts_log.exists():
            self.logger.info("检测到失败文本日志，正在加载...")
            try:
                with open(self.failed_texts_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            text_id = record.get('text_id')
                            if text_id:
                                failed_texts_cache[text_id] = record
                self.logger.info(f"已加载 {len(failed_texts_cache)} 条失败记录")
            except Exception as e:
                self.logger.warning(f"读取失败日志出错: {str(e)}")
        return failed_texts_cache

    def collect_tasks(
        self,
        pages: dict,
        outline: dict,
        get_chapter_context_func
    ) -> List[Tuple]:
        """
        收集所有需要翻译的任务

        Args:
            pages: {page_idx: [items]} 页面内容字典
            outline: 文档大纲
            get_chapter_context_func: 获取章节上下文的函数

        Returns:
            [(item, field_name, text, context), ...] 任务列表
        """
        tasks = []

        for page_idx in sorted(pages.keys()):
            items = pages[page_idx]

            # 获取章节上下文
            chapter_context = get_chapter_context_func(page_idx, outline)

            for idx, item in enumerate(items):
                # 检查item是否有type字段，如果没有则跳过
                item_type = item.get('type')
                if not item_type:
                    # 没有type字段，标记为已处理并跳过
                    item['processed'] = True
                    continue

                # 只跳过真正不需要翻译的内容
                if item_type in ['footer', 'page_number']:
                    continue

                # 添加上下文窗口（前后500字符，提供更充足的上下文参考）
                context = chapter_context.copy()
                if idx > 0 and items[idx - 1].get('text'):
                    context['prev_text'] = items[idx - 1]['text'][-500:]
                else:
                    context['prev_text'] = ''

                if idx < len(items) - 1 and items[idx + 1].get('text'):
                    context['next_text'] = items[idx + 1]['text'][:500]
                else:
                    context['next_text'] = ''

                # 1. 正文文本
                if item_type == 'text' and item.get('text'):
                    # 过滤OCR垃圾文本（控制字符乱码）
                    if self.is_garbage_text(item['text']):
                        item['processed'] = True  # 标记为已处理，跳过翻译
                        continue
                    tasks.append((item, 'text_zh', item['text'], context))

                # 2. 页面脚注（重要注释）
                if item_type == 'page_footnote' and item.get('text'):
                    # 过滤OCR垃圾文本（控制字符乱码）
                    if self.is_garbage_text(item['text']):
                        item['processed'] = True  # 标记为已处理，跳过翻译
                        continue
                    tasks.append((item, 'text_zh', item['text'], context))

                # 3. 列表项
                if item_type == 'list' and item.get('list_items'):
                    # 初始化列表翻译字段
                    if 'list_items_zh' not in item:
                        item['list_items_zh'] = []
                    # 翻译每个列表项
                    for list_item in item['list_items']:
                        if list_item and isinstance(list_item, str):
                            # 过滤OCR垃圾文本
                            if not self.is_garbage_text(list_item):
                                tasks.append((item, 'list_items_zh', list_item, context))

                # 4. 表格
                if item_type == 'table':
                    # 翻译表格标题
                    if item.get('table_caption'):
                        caption_text = ' '.join(item['table_caption']) if isinstance(item['table_caption'], list) else item['table_caption']
                        # 过滤OCR垃圾文本
                        if not self.is_garbage_text(caption_text):
                            tasks.append((item, 'table_caption_zh', caption_text, context))
                    # 翻译表格内容
                    if item.get('table_body'):
                        tasks.append((item, 'table_body_zh', item['table_body'], context))

                # 5. 图片
                if item_type == 'image':
                    # 翻译图片标题
                    if item.get('image_caption'):
                        caption_text = ' '.join(item['image_caption']) if isinstance(item['image_caption'], list) else item['image_caption']
                        # 过滤OCR垃圾文本
                        if not self.is_garbage_text(caption_text):
                            tasks.append((item, 'image_caption_zh', caption_text, context))
                    # 翻译图片脚注
                    if item.get('image_footnote'):
                        footnote_text = ' '.join(item['image_footnote']) if isinstance(item['image_footnote'], list) else item['image_footnote']
                        if footnote_text:
                            # 过滤OCR垃圾文本
                            if not self.is_garbage_text(footnote_text):
                                tasks.append((item, 'image_footnote_zh', footnote_text, context))

                # 6. 参考文献（不翻译，但标记为已处理）
                if item_type == 'ref_text':
                    item['processed'] = True

                # 7. 代码块（不翻译，但标记为已处理）
                if item_type == 'code':
                    item['processed'] = True

        return tasks

    def execute_translations(
        self,
        tasks: List[Tuple],
        translator: ArticleTranslator
    ) -> List[str]:
        """
        批量执行翻译（带 text_id 追踪）

        Args:
            tasks: [(item, field_name, text, context), ...] 任务列表
            translator: 翻译器实例

        Returns:
            翻译结果列表
        """
        self.logger.info(f"共收集 {len(tasks)} 个翻译任务，开始并发翻译...")

        # 批量并发翻译（带text_id追踪）
        translation_tasks = []
        for task_idx, (item, field_name, text, context) in enumerate(tasks):
            # 生成唯一的text_id
            page_idx = item.get('page_idx', 0)
            text_id = f"page_{page_idx}_task_{task_idx}_{field_name}"

            # 将text_id添加到context中
            context_with_id = context.copy()
            context_with_id['text_id'] = text_id
            context_with_id['page_idx'] = page_idx

            translation_tasks.append((text, context_with_id))

        translations = translator.translate_batch(translation_tasks)
        return translations

    def assign_results(
        self,
        tasks: List[Tuple],
        translations: List[str],
        failed_texts_cache: Dict
    ) -> Dict:
        """
        将翻译结果分配回原始 items

        Args:
            tasks: [(item, field_name, text, context), ...] 任务列表
            translations: 翻译结果列表
            failed_texts_cache: 失败文本缓存

        Returns:
            重试统计信息 {'retry_success_count': int, 'retry_failed_count': int}
        """
        # 跟踪哪些之前失败的文本这次成功了
        retry_success_count = 0
        retry_failed_count = 0

        # 赋值翻译结果
        for i, (item, field_name, original_text, context) in enumerate(tasks):
            translated_text = translations[i]

            # 生成 text_id（需要与 execute_translations 中的逻辑一致）
            page_idx = item.get('page_idx', 0)
            text_id = f"page_{page_idx}_task_{i}_{field_name}"

            # 检查是否是之前失败的文本
            if text_id in failed_texts_cache:
                # 检查这次是否翻译成功（译文不等于原文）
                if translated_text != original_text:
                    retry_success_count += 1
                    # 从缓存中移除（表示已成功）
                    del failed_texts_cache[text_id]
                else:
                    retry_failed_count += 1

            # 检查是否是合并项
            if item.get('merged') and 'original_items' in item:
                # 拆分译文回原始TEXT块
                originals = item['original_items']

                # 按原始文本长度比例拆分
                len1 = len(originals[0]['text'])
                len2 = len(originals[1]['text'])
                total_len = len1 + len2

                if total_len > 0:
                    ratio = len1 / total_len
                    split_point = int(len(translated_text) * ratio)

                    # 分配译文
                    originals[0][field_name] = translated_text[:split_point].strip()
                    originals[1][field_name] = translated_text[split_point:].strip()

                    # 保留合并信息（用于调试）
                    originals[0]['_merged_from'] = item['text']
                    originals[1]['_merged_from'] = item['text']
                else:
                    # 异常情况：原始文本长度为0，直接赋值给第一个
                    originals[0][field_name] = translated_text
            else:
                # 特殊处理：列表项需要append而不是赋值
                if field_name == 'list_items_zh':
                    if 'list_items_zh' not in item:
                        item['list_items_zh'] = []
                    item['list_items_zh'].append(translated_text)
                else:
                    # 其他字段直接赋值
                    item[field_name] = translated_text

            if (i + 1) % max(1, len(tasks) // 10) == 0:
                progress = (i + 1) * 100 // len(tasks)
                self.logger.info(f"  翻译进度: {i + 1}/{len(tasks)} ({progress}%)")

        self.logger.success(f"翻译完成: {len(tasks)} 个内容块")

        return {
            'retry_success_count': retry_success_count,
            'retry_failed_count': retry_failed_count
        }

    def update_failed_log(
        self,
        failed_texts_cache: Dict,
        retry_stats: Dict
    ) -> None:
        """
        更新失败日志文件

        Args:
            failed_texts_cache: 失败文本缓存
            retry_stats: 重试统计信息
        """
        retry_success_count = retry_stats['retry_success_count']
        retry_failed_count = retry_stats['retry_failed_count']

        # 输出重试统计
        if retry_success_count > 0 or retry_failed_count > 0:
            self.logger.info(f"\n📊 失败文本重试统计:")
            if retry_success_count > 0:
                self.logger.success(f"  ✓ 重试成功: {retry_success_count} 个")
            if retry_failed_count > 0:
                self.logger.warning(f"  ✗ 仍失败: {retry_failed_count} 个")

        # 更新失败日志（移除成功的记录）
        if self.failed_texts_log.exists() and retry_success_count > 0:
            try:
                # 读取所有记录
                all_records = []
                with open(self.failed_texts_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            # 只保留仍失败的记录
                            if record.get('text_id') in failed_texts_cache:
                                all_records.append(record)

                # 重写文件
                with open(self.failed_texts_log, 'w', encoding='utf-8') as f:
                    for record in all_records:
                        f.write(json.dumps(record, ensure_ascii=False) + '\n')

                self.logger.success(f"已更新失败日志，移除 {retry_success_count} 条成功记录")

            except Exception as e:
                self.logger.warning(f"更新失败日志出错: {str(e)}")
