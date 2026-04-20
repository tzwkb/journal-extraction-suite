
import time
import json
import re
from typing import List, Dict, Any, Union, Optional, Tuple
from pathlib import Path
from config import UserConfig
from core.logger import get_logger

def remove_file_with_retry(path, retries: int = 3, delay: float = 1.0) -> bool:
    for _ in range(retries):
        try:
            Path(path).unlink()
            return True
        except OSError:
            time.sleep(delay)
    return False

def is_file_locked(path) -> bool:
    try:
        with open(path, 'a'):
            return False
    except OSError:
        return True

try:
    import fitz
except ImportError:
    fitz = None

class PDFBatchManager:
    
    def __init__(self, pages_per_batch: int = 5, overlap_pages: int = 1):
        self.pages_per_batch = pages_per_batch
        self.overlap_pages = overlap_pages
        
        if fitz is None:
            raise ImportError("需要安装 PyMuPDF: pip install pymupdf")
    
    def split_to_batches(self, pdf_path: str) -> List[Dict[str, Any]]:
        print(f"📄 分析PDF: {Path(pdf_path).name}")
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        print(f"   总页数: {total_pages}")
        print(f"   每批处理: {self.pages_per_batch} 页")
        print(f"   重叠页数: {self.overlap_pages} 页（前后各{self.overlap_pages}页）")
        
        batches = []
        
        step = self.pages_per_batch - self.overlap_pages
        if step <= 0:
            raise ValueError(
                f"overlap_pages ({self.overlap_pages}) 必须小于 pages_per_batch ({self.pages_per_batch})，"
                f"否则步长为 {step}，会导致无限循环"
            )

        start_page = 0
        batch_idx = 0
        
        while start_page < total_pages:
            end_page = min(start_page + self.pages_per_batch, total_pages)
            
            temp_doc = fitz.open()
            temp_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)
            
            pdf_bytes = temp_doc.write()
            temp_doc.close()
            
            has_overlap_before = start_page > 0
            has_overlap_after = end_page < total_pages
            
            batches.append({
                'batch_idx': batch_idx + 1,
                'pages': (start_page + 1, end_page),
                'pdf_bytes': pdf_bytes,
                'page_range': f"{start_page + 1}-{end_page}",
                'has_overlap_before': has_overlap_before,
                'has_overlap_after': has_overlap_after,
                'overlap_pages': self.overlap_pages,
                'size_kb': len(pdf_bytes) / 1024
            })
            
            start_page += step
            batch_idx += 1
        
        doc.close()
        
        print(f"   已分割为 {len(batches)} 个批次")
        print(f"   实际步长: 每批新增 {step} 页内容\n")
        
        return batches
    
class ArticleMerger:
    
    @staticmethod
    def safe_get_field(article: Dict, field: str, default: str = '') -> str:
        value = article.get(field, default)
        return value if value is not None else default
    
    @classmethod
    def merge_fragments(cls, all_batch_results: List[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        print("🔗 合并跨页文章片段...")
        
        all_fragments = []
        
        batch_idx = 0
        for batch_results in all_batch_results:
            for article in batch_results:
                title = cls.safe_get_field(article, 'title').strip()
                content = cls.safe_get_field(article, 'content').strip()
                
                if not content or len(content) < 50:
                    continue
                
                article['_batch_idx'] = batch_idx
                article['_normalized_title'] = cls._normalize_for_comparison(title)
                all_fragments.append(article)
            batch_idx += 1
        
        fragments_by_title = cls._group_fragments_by_similar_title(all_fragments)
        
        print(f"   发现 {len(fragments_by_title)} 个不同标题的文章")
        
        merged_articles = []
        for title, fragments in fragments_by_title.items():
            if not title:
                for frag in fragments:
                    merged_articles.append({
                        'title': '',
                        'subtitle': cls.safe_get_field(frag, 'subtitle'),
                        'authors': cls.safe_get_field(frag, 'authors'),
                        'content': cls.safe_get_field(frag, 'content'),
                        'start_page': frag.get('start_page'),
                        'end_page': frag.get('end_page'),
                        'images': frag.get('images', [])
                    })
                continue
            
            fragments.sort(key=lambda x: x.get('_batch_idx', 0))
            
            if len(fragments) == 1:
                not_in_toc = fragments[0].get('not_in_toc', False)
                merged_articles.append({
                    'title': title,
                    'subtitle': cls.safe_get_field(fragments[0], 'subtitle'),
                    'authors': cls.safe_get_field(fragments[0], 'authors'),
                    'content': cls.safe_get_field(fragments[0], 'content'),
                    'not_in_toc': not_in_toc,
                    'start_page': fragments[0].get('start_page'),
                    'end_page': fragments[0].get('end_page'),
                    'images': fragments[0].get('images', [])
                })
            else:
                print(f"   🔗 合并 {len(fragments)} 个片段: {title[:60]}...")

                subtitle = ''
                authors = ''
                not_in_toc = False
                start_pages = [f.get('start_page') for f in fragments if f.get('start_page')]
                end_pages = [f.get('end_page') for f in fragments if f.get('end_page')]
                start_page = min(start_pages) if start_pages else None
                end_page = max(end_pages) if end_pages else None

                for frag in fragments:
                    if not subtitle and frag.get('subtitle'):
                        subtitle = cls.safe_get_field(frag, 'subtitle')
                    if not authors and frag.get('authors'):
                        authors = cls.safe_get_field(frag, 'authors')
                    if frag.get('not_in_toc', False):
                        not_in_toc = True
                    if subtitle and authors:
                        break

                merged_content = cls._smart_merge_contents(fragments)

                all_images = []
                for frag in fragments:
                    frag_images = frag.get('images', [])
                    if isinstance(frag_images, list):
                        all_images.extend(frag_images)

                merged_articles.append({
                    'title': title,
                    'subtitle': subtitle,
                    'authors': authors,
                    'content': merged_content,
                    'not_in_toc': not_in_toc,
                    'start_page': start_page,
                    'end_page': end_page,
                    'images': all_images
                })
        
        print(f"✅ 合并完成，共 {len(merged_articles)} 篇文章")
        
        filtered_articles = cls._filter_non_articles(merged_articles)
        
        if len(filtered_articles) < len(merged_articles):
            removed_count = len(merged_articles) - len(filtered_articles)
            print(f"🔍 已过滤 {removed_count} 个非文章内容（目录、封面等）")
        
        return filtered_articles
    

    @classmethod
    def _group_fragments_by_similar_title(cls, fragments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        from collections import defaultdict
        
        groups = {}
        normalized_to_original = {}
        
        for frag in fragments:
            title = cls.safe_get_field(frag, 'title').strip()
            normalized = frag.get('_normalized_title', '')
            
            if not title and not normalized:
                if '' not in groups:
                    groups[''] = []
                    normalized_to_original[''] = ''
                groups[''].append(frag)
                continue
            
            found_group = False
            for existing_normalized in list(groups.keys()):
                if not existing_normalized:
                    continue
                
                if normalized == existing_normalized:
                    groups[existing_normalized].append(frag)
                    found_group = True
                    break
                
                if normalized and existing_normalized:
                    if (normalized in existing_normalized) or (existing_normalized in normalized):
                        groups[existing_normalized].append(frag)
                        found_group = True
                        break
            
            if not found_group:
                groups[normalized] = [frag]
                normalized_to_original[normalized] = title
        
        result = {}
        for normalized, frags in groups.items():
            if not normalized:
                result[''] = frags
            else:
                best_title = max((cls.safe_get_field(f, 'title').strip() for f in frags), 
                                key=len, default='')
                result[best_title] = frags
        
        return result
    
    @classmethod
    def _normalize_for_comparison(cls, text: str) -> str:
        import re
        if not text:
            return ''

        normalized = text.lower()
        normalized = re.sub(r'[–—―‒−－-]', '-', normalized)
        normalized = re.sub(r'[""„‟❝❞«»‹›]', '"', normalized)
        normalized = re.sub(r'[…⋯]', '...', normalized)
        normalized = re.sub(r'[^\x00-\x7F]+', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    @classmethod
    def _fuzzy_contains(cls, sample: str, content: str, threshold: float = 0.9) -> bool:
        if not sample or not content:
            return False

        sample_norm = cls._normalize_for_comparison(sample)
        content_norm = cls._normalize_for_comparison(content)

        if sample_norm in content_norm:
            return True

        sample_len = len(sample_norm)
        if sample_len == 0:
            return False

        max_similarity = 0.0
        for i in range(len(content_norm) - sample_len + 1):
            window = content_norm[i:i + sample_len]
            matches = sum(1 for a, b in zip(sample_norm, window) if a == b)
            similarity = matches / sample_len
            max_similarity = max(max_similarity, similarity)

            if similarity >= threshold:
                return True

        return max_similarity >= threshold

    @classmethod
    def _smart_merge_contents(cls, fragments: List[Dict[str, Any]]) -> str:
        if not fragments:
            return ''

        if len(fragments) == 1:
            return cls.safe_get_field(fragments[0], 'content')

        merged_parts = []

        for i, frag in enumerate(fragments):
            content = cls.safe_get_field(frag, 'content').strip()
            if not content:
                continue

            if i == 0:
                merged_parts.append(content)
            else:
                prev_content = merged_parts[-1] if merged_parts else ''

                if prev_content and len(content) > len(prev_content) * 1.5:
                    prev_sample = prev_content[:min(300, len(prev_content))]
                    if cls._fuzzy_contains(prev_sample, content, threshold=0.85):
                        print(f"      检测到更完整版本（{len(content)} > {len(prev_content)}字符），替换")
                        merged_parts[-1] = content
                        continue

                overlap_found = False
                if prev_content:
                    prev_tail = prev_content[-200:] if len(prev_content) > 200 else prev_content
                    curr_head = content[:200] if len(content) > 200 else content

                    for overlap_len in range(min(150, len(prev_tail), len(curr_head)), 20, -1):
                        if prev_tail[-overlap_len:] == content[:overlap_len]:
                            overlap_found = True
                            new_content = content[overlap_len:].strip()
                            if new_content:
                                merged_parts.append(new_content)
                                print(f"      检测到开头重叠 ({overlap_len} 字符)，智能去重")
                            else:
                                print(f"      检测到完全重叠，跳过重复片段")
                            break

                if not overlap_found:
                    merged_parts.append(content)

        merged_content = '\n\n'.join(merged_parts)
        deduplicated_content = cls._deduplicate_paragraphs(merged_content)

        return deduplicated_content
    
    @staticmethod
    def _deduplicate_paragraphs(content: str) -> str:
        import re

        if not content or len(content.strip()) == 0:
            return content

        paragraphs = re.split(r'\n\s*\n', content)

        seen_map = {}
        unique_paragraphs = []
        duplicate_count = 0
        replaced_count = 0

        for para in paragraphs:
            para_stripped = para.strip()

            if not para_stripped:
                continue

            normalized = para_stripped.lower()
            normalized = re.sub(r'[–—-]', '-', normalized)
            normalized = re.sub(r'[""'']', '"', normalized)
            normalized = re.sub(r'[…]', '...', normalized)
            normalized = re.sub(r'\s+', ' ', normalized)
            normalized = normalized.strip()

            if len(normalized) < 20:
                unique_paragraphs.append(para_stripped)
                continue

            if normalized in seen_map:
                duplicate_count += 1
                continue

            is_similar = False
            replaced = False
            for existing_norm, (existing_text, existing_idx) in list(seen_map.items()):
                if len(existing_norm) > 50:
                    sample_len = min(100, len(normalized), len(existing_norm))
                    if normalized[:sample_len] == existing_norm[:sample_len]:
                        if len(normalized) > len(existing_norm) * 1.5:
                            print(f"      检测到更完整段落版本（{len(normalized)} > {len(existing_norm)}字符），替换旧版本")
                            del seen_map[existing_norm]
                            seen_map[normalized] = (para_stripped, existing_idx)
                            unique_paragraphs[existing_idx] = para_stripped
                            replaced = True
                            replaced_count += 1
                            break
                        else:
                            is_similar = True
                            duplicate_count += 1
                            break

            if replaced:
                continue

            if not is_similar:
                idx = len(unique_paragraphs)
                seen_map[normalized] = (para_stripped, idx)
                unique_paragraphs.append(para_stripped)

        if duplicate_count > 0 or replaced_count > 0:
            msg = f"      去除 {duplicate_count} 个重复段落"
            if replaced_count > 0:
                msg += f"，替换 {replaced_count} 个不完整版本"
            print(msg)

        return '\n\n'.join(unique_paragraphs)
    
    @classmethod
    def _filter_non_articles(cls, articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
        filtered = []
        
        toc_keywords = [
            'contents', 'table of contents', 'toc',
            '目录', '目次', 'もくじ',
            'contenido', 'índice', 'sommaire'
        ]
        
        cover_keywords = [
            'cover', 'front cover', 'back cover',
            'copyright', 'publication info',
            '封面', '版权', '出版信息'
        ]
        
        for article in articles:
            title = (article.get('title') or '').strip().lower()
            content = (article.get('content') or '').strip()
            
            if not title and not content:
                continue
            
            is_toc = False
            for keyword in toc_keywords:
                if keyword in title:
                    is_toc = True
                    break
            
            is_cover = False
            for keyword in cover_keywords:
                if keyword in title:
                    is_cover = True
                    break
            
            if not is_toc and content:
                lines = content.split('\n')
                if len(lines) < 30:
                    page_number_lines = sum(1 for line in lines if line.strip().isdigit() or 
                                           any(pattern in line for pattern in [' p.', ' pp.', '页']))
                    if page_number_lines > len(lines) * 0.3:
                        is_toc = True
            
            if not is_toc and not is_cover:
                filtered.append(article)
        
        return filtered
    
    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return ArticleMerger._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    @classmethod
    def _calculate_similarity_score(cls, title1: str, title2: str) -> float:
        import re
        from difflib import SequenceMatcher
        
        def normalize(text):
            text = text.lower().strip()
            text = re.sub(r'[^\w\s]', ' ', text)
            return ' '.join(text.split())
        
        norm1 = normalize(title1)
        norm2 = normalize(title2)
        
        if not norm1 or not norm2:
            return 0.0
        
        if norm1 == norm2:
            return 1.0
        
        distance = cls._levenshtein_distance(norm1, norm2)
        max_len = max(len(norm1), len(norm2))
        lev_sim = 1.0 - (distance / max_len) if max_len > 0 else 0.0
        
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        intersection = words1 & words2
        union = words1 | words2
        jac_word = len(intersection) / len(union) if union else 0.0
        
        seq_sim = SequenceMatcher(None, norm1, norm2).ratio()
        
        cont_sim = 0.0
        shorter = min(norm1, norm2, key=len)
        longer = max(norm1, norm2, key=len)
        if shorter in longer:
            cont_sim = len(shorter) / len(longer)
        
        stopwords = {
            'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
            'if', 'do', 'we', 'have', 's', 'not', 'like', 'they', 're', 'us', 'it'
        }
        keywords1 = [w for w in norm1.split() if w not in stopwords]
        keywords2 = [w for w in norm2.split() if w not in stopwords]
        kw_set1 = set(keywords1)
        kw_set2 = set(keywords2)
        kw_inter = kw_set1 & kw_set2
        kw_union = kw_set1 | kw_set2
        kw_sim = len(kw_inter) / len(kw_union) if kw_union else 0.0
        
        weights = UserConfig.SIMILARITY_WEIGHTS
        
        scores = {
            'levenshtein': lev_sim,
            'jaccard_word': jac_word,
            'sequence': seq_sim,
            'contains': cont_sim,
            'keywords': kw_sim
        }
        
        hybrid_score = sum(scores[k] * weights[k] for k in scores.keys())
        
        return hybrid_score
    
    @classmethod
    def is_similar_title(cls, title1: str, title2: str, threshold: float = None) -> bool:
        if threshold is None:
            threshold = UserConfig.TITLE_SIMILARITY_THRESHOLD
            
        if not title1 or not title2:
            return False
        
        if title1.strip() == title2.strip():
            return True
        
        similarity = cls._calculate_similarity_score(title1, title2)
        
        return similarity >= threshold
    
    @classmethod
    def _is_content_duplicate(cls, content1: str, content2: str, threshold: float = None) -> bool:
        if threshold is None:
            threshold = UserConfig.CONTENT_DUPLICATE_THRESHOLD
        if not content1 or not content2:
            return False
        
        c1 = content1[:500].lower().strip()
        c2 = content2[:500].lower().strip()
        
        shorter = min(len(c1), len(c2))
        longer = max(len(c1), len(c2))
        
        if shorter == 0:
            return False
        
        if c1[:shorter] == c2[:shorter]:
            return True
        
        if len(c1) < len(c2):
            return c1 in c2
        else:
            return c2 in c1
    
    @staticmethod
    def _check_article_start_quality(content: str, title: str = '') -> tuple:
        if not content or len(content) < 50:
            return True, ""

        first_words = content.split()[:3]
        if not first_words:
            return True, ""

        first_word = first_words[0].lower().rstrip('.,!?;:')

        if content and content[0].islower():
            truncated_patterns = {
                'less', 'ness', 'ment', 'tion', 'sion', 'ing', 'ed', 'er', 'est',
                'ly', 'ful', 'able', 'ible', 'ous', 'ive', 'al', 'ic', 'ant', 'ent'
            }

            for suffix in truncated_patterns:
                if first_word == suffix or (first_word.startswith(suffix) and len(first_word) > len(suffix)):
                    return False, f"⚠️ 开头明显被截断：以 '{first_word}' 开始（可能缺少前缀）"

            high_suspicious_starts = {
                'and', 'but', 'or', 'nor', 'yet', 'so',
                'because', 'although', 'though', 'since', 'unless', 'while',
                'was', 'were', 'been', 'being',
                'having', 'doing'
            }

            medium_suspicious_starts = {
                'the', 'that', 'this', 'which', 'what', 'who', 'where', 'when', 'why', 'how',
                'it', 'he', 'she', 'they', 'we',
                'as', 'if', 'in', 'on', 'at', 'to', 'for', 'by', 'from', 'with', 'of',
                'a', 'an', 'is', 'are', 'have', 'has', 'do', 'does', 'did',
                'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'shall'
            }

            if first_word in high_suspicious_starts:
                return False, f"⚠️ 开头很可能被截断：以连接词 '{first_word}' 开始"

            if first_word in medium_suspicious_starts:
                if len(first_words) >= 2:
                    second_word = first_words[1]
                    if second_word and second_word[0].isupper():
                        return True, ""

                return False, f"ℹ️ 开头可能被截断：以 '{first_word}' 开始（小写，但可能合理）"

            if len(first_word) > 1 and first_word not in {'i', 'a', 'e'}:
                if len(first_word) >= 4:
                    return False, f"⚠️ 开头异常：以不常见小写词 '{first_word}' 开始（长度{len(first_word)}）"

        return True, ""
    
    @classmethod
    def deduplicate(cls, articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not articles:
            return articles
        
        print("🔍 检测并去除重复文章...")
        print("📋 检查文章开头质量...")
        
        deduplicated = []
        seen_titles = {}
        quality_issues = []
        
        for article_idx, article in enumerate(articles, 1):
            title_value = article.get('title', '')
            title = title_value.strip() if title_value else ''
            content = article.get('content', '') or ''
            
            if not title and not content.strip():
                print(f"   ⏭️  跳过空文章")
                continue
            
            is_valid_start, issue_desc = cls._check_article_start_quality(content, title)
            if not is_valid_start:
                quality_issues.append({
                    'article_idx': article_idx,
                    'title': title[:60] if title else '（无标题）',
                    'issue': issue_desc,
                    'content_start': content[:50] if content else ''
                })
                print(f"   {issue_desc} - 文章: {title[:50] if title else '（无标题）'}...")
            
            if not title:
                is_content_dup = False
                dup_idx = None
                
                for idx, existing_article in enumerate(deduplicated):
                    existing_content = existing_article.get('content') or ''
                    if cls._is_content_duplicate(content, existing_content):
                        is_content_dup = True
                        dup_idx = idx
                        print(f"   ⏭️  跳过重复内容: 内容与第{idx+1}篇重复（无标题文章）")
                        break
                
                if is_content_dup:
                    continue
                else:
                    if len(content.strip()) < 200:
                        print(f"   ⏭️  跳过过短内容: {len(content)} 字符（无标题文章）")
                        continue
                    else:
                        print(f"   ⚠️  保留无标题文章: {content[:50]}...")
                        deduplicated.append(article)
                continue
            
            is_duplicate = False
            duplicate_idx = None
            
            for existing_title, idx in seen_titles.items():
                if cls.is_similar_title(title, existing_title):
                    is_duplicate = True
                    duplicate_idx = idx
                    break
            
            if is_duplicate:
                existing_article = deduplicated[duplicate_idx]
                existing_content = existing_article.get('content') or ''
                current_content = content
                existing_len = len(existing_content)
                current_len = len(current_content)
                
                if current_len > existing_len:
                    print(f"   📝 替换重复文章: {title[:50]}... (更完整: {current_len} vs {existing_len} 字符)")
                    deduplicated[duplicate_idx] = article
                else:
                    print(f"   ⏭️  跳过重复文章: {title[:50]}... (已有更完整版本)")
            else:
                content_dup_found = False
                for idx, existing_article in enumerate(deduplicated):
                    existing_title = (existing_article.get('title') or '').strip()
                    existing_content = existing_article.get('content') or ''
                    
                    if cls._is_content_duplicate(content, existing_content):
                        content_dup_found = True
                        print(f"\n   ⚠️  【异常警告】发现内容重复但标题不同的文章:")
                        print(f"      当前文章标题: {title[:60]}...")
                        print(f"      已存在文章标题: {existing_title[:60]}...")
                        print(f"      内容相似度: 高（前500字符匹配）")
                        print(f"      建议: 人工检查是否为同一篇文章")
                        print(f"      处理: 两篇都保留，请稍后审查\n")
                        break
                
                seen_titles[title] = len(deduplicated)
                deduplicated.append(article)
        
        removed_count = len(articles) - len(deduplicated)
        if removed_count > 0:
            print(f"✅ 去重完成，移除 {removed_count} 篇重复/无效文章")
        else:
            print("✅ 未发现重复文章")
        
        if quality_issues:
            print(f"\n{'='*80}")
            print(f"⚠️  【文章开头质量检查报告】发现 {len(quality_issues)} 篇文章开头可能有问题")
            print(f"{'='*80}")
            for issue in quality_issues:
                print(f"\n【第 {issue['article_idx']} 篇】{issue['title']}")
                print(f"  问题: {issue['issue']}")
                print(f"  开头: {issue['content_start']}...")
                print(f"  建议: 检查该文章是否被截断，可能需要重新提取")
            print(f"{'='*80}\n")
        
        return deduplicated

class PDFPreprocessor:

    _log = get_logger("pdf_preprocessor")

    @staticmethod
    def remove_images(input_pdf_path: str, output_pdf_path: str, selective: bool = True) -> int:
        log = PDFPreprocessor._log
        doc = fitz.open(input_pdf_path)
        removed_count = 0
        if selective:
            log.info("🔍 扫描PDF中的图像...")
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                for img in image_list:
                    xref = img[0]
                    try:
                        img_info = doc.extract_image(xref)
                        if img_info.get('ext') == 'webp':
                            log.warning(f"  第{page_num+1}页: 删除WebP图像 (xref={xref})")
                            page.delete_image(xref)
                            removed_count += 1
                        elif len(img_info.get('image', b'')) < 100:
                            log.warning(f"  第{page_num+1}页: 删除异常小图像 (xref={xref}, size={len(img_info['image'])})")
                            page.delete_image(xref)
                            removed_count += 1
                    except Exception as e:
                        log.warning(f"  第{page_num+1}页: 删除损坏图像 (xref={xref}, 错误={str(e)[:50]})")
                        page.delete_image(xref)
                        removed_count += 1
            doc.save(output_pdf_path, garbage=4, deflate=True)
            doc.close()
            log.info(f"✅ 选择性删除完成: 删除{removed_count}个可疑图像")
        else:
            log.info("🔍 删除PDF中的所有图像...")
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                for img in image_list:
                    xref = img[0]
                    page.delete_image(xref)
                    removed_count += 1
            doc.save(output_pdf_path, garbage=4, deflate=True)
            doc.close()
            log.info(f"✅ 完全删除完成: 删除{removed_count}个图像")
        return removed_count


logger = get_logger("json_utils")

def clean_articles_list(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned_articles = []
    for art in articles:
        cleaned = {}
        for key, value in art.items():
            if value is None:
                cleaned[key] = None
            elif isinstance(value, str):
                value = value.strip()
                cleaned[key] = None if value.lower() == 'null' else value
            else:
                cleaned[key] = value
        cleaned_articles.append(cleaned)
    return cleaned_articles

class JSONParser:

    @staticmethod
    def parse_with_llm_retry(
        initial_response: str,
        llm_fix_callback,
        pdf_bytes: bytes,
        expected_type: str = 'array',
        max_retries: int = 10,
        retry_on_callback_error: bool = False
    ):
        current_response = initial_response
        fix_attempt = 0

        while fix_attempt <= max_retries:
            try:
                result = JSONParser.parse_llm_response(current_response, expected_type=expected_type)

                if fix_attempt > 0:
                    print(f"      ✅ JSON修复成功！(第{fix_attempt}次修复)")

                return result

            except ValueError as e:
                error_msg = str(e)
                fix_attempt += 1

                if fix_attempt > max_retries:
                    print(f"      ❌ 达到最大修复次数({max_retries})，无法修复JSON")
                    raise ValueError(f"JSON修复失败（已重试{max_retries}次）: {error_msg}")

                print(f"      ⚠️ JSON解析失败(第{fix_attempt}次): {error_msg[:80]}")
                print(f"      🔧 正在请求LLM修复JSON...")

                fix_prompt = f"""Your previous JSON response has a syntax error:

ERROR: {error_msg}

Your previous response was:
{current_response[:2000]}...

Please fix the JSON syntax error and return ONLY the corrected JSON {'array' if expected_type == 'array' else 'object'}.
Requirements:
1. Return ONLY valid JSON {'array format: [...]' if expected_type == 'array' else 'object format: {...}'}
2. Fix all syntax errors (missing commas, quotes, brackets, etc.)
3. Keep all the content from the original response
4. Use markdown code block: ```json ... ```

Return the corrected JSON now:"""

                try:
                    current_response = llm_fix_callback(pdf_bytes, fix_prompt)
                    print(f"      📝 已收到修复后的JSON，重新解析...")

                except Exception as fix_error:
                    if retry_on_callback_error:
                        error_detail = str(fix_error)[:100]
                        print(f"      ❌ LLM修复请求失败: {error_detail}")
                        print(f"      ⏳ 等待5秒后继续重试...")
                        logger.warning(f"LLM fix callback failed: {error_detail}")

                        import time
                        time.sleep(5)
                        fix_attempt -= 1
                        continue
                    else:
                        print(f"      ❌ LLM修复请求失败: {str(fix_error)[:100]}")
                        print(f"      ⚠️ 无法继续修复JSON")
                        raise ValueError(f"LLM修复请求失败: {fix_error}")

        raise ValueError("JSON修复失败（未知原因）")

    @staticmethod
    def _extract_first_json(json_str: str) -> str:
        open_char = close_char = None
        depth = 0
        in_string = False
        escape = False
        start = -1

        for i, c in enumerate(json_str):
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if open_char is None:
                if c == '[':
                    open_char, close_char = '[', ']'
                    start = i
                    depth = 1
                elif c == '{':
                    open_char, close_char = '{', '}'
                    start = i
                    depth = 1
            else:
                if c == open_char:
                    depth += 1
                elif c == close_char:
                    depth -= 1
                    if depth == 0:
                        return json_str[start:i + 1]

        return json_str

    @staticmethod
    def _fix_json_string(json_str: str) -> str:
        fixed = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)

        def fix_escape(match):
            char = match.group(1)
            if char in '"\\"/bfnrtu':
                return match.group(0)
            else:
                return '\\\\' + char

        fixed = re.sub(r'\\(.)', fix_escape, fixed)

        return fixed

    @staticmethod
    def parse_llm_response(response: str, expected_type: str = 'array') -> Union[Dict, List]:
        if not response or not isinstance(response, str):
            raise ValueError("响应为空或格式不正确")

        from logger import ResponseValidator

        is_error, error_desc = ResponseValidator.is_error_response(response)
        if is_error:
            raise ValueError(f"响应包含错误信息: {error_desc}")

        response = response.strip()

        markdown_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        match = re.search(markdown_pattern, response, re.DOTALL)

        if match:
            json_str = match.group(1).strip()
            logger.debug("从markdown代码块中提取JSON")
        else:
            json_obj_match = re.search(r'\{.*?\}', response, re.DOTALL)
            json_arr_match = re.search(r'\[.*?\]', response, re.DOTALL)

            if json_arr_match and (not json_obj_match or len(json_arr_match.group(0)) > len(json_obj_match.group(0))):
                json_str = json_arr_match.group(0).strip()
                logger.debug("提取JSON数组")
            elif json_obj_match:
                json_str = json_obj_match.group(0).strip()
                logger.debug("提取JSON对象")
            else:
                json_str = response

        if not json_str or json_str.isspace():
            raise ValueError("提取的JSON内容为空")

        parse_attempts = [
            ("原始JSON", json_str),
            ("提取首个JSON", None),
            ("修复后的JSON", None),
        ]

        last_error = None

        for attempt_name, attempt_json in parse_attempts:
            if attempt_json is None:
                try:
                    if attempt_name == "提取首个JSON":
                        attempt_json = JSONParser._extract_first_json(json_str)
                    elif attempt_name == "修复后的JSON":
                        attempt_json = JSONParser._fix_json_string(json_str)
                    else:
                        continue
                except Exception as fix_error:
                    logger.debug(f"{attempt_name}时出错: {fix_error}")
                    continue

            try:
                data = json.loads(attempt_json)

                if attempt_name != "原始JSON":
                    logger.info(f"✅ 使用{attempt_name}成功解析")

                if expected_type == 'array' and not isinstance(data, list):
                    logger.warning(f"期望array但得到{type(data).__name__}")

                    raise ValueError(
                        f"[CONTENT_ERROR] 类型不匹配: 期望 array (文章列表)，但收到 {type(data).__name__}。"
                        f"LLM 可能误解了任务或只返回了部分内容（如只返回 images 字段）。"
                        f"需要重新从 PDF 提取完整的文章列表。"
                    )

                elif expected_type == 'object' and not isinstance(data, dict):
                    logger.warning(f"期望object但得到{type(data).__name__}")
                    if isinstance(data, list) and len(data) > 0:
                        return data[0]
                    raise ValueError(f"无法转换为object: {type(data).__name__}")

                return data

            except json.JSONDecodeError as e:
                last_error = e
                logger.debug(f"{attempt_name}解析失败: {e}")
                continue
            except Exception as e:
                last_error = e
                logger.debug(f"{attempt_name}处理出错: {e}")
                continue

        logger.error(f"JSON解析失败: {last_error}")
        logger.debug(f"尝试解析的内容: {json_str[:500]}...")
        raise ValueError(f"JSON解析失败: {last_error}")


logger = get_logger("table_extractor")

class TableExtractor:

    CAPTION_PATTERN = re.compile(
        r'(?:Table|TABLE|表)\s*\d+[\.\:。]?\s*.{0,80}',
        re.IGNORECASE
    )

    def extract_tables_from_pdf(
        self,
        pdf_bytes: bytes,
        batch_pages: Tuple[int, int],
        full_pdf: bool = False
    ) -> List[Dict]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"无法打开PDF: {e}")
            return []

        tables = []
        start_page, end_page = batch_pages

        if full_pdf:
            page_indices = range(start_page - 1, min(end_page, len(doc)))
            def actual_page_num(page_idx): return page_idx + 1
        else:
            page_indices = range(len(doc))
            def actual_page_num(page_idx): return start_page + page_idx

        for page_num in page_indices:
            actual_page = actual_page_num(page_num)
            page = doc[page_num]

            try:
                page_tables = page.find_tables()
            except Exception as e:
                logger.debug(f"页码 {actual_page}: find_tables 失败 - {e}")
                continue

            if not page_tables or not page_tables.tables:
                continue

            page_text = page.get_text("text")
            page_blocks = page.get_text("blocks")

            for tbl in page_tables.tables:
                try:
                    markdown = self._table_to_markdown(tbl)
                    if not markdown:
                        continue

                    bbox = list(tbl.bbox) if isinstance(tbl.bbox, (tuple, list)) else [tbl.bbox.x0, tbl.bbox.y0, tbl.bbox.x1, tbl.bbox.y1]
                    bbox_rect = fitz.Rect(bbox)

                    caption, anchor_before, anchor_after = self._extract_caption_and_anchor(
                        page, page_blocks, bbox_rect
                    )

                    table_info = {
                        'page': actual_page,
                        'markdown': markdown,
                        'caption': caption,
                        'anchor_before': anchor_before,
                        'anchor_after': anchor_after,
                        'bbox': bbox,
                        'belongs_to_article': None,
                        'inserted': False,
                    }

                    tables.append(table_info)
                    logger.debug(
                        f"页码 {actual_page}: 提取表格 "
                        f"caption='{caption[:40] if caption else '无'}'"
                    )

                except Exception as e:
                    logger.warning(f"页码 {actual_page}: 表格处理失败 - {e}")
                    continue

        doc.close()

        tables = self._merge_cross_page_tables(tables)

        logger.info(f"批次 {start_page}-{end_page}: 提取 {len(tables)} 个表格")
        return tables

    def _table_to_markdown(self, tbl) -> str:
        try:
            rows = tbl.extract()
            if not rows:
                return ""

            rows = [row for row in rows if any(cell for cell in row if cell and str(cell).strip())]
            if not rows:
                return ""

            def clean_cell(cell) -> str:
                if cell is None:
                    return ""
                text = str(cell).strip()
                text = text.replace('|', '\\|')
                text = re.sub(r'\s*\n\s*', ' ', text)
                return text

            cleaned_rows = [[clean_cell(cell) for cell in row] for row in rows]

            col_count = max(len(row) for row in cleaned_rows)

            cleaned_rows = [
                row + [''] * (col_count - len(row))
                for row in cleaned_rows
            ]

            lines = []
            lines.append('| ' + ' | '.join(cleaned_rows[0]) + ' |')
            lines.append('| ' + ' | '.join(['---'] * col_count) + ' |')
            for row in cleaned_rows[1:]:
                lines.append('| ' + ' | '.join(row) + ' |')

            return '\n'.join(lines)

        except Exception as e:
            logger.warning(f"表格转 Markdown 失败: {e}")
            return ""

    def _extract_caption_and_anchor(
        self,
        page: fitz.Page,
        blocks: list,
        table_bbox: fitz.Rect
    ) -> Tuple[Optional[str], str, str]:
        text_blocks = [
            b for b in blocks
            if b[6] == 0
            and b[4].strip()
        ]
        text_blocks.sort(key=lambda b: b[1])

        above_blocks = [b for b in text_blocks if b[3] <= table_bbox.y0 + 5]
        below_blocks = [b for b in text_blocks if b[1] >= table_bbox.y1 - 5]

        anchor_before = ""
        if above_blocks:
            recent = above_blocks[-2:]
            anchor_before = " ".join(b[4].strip()[:100] for b in recent)
            anchor_before = re.sub(r'\s+', ' ', anchor_before).strip()

        anchor_after = ""
        if below_blocks:
            recent = below_blocks[:2]
            anchor_after = " ".join(b[4].strip()[:100] for b in recent)
            anchor_after = re.sub(r'\s+', ' ', anchor_after).strip()

        caption = None

        for b in below_blocks[:3]:
            text = b[4].strip()
            m = self.CAPTION_PATTERN.search(text)
            if m:
                caption = m.group(0).strip()
                break

        if not caption:
            for b in reversed(above_blocks[-3:]):
                text = b[4].strip()
                m = self.CAPTION_PATTERN.search(text)
                if m:
                    caption = m.group(0).strip()
                    break

        return caption, anchor_before, anchor_after

    def _merge_cross_page_tables(self, tables: List[Dict]) -> List[Dict]:
        if len(tables) < 2:
            return tables

        merged = [tables[0]]
        for current in tables[1:]:
            prev = merged[-1]

            prev_cols = prev['markdown'].count('|') // max(prev['markdown'].count('\n'), 1)
            curr_cols = current['markdown'].count('|') // max(current['markdown'].count('\n'), 1)

            is_continuation = (
                current['page'] == prev['page'] + 1
                and not current['caption']
                and abs(prev_cols - curr_cols) <= 1
            )

            if is_continuation:
                curr_lines = current['markdown'].split('\n')
                if len(curr_lines) > 2:
                    continuation_rows = '\n'.join(curr_lines[2:])
                    prev['markdown'] = prev['markdown'] + '\n' + continuation_rows
                    prev['anchor_after'] = current['anchor_after']
                    logger.debug(
                        f"合并跨页表格: 页{prev['page']}-{current['page']}"
                    )
            else:
                merged.append(current)

        return merged

    def match_tables_to_articles(
        self,
        tables: List[Dict],
        articles: List[Dict]
    ) -> List[Dict]:
        for table in tables:
            table_page = table['page']
            caption = table.get('caption', '') or ''
            anchor_before = table.get('anchor_before', '') or ''

            best_match = None
            best_score = 0

            for article in articles:
                content = article.get('content', '') or ''
                page_start = article.get('page_start', 0) or 0
                page_end = article.get('page_end', 9999) or 9999
                score = 0

                if caption and len(caption) > 5:
                    caption_text = re.sub(r'^(?:Table|TABLE|表)\s*\d+[\.\:。]?\s*', '', caption).strip()
                    if caption_text and caption_text.lower() in content.lower():
                        score += 100

                if caption and len(caption) > 5:
                    caption_text = re.sub(r'^(?:Table|TABLE|表)\s*\d+[\.\:。]?\s*', '', caption).strip()
                    placeholder_pattern = re.compile(r'\[TABLE:[^\]]*\]', re.IGNORECASE)
                    for ph in placeholder_pattern.finditer(content):
                        ph_text = ph.group(0).lower()
                        if caption_text and any(kw.lower() in ph_text for kw in caption_text.split() if len(kw) > 3):
                            score += 80
                            break
                elif not caption:
                    if '[TABLE:' in content.upper() and page_start <= table_page <= page_end:
                        score += 30

                if anchor_before and len(anchor_before) > 10:
                    anchor_snippet = anchor_before[:30].strip()
                    if anchor_snippet and anchor_snippet.lower() in content.lower():
                        score += 50

                if page_start <= table_page <= page_end:
                    score += 10

                if score > best_score:
                    best_score = score
                    best_match = article

            if best_match and best_score > 0:
                table['belongs_to_article'] = best_match.get('title')
                logger.debug(
                    f"表格 '{caption[:30]}' → 文章 '{best_match.get('title', '')[:30]}' "
                    f"(score={best_score})"
                )
            else:
                logger.debug(f"表格 '{caption[:30]}' 无法匹配到文章")

        return tables

    def inject_tables_into_articles(
        self,
        articles: List[Dict],
        tables: List[Dict]
    ) -> List[Dict]:
        article_tables: Dict[str, List[Dict]] = {}
        for table in tables:
            title = table.get('belongs_to_article')
            if title:
                article_tables.setdefault(title, []).append(table)

        for article in articles:
            title = article.get('title', '')
            if title not in article_tables:
                continue

            content = article.get('content', '') or ''
            tbls = article_tables[title]

            tbls.sort(key=lambda t: t['page'])

            for table in tbls:
                caption = table.get('caption', '')
                markdown = table.get('markdown', '')
                anchor_before = table.get('anchor_before', '') or ''

                table_text = '\n\n'
                if caption:
                    table_text += f"**{caption}**\n\n"
                table_text += markdown + '\n\n'

                inserted = False
                placeholder_pattern = re.compile(r'\[TABLE:[^\]]*\]', re.IGNORECASE)
                placeholders = list(placeholder_pattern.finditer(content))
                if placeholders:
                    best_ph = None
                    best_ph_score = 0
                    caption_keywords = re.sub(r'^(?:Table|TABLE|表)\s*\d+[\.\:。]?\s*', '', caption).lower().split() if caption else []
                    for ph in placeholders:
                        ph_text = ph.group(0).lower()
                        score = sum(1 for kw in caption_keywords if kw in ph_text) if caption_keywords else 0
                        if not caption_keywords:
                            score = 1
                        if score > best_ph_score:
                            best_ph_score = score
                            best_ph = ph
                    if best_ph:
                        content = content[:best_ph.start()] + table_text.strip() + content[best_ph.end():]
                        inserted = True
                if anchor_before and len(anchor_before) > 10:
                    anchor_snippet = anchor_before[-40:].strip()
                    idx = content.lower().find(anchor_snippet.lower())
                    if idx != -1:
                        insert_pos = content.find('\n', idx + len(anchor_snippet))
                        if insert_pos == -1:
                            insert_pos = len(content)
                        content = content[:insert_pos] + table_text + content[insert_pos:]
                        inserted = True

                if not inserted:
                    content = content + table_text

                table['inserted'] = True
                logger.debug(
                    f"表格 '{caption[:30]}' 插入文章 '{title[:30]}' "
                    f"({'anchor定位' if inserted else '末尾追加'})"
                )

            article['content'] = content

        uninserted = [t for t in tables if not t.get('inserted') and t.get('belongs_to_article')]
        if uninserted:
            logger.warning(f"{len(uninserted)} 个表格未能插入")

        return articles
