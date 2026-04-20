
import fitz
import io
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PIL import Image
from core.logger import get_logger
from config import UserConfig

logger = get_logger("image_extractor")

class ImageExtractor:

    def __init__(self):
        pass

    def extract_batch_images(
        self,
        pdf_bytes: bytes,
        batch_pages: Tuple[int, int],
        output_dir: Path
    ) -> List[Dict]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"无法打开PDF字节流: {e}")
            return []

        images = []
        start_page, end_page = batch_pages

        total_images = 0
        images_with_bbox = 0
        images_without_bbox = 0

        logger.info(f"开始提取批次图片: 页码 {start_page}-{end_page}")

        for page_num in range(len(doc)):
            page = doc[page_num]
            actual_page = start_page + page_num

            page_rect = page.rect
            page_height = page_rect.height
            page_width = page_rect.width

            image_list = page.get_images(full=True)

            if not image_list:
                continue

            logger.debug(f"页码 {actual_page}: 发现 {len(image_list)} 张图片")

            for img_index, img in enumerate(image_list):
                xref = img[0]
                img_name = img[7]
                total_images += 1

                try:
                    rects = page.get_image_rects(xref)

                    if not rects:
                        logger.debug(f"页码 {actual_page}: 图片 {xref} 无法获取显示边界，使用原始提取")

                        try:
                            img_info = doc.extract_image(xref)
                            img_bytes = img_info["image"]
                            img_ext = img_info["ext"]
                        except RuntimeError as e:
                            error_msg = str(e)
                            if "bandwriter" in error_msg.lower() or "invalid" in error_msg.lower():
                                logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: 图片数据损坏，跳过 - {error_msg}")
                            else:
                                logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: 提取失败 - {error_msg}")
                            continue
                        except Exception as e:
                            logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: 未知错误 - {str(e)}")
                            continue

                        bbox = self._get_image_bbox(page, img_name, xref)

                        if img_ext == 'webp':
                            logger.warning(f"页码 {actual_page}: 跳过WebP格式图片")
                            continue

                        if bbox:
                            img_width_pts = bbox[2] - bbox[0]
                            img_height_pts = bbox[3] - bbox[1]

                            if self._is_fullpage_image(img_width_pts, img_height_pts, page_width, page_height):
                                width_ratio = img_width_pts / page_width if page_width > 0 else 0
                                height_ratio = img_height_pts / page_height if page_height > 0 else 0
                                logger.info(f"页码 {actual_page}: 跳过整页图片（回退方案）(宽{width_ratio:.1%}, 高{height_ratio:.1%})")
                                continue
                    else:
                        rect = rects[0]

                        zoom = 2.0
                        mat = fitz.Matrix(zoom, zoom)

                        bbox = [rect.x0, rect.y0, rect.x1, rect.y1]

                        if self._is_fullpage_image(rect.width, rect.height, page_width, page_height):
                            width_ratio = rect.width / page_width if page_width > 0 else 0
                            height_ratio = rect.height / page_height if page_height > 0 else 0
                            area_ratio = (rect.width * rect.height) / (page_width * page_height) if (page_width * page_height) > 0 else 0
                            logger.info(f"页码 {actual_page}: 跳过整页图片 (宽{width_ratio:.1%}, 高{height_ratio:.1%}, 面积{area_ratio:.1%})")
                            continue

                        try:
                            pix = page.get_pixmap(clip=rect, matrix=mat)
                            img_bytes = pix.tobytes("png")
                            img_ext = "png"
                        except RuntimeError as e:
                            error_msg = str(e)
                            if "bandwriter" in error_msg.lower() or "invalid" in error_msg.lower():
                                logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: 图片数据损坏（pixmap渲染失败），跳过 - {error_msg}")
                            else:
                                logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: pixmap渲染失败 - {error_msg}")
                            continue
                        except Exception as e:
                            logger.warning(f"页码 {actual_page}, 图片索引 {img_index}: pixmap渲染未知错误 - {str(e)}")
                            continue

                        logger.debug(f"页码 {actual_page}: 使用 pixmap 提取图片 {xref}，边界={bbox}")

                    if bbox:
                        images_with_bbox += 1
                    else:
                        images_without_bbox += 1

                    position_info = self._calculate_position(
                        bbox, page_height, page_width
                    )

                    img_filename = f"page_{actual_page:03d}_img_{img_index:03d}.{img_ext}"
                    img_path = output_dir / img_filename

                    with open(img_path, "wb") as f:
                        f.write(img_bytes)

                    try:
                        pil_img = Image.open(io.BytesIO(img_bytes))
                        img_width, img_height = pil_img.size
                    except:
                        img_width, img_height = 0, 0

                    img_data = {
                        'page': actual_page,
                        'path': str(img_path),
                        'format': img_ext,
                        'size': len(img_bytes),
                        'xref': xref,
                        'width': img_width,
                        'height': img_height,
                        'bbox': bbox,
                        'relative_y_top': position_info['y_top'],
                        'relative_y_bottom': position_info['y_bottom'],
                        'relative_x_left': position_info['x_left'],
                        'relative_x_right': position_info['x_right'],
                        'vertical_position': position_info['vertical_pos'],
                        'horizontal_position': position_info['horizontal_pos']
                    }

                    images.append(img_data)

                    logger.debug(
                        f"  提取图片 {img_index+1}: {img_filename}, "
                        f"位置={position_info['vertical_pos']}, "
                        f"大小={len(img_bytes)/1024:.1f}KB"
                    )

                except RuntimeError as e:
                    error_msg = str(e)
                    if "bandwriter" in error_msg.lower() or "invalid" in error_msg.lower():
                        logger.warning(
                            f"页码 {actual_page}, 图片索引 {img_index}: "
                            f"图片数据损坏（外层捕获），跳过 - {error_msg[:100]}"
                        )
                    else:
                        logger.error(
                            f"页码 {actual_page}, 图片索引 {img_index}: "
                            f"RuntimeError - {error_msg[:100]}"
                        )
                    continue
                except Exception as e:
                    logger.error(
                        f"页码 {actual_page}, 图片索引 {img_index}: "
                        f"提取失败 - {str(e)[:100]}"
                    )
                    continue

        doc.close()

        logger.info(f"批次提取完成: 共 {len(images)} 张图片")
        if total_images > 0 and images_without_bbox > 0:
            bbox_success_rate = images_with_bbox / total_images * 100
            logger.info(
                f"  位置信息: {images_with_bbox} 张有位置 ({bbox_success_rate:.1f}%), "
                f"{images_without_bbox} 张使用默认位置 ({images_without_bbox/total_images*100:.1f}%)"
            )
            if images_without_bbox / total_images > 0.3:
                logger.info(
                    f"  📌 说明: 部分PDF图片（如背景图、水印、内联图片）无位置信息是正常现象，"
                    f"系统已使用默认中心位置处理"
                )

        return images

    def _is_fullpage_image(
        self,
        img_width: float,
        img_height: float,
        page_width: float,
        page_height: float
    ) -> bool:
        if not UserConfig.IMAGE_ENABLE_FULLPAGE_FILTER:
            return False

        if page_width == 0 or page_height == 0:
            return False

        width_ratio = img_width / page_width
        height_ratio = img_height / page_height
        area_ratio = (img_width * img_height) / (page_width * page_height)

        page_aspect = page_width / page_height
        img_aspect = img_width / img_height if img_height > 0 else 1.0
        aspect_diff = abs(page_aspect - img_aspect)

        is_fullpage = (
            width_ratio > UserConfig.IMAGE_FULLPAGE_WIDTH_RATIO and
            height_ratio > UserConfig.IMAGE_FULLPAGE_HEIGHT_RATIO and
            area_ratio > UserConfig.IMAGE_FULLPAGE_AREA_RATIO and
            aspect_diff < UserConfig.IMAGE_FULLPAGE_ASPECT_DIFF
        )

        return is_fullpage

    def _get_image_bbox(self, page: fitz.Page, img_name: str, xref: int) -> Optional[List[float]]:
        try:
            bbox = page.get_image_bbox(img_name)
            if bbox:
                return [bbox.x0, bbox.y0, bbox.x1, bbox.y1]
        except AttributeError:
            logger.debug(f"PyMuPDF版本过旧，不支持get_image_bbox")
        except Exception as e:
            logger.debug(f"get_image_bbox失败 (name={img_name}): {e}")

        try:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") == 1:
                    if block.get("number") == xref or block.get("xref") == xref:
                        bbox = block.get("bbox")
                        if bbox:
                            return list(bbox)
        except Exception as e:
            logger.debug(f"通过文本块查找bbox失败: {e}")

        logger.debug(f"无法获取图片xref={xref}的bbox信息，将使用默认中心位置")
        return None

    def _calculate_position(
        self,
        bbox: Optional[List[float]],
        page_height: float,
        page_width: float
    ) -> Dict[str, any]:
        if not bbox or page_height == 0 or page_width == 0:
            return {
                'y_top': 0.5,
                'y_bottom': 0.5,
                'x_left': 0.5,
                'x_right': 0.5,
                'vertical_pos': 'middle',
                'horizontal_pos': 'center'
            }

        x0, y0, x1, y1 = bbox

        y_top_relative = y0 / page_height
        y_bottom_relative = y1 / page_height
        x_left_relative = x0 / page_width
        x_right_relative = x1 / page_width

        y_top_relative = max(0.0, min(1.0, y_top_relative))
        y_bottom_relative = max(0.0, min(1.0, y_bottom_relative))
        x_left_relative = max(0.0, min(1.0, x_left_relative))
        x_right_relative = max(0.0, min(1.0, x_right_relative))

        y_center = (y_top_relative + y_bottom_relative) / 2
        x_center = (x_left_relative + x_right_relative) / 2

        if y_center < 0.33:
            vertical_pos = 'top'
        elif y_center < 0.67:
            vertical_pos = 'middle'
        else:
            vertical_pos = 'bottom'

        if x_center < 0.33:
            horizontal_pos = 'left'
        elif x_center < 0.67:
            horizontal_pos = 'center'
        else:
            horizontal_pos = 'right'

        return {
            'y_top': round(y_top_relative, 4),
            'y_bottom': round(y_bottom_relative, 4),
            'x_left': round(x_left_relative, 4),
            'x_right': round(x_right_relative, 4),
            'vertical_pos': vertical_pos,
            'horizontal_pos': horizontal_pos
        }

    def save_metadata(self, images: List[Dict], output_path: str) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(images, f, ensure_ascii=False, indent=2)

            logger.info(f"图片元数据已保存: {output_path}")
        except Exception as e:
            logger.error(f"保存图片元数据失败: {e}")

    @staticmethod
    def build_image_metadata_table(images: List[Dict]) -> str:
        if not images:
            return ""

        lines = []
        lines.append("\n## 📷 Available Images Metadata\n")
        lines.append("| Image ID | Page | Width | Height | Format |")
        lines.append("|----------|------|-------|--------|--------|")

        for img in images:
            img_id = img.get('_temp_id', 'unknown')
            page = img.get('page', '?')

            width = img.get('width', '?')
            height = img.get('height', '?')

            if (width == '?' or height == '?') and img.get('bbox'):
                bbox = img['bbox']
                if bbox and len(bbox) >= 4:
                    width = int(bbox[2] - bbox[0])
                    height = int(bbox[3] - bbox[1])

            fmt = img.get('format', '?')
            lines.append(f"| {img_id} | {page} | {width}px | {height}px | {fmt} |")

        lines.append("\n**CRITICAL RULES FOR IMAGE USAGE:**")
        lines.append("1. Only use `image_id` values listed in the table above")
        lines.append("2. Each `image_id` can only be used ONCE across all articles")
        lines.append("3. If an image doesn't belong to any article, omit it entirely")
        lines.append("4. Image descriptions should be 2-3 sentences explaining what's shown\n")

        return '\n'.join(lines)

    @staticmethod
    def validate_image_descriptions(
        articles: List[Dict],
        images: List[Dict],
        page_range: str
    ) -> List[Dict]:
        if not images:
            return articles

        id_to_image = {img['_temp_id']: img for img in images}
        used_ids = set()

        try:
            start_page, end_page = map(int, page_range.split('-'))
        except:
            start_page, end_page = 1, 999999

        validated_count = 0
        discarded_count = 0

        validation_failures = {
            'L1_format': 0,
            'L2_not_exist': 0,
            'L3_duplicate': 0,
            'L4_page_range': 0
        }

        for article in articles:
            if 'images' not in article:
                article['images'] = []
                continue

            if not isinstance(article['images'], list):
                logger.warning(f"文章 '{article.get('title', 'Unknown')[:30]}...' 的images字段不是列表（类型: {type(article['images']).__name__}），已重置为空列表")
                article['images'] = []
                continue

            if not article['images']:
                article['images'] = []
                continue

            article_start = article.get('page_start', start_page)
            article_end = article.get('page_end', end_page)

            validated_images = []

            for img_ref in article['images']:
                image_id = img_ref.get('image_id')
                if not image_id or not isinstance(image_id, str):
                    discarded_count += 1
                    validation_failures['L1_format'] += 1
                    logger.debug(f"L1验证失败: image_id格式错误 - {img_ref}")
                    continue

                if image_id not in id_to_image:
                    discarded_count += 1
                    validation_failures['L2_not_exist'] += 1
                    logger.debug(f"L2验证失败: image_id不存在 - {image_id}")
                    continue

                if image_id in used_ids:
                    discarded_count += 1
                    validation_failures['L3_duplicate'] += 1
                    logger.debug(f"L3验证失败: image_id重复使用 - {image_id}")
                    continue

                original_img = id_to_image[image_id]
                img_page = original_img.get('page', 0)

                if not (article_start - 3 <= img_page <= article_end + 3):
                    discarded_count += 1
                    validation_failures['L4_page_range'] += 1
                    logger.debug(f"L4验证失败: 页面范围不匹配 - image_id={image_id}, img_page={img_page}, article_range={article_start}-{article_end}")
                    continue

                validated_img = original_img.copy()
                desc_value = img_ref.get('description', '')
                validated_img['description'] = str(desc_value).strip() if desc_value else ''
                rel_value = img_ref.get('relevance', '')
                validated_img['relevance'] = str(rel_value).strip() if rel_value else ''

                validated_images.append(validated_img)
                used_ids.add(image_id)
                validated_count += 1

            article['images'] = validated_images

        if validated_count + discarded_count > 0:
            print(f"      📊 图片描述验证: {validated_count}个通过, {discarded_count}个被丢弃")
            if discarded_count > 0:
                failure_details = []
                if validation_failures['L1_format'] > 0:
                    failure_details.append(f"格式错误:{validation_failures['L1_format']}")
                if validation_failures['L2_not_exist'] > 0:
                    failure_details.append(f"ID不存在:{validation_failures['L2_not_exist']}")
                if validation_failures['L3_duplicate'] > 0:
                    failure_details.append(f"ID重复:{validation_failures['L3_duplicate']}")
                if validation_failures['L4_page_range'] > 0:
                    failure_details.append(f"页面不匹配:{validation_failures['L4_page_range']}")
                print(f"      🔍 [Debug] 验证失败详情: {', '.join(failure_details)}")
            logger.info(f"图片验证统计: validated={validated_count}, discarded={discarded_count}")

        return articles

    @staticmethod
    def detect_undescribed_images(
        articles: List[Dict],
        images: List[Dict],
        page_range: str
    ) -> tuple:
        if not images:
            return 0, []

        described_ids = set()
        for article in articles:
            article_images = article.get('images', [])
            if not isinstance(article_images, list):
                logger.warning(f"detect_undescribed_images: 文章的images字段不是列表（类型: {type(article_images).__name__}）")
                continue
            for img in article_images:
                if isinstance(img, dict):
                    described_ids.add(img.get('image_id'))

        missing_count = len(images) - len(described_ids)
        missing_ids = [img['_temp_id'] for img in images if img['_temp_id'] not in described_ids]

        if missing_count > 0:
            print(f"      ⚠️ {missing_count} 张图片未被LLM描述: {', '.join(missing_ids[:5])}")
            if missing_count > 5:
                print(f"         （还有 {missing_count - 5} 张未列出）")
            logger.warning(f"批次{page_range}: {missing_count}张图片未被LLM描述，ID={missing_ids}")

        return missing_count, missing_ids

    def extract_batch_with_cache(
        self,
        pdf_bytes: bytes,
        batch_pages: Tuple[int, int],
        batch_dir: Path,
        cache_path: Path,
        image_cleaner
    ) -> List[Dict]:
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_images = json.load(f)

                if cached_images:
                    has_description = any(img.get('description') for img in cached_images if isinstance(img, dict))

                    if has_description:
                        print(f"      ✓ [缓存] 已存在 {len(cached_images)} 张图片（含AI描述），跳过提取")
                        return cached_images
                    else:
                        print(f"      ⚠️ [缓存] 图片元数据为旧格式（无AI描述），将重新提取...")

            except Exception as cache_error:
                print(f"      ⚠️ [缓存] 加载失败: {cache_error}，将重新提取")

        try:
            raw_images = self.extract_batch_images(
                pdf_bytes,
                batch_pages,
                batch_dir
            )

            from config import UserConfig
            cleaned_images, _ = image_cleaner.clean_images(raw_images, UserConfig)

            if cleaned_images:
                try:
                    self.save_metadata(cleaned_images, str(cache_path))
                    print(f"      🖼️  提取{len(raw_images)}张图片，清洗后{len(cleaned_images)}张")
                except Exception as save_error:
                    print(f"      ⚠️  保存图片元数据失败: {save_error}")
            else:
                print(f"      ℹ️  未提取到图片")

            return cleaned_images

        except Exception as img_error:
            print(f"      ⚠️  批次图片提取失败: {img_error}")
            print(f"      ℹ️  将继续文章提取，但不生成图片描述")
            return []

    @staticmethod
    def collect_all_images(
        batches: List[Dict],
        json_output_dir: Path,
        image_cleaner,
        image_base_dir: Path
    ) -> List[Dict]:
        all_images = []
        seen_images = {}

        print(f"正在从 {len(batches)} 个批次中提取图片...")

        batches_dir = json_output_dir / "batches"

        for idx, batch in enumerate(batches, 1):
            batch_image_dir = image_base_dir / f"batch_{idx:02d}"

            images_meta_path = batches_dir / f"images_batch_{idx:02d}.json"

            if images_meta_path.exists():
                try:
                    with open(images_meta_path, 'r', encoding='utf-8') as f:
                        cached_images = json.load(f)

                    if cached_images:
                        added_count = 0
                        duplicate_count = 0
                        replaced_count = 0

                        for img in cached_images:
                            page = img.get('page')
                            img_filename = Path(img.get('path', '')).name
                            img_key = (page, img_filename)

                            if img_key not in seen_images:
                                all_images.append(img)
                                seen_images[img_key] = len(all_images) - 1
                                added_count += 1
                            else:
                                existing_idx = seen_images[img_key]
                                existing_img = all_images[existing_idx]

                                new_is_meaningful = img.get('is_meaningful', False)
                                new_article_value = img.get('belongs_to_article', '')
                                new_has_article = bool(new_article_value and str(new_article_value).strip())
                                new_score = (2 if new_is_meaningful else 0) + (1 if new_has_article else 0)

                                existing_is_meaningful = existing_img.get('is_meaningful', False)
                                existing_article_value = existing_img.get('belongs_to_article', '')
                                existing_has_article = bool(existing_article_value and str(existing_article_value).strip())
                                existing_score = (2 if existing_is_meaningful else 0) + (1 if existing_has_article else 0)

                                if new_score > existing_score:
                                    all_images[existing_idx] = img
                                    replaced_count += 1
                                else:
                                    duplicate_count += 1

                        if duplicate_count > 0 or replaced_count > 0:
                            msg = f"  批次 {idx}/{len(batches)}: ✓ [缓存] 加载 {len(cached_images)} 张图片，添加 {added_count} 张"
                            if replaced_count > 0:
                                msg += f"（替换 {replaced_count} 张更有意义的版本）"
                            if duplicate_count > 0:
                                msg += f"（跳过 {duplicate_count} 张重复）"
                            print(msg)
                        else:
                            print(f"  批次 {idx}/{len(batches)}: ✓ [缓存] 加载 {len(cached_images)} 张图片")

                        continue

                except Exception as cache_error:
                    print(f"  批次 {idx}/{len(batches)}: ⚠️ [缓存] 加载失败: {cache_error}，将重新提取")

            try:
                extractor = ImageExtractor()

                raw_images = extractor.extract_batch_images(
                    batch['pdf_bytes'],
                    batch['pages'],
                    batch_image_dir
                )

                from config import UserConfig
                cleaned_images, _ = image_cleaner.clean_images(
                    raw_images,
                    UserConfig
                )

                print(f"  批次 {idx}/{len(batches)}: 提取 {len(raw_images)} 张, 清洗后 {len(cleaned_images)} 张")

                extractor.save_metadata(cleaned_images, str(images_meta_path))

                added_count = 0
                duplicate_count = 0
                replaced_count = 0

                for img in cleaned_images:
                    page = img.get('page')
                    img_filename = Path(img.get('path', '')).name
                    img_key = (page, img_filename)

                    if img_key not in seen_images:
                        all_images.append(img)
                        seen_images[img_key] = len(all_images) - 1
                        added_count += 1
                    else:
                        existing_idx = seen_images[img_key]
                        existing_img = all_images[existing_idx]

                        new_is_meaningful = img.get('is_meaningful', False)
                        new_article_value = img.get('belongs_to_article', '')
                        new_has_article = bool(new_article_value and str(new_article_value).strip())
                        new_score = (2 if new_is_meaningful else 0) + (1 if new_has_article else 0)

                        existing_is_meaningful = existing_img.get('is_meaningful', False)
                        existing_article_value = existing_img.get('belongs_to_article', '')
                        existing_has_article = bool(existing_article_value and str(existing_article_value).strip())
                        existing_score = (2 if existing_is_meaningful else 0) + (1 if existing_has_article else 0)

                        if new_score > existing_score:
                            all_images[existing_idx] = img
                            replaced_count += 1
                        else:
                            duplicate_count += 1

                if duplicate_count > 0 or replaced_count > 0:
                    msg = f"  批次 {idx}/{len(batches)}: 去重后添加 {added_count} 张"
                    if replaced_count > 0:
                        msg += f"（替换 {replaced_count} 张更有意义的版本）"
                    if duplicate_count > 0:
                        msg += f"（跳过 {duplicate_count} 张重复）"
                    print(msg)

            except Exception as batch_img_error:
                error_msg = f"批次 {idx} 图片处理失败: {str(batch_img_error)}"
                logger.error(error_msg)
                logger.exception("详细错误信息:")
                raise RuntimeError(error_msg) from batch_img_error

        print(f"\n✅ 图片提取完成: 共 {len(all_images)} 张（清洗后）\n")
        return all_images

class ImageCleaner:

    def __init__(self, config=None):
        self.config = config

    def clean_images(
        self,
        images: List[Dict],
        config=None
    ) -> Tuple[List[Dict], Dict[str, int]]:
        if config is None:
            config = self.config

        if config is None:
            config = self._get_default_config()

        cleaned = []
        stats = {
            'total': len(images),
            'filtered_by_format': 0,
            'filtered_by_size': 0,
            'filtered_by_dimensions': 0,
            'filtered_by_color': 0,
            'filtered_by_error': 0,
            'passed': 0
        }

        logger.info(f"开始清洗图片: 共 {len(images)} 张")

        for img_info in images:
            try:
                img_format = img_info.get('format', '').lower()
                exclude_formats = getattr(config, 'IMAGE_EXCLUDE_FORMATS', ['webp'])
                supported_formats = getattr(config, 'IMAGE_SUPPORTED_FORMATS', ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif'])
                if img_format in exclude_formats or (supported_formats and img_format not in supported_formats):
                    stats['filtered_by_format'] += 1
                    logger.debug(f"过滤（格式）: {Path(img_info['path']).name}")
                    continue

                if img_info.get('size', 0) < getattr(config, 'IMAGE_MIN_FILE_SIZE', 50 * 1024):
                    stats['filtered_by_size'] += 1
                    logger.debug(
                        f"过滤（文件大小）: {Path(img_info['path']).name}, "
                        f"{img_info['size']/1024:.1f}KB < {config.IMAGE_MIN_FILE_SIZE/1024}KB"
                    )
                    continue

                try:
                    img = Image.open(img_info['path'])
                except Exception as e:
                    stats['filtered_by_error'] += 1
                    logger.warning(f"无法打开图片 {img_info['path']}: {e}")
                    continue

                width, height = img.size
                if width < getattr(config, 'IMAGE_MIN_WIDTH', 800) or height < getattr(config, 'IMAGE_MIN_HEIGHT', 600):
                    stats['filtered_by_dimensions'] += 1
                    logger.debug(
                        f"过滤（尺寸）: {Path(img_info['path']).name}, "
                        f"{width}x{height} < {config.IMAGE_MIN_WIDTH}x{config.IMAGE_MIN_HEIGHT}"
                    )
                    continue

                color_richness = self._calculate_color_richness(img)
                if color_richness < config.IMAGE_MIN_COLOR_RICHNESS:
                    stats['filtered_by_color'] += 1
                    logger.debug(
                        f"过滤（色彩）: {Path(img_info['path']).name}, "
                        f"丰富度={color_richness:.2%} < {config.IMAGE_MIN_COLOR_RICHNESS:.2%}"
                    )
                    continue

                img_info['width'] = width
                img_info['height'] = height
                img_info['color_richness'] = round(color_richness, 4)

                cleaned.append(img_info)
                stats['passed'] += 1

            except Exception as e:
                stats['filtered_by_error'] += 1
                logger.error(f"处理图片时出错 {img_info.get('path', 'unknown')}: {e}")
                continue

        logger.info(
            f"清洗完成: 保留 {stats['passed']}/{stats['total']} 张图片 "
            f"({stats['passed']/stats['total']*100 if stats['total'] > 0 else 0:.1f}%)"
        )

        return cleaned, stats

    def _calculate_color_richness(self, img: Image.Image) -> float:
        try:
            if img.mode != 'RGB':
                img = img.convert('RGB')

            img_small = img.resize((50, 50), Image.Resampling.LANCZOS)

            pixels = np.array(img_small)

            pixels_reshaped = pixels.reshape(-1, 3)

            unique_colors = np.unique(pixels_reshaped, axis=0)
            num_unique_colors = len(unique_colors)

            max_possible_colors = 50 * 50
            richness = num_unique_colors / max_possible_colors

            richness = min(max(richness, 0.0), 1.0)

            return richness

        except Exception as e:
            logger.warning(f"计算色彩丰富度失败: {e}")
            return 0.5

    def print_stats(self, stats: Dict[str, int]) -> None:
        total = stats['total']
        passed = stats['passed']

        print("\n" + "=" * 60)
        print("图片清洗统计")
        print("=" * 60)
        print(f"总图片数: {total}")
        print(f"通过检查: {passed} ({passed/total*100 if total > 0 else 0:.1f}%)")
        print(f"\n过滤原因：")
        print(f"  - 格式不符: {stats['filtered_by_format']}")
        print(f"  - 文件过小: {stats['filtered_by_size']}")
        print(f"  - 尺寸过小: {stats['filtered_by_dimensions']}")
        print(f"  - 色彩单一: {stats['filtered_by_color']}")
        print(f"  - 处理错误: {stats['filtered_by_error']}")
        print("=" * 60 + "\n")

    def loose_filter_low_quality_images(
        self,
        images: List[Dict]
    ) -> Tuple[List[Dict], Dict[str, int]]:
        filtered = []
        stats = {
            'total': len(images),
            'filtered_by_dimensions': 0,
            'filtered_by_color': 0,
            'filtered_by_size': 0,
            'filtered_by_aspect_ratio': 0,
            'filtered_by_error': 0,
            'passed': 0
        }

        logger.info(f"开始宽松过滤: 共 {len(images)} 张图片")

        for img_info in images:
            try:
                file_size = img_info.get('size', 0)
                if file_size < UserConfig.IMAGE_LOOSE_MIN_FILE_SIZE:
                    stats['filtered_by_size'] += 1
                    logger.debug(
                        f"过滤（文件过小）: {Path(img_info['path']).name}, "
                        f"{file_size/1024:.1f}KB < {UserConfig.IMAGE_LOOSE_MIN_FILE_SIZE/1024:.1f}KB"
                    )
                    continue

                try:
                    img = Image.open(img_info['path'])
                except Exception as e:
                    stats['filtered_by_error'] += 1
                    logger.warning(f"无法打开图片 {img_info['path']}: {e}")
                    continue

                width, height = img.size
                if width < UserConfig.IMAGE_LOOSE_MIN_DIMENSION or height < UserConfig.IMAGE_LOOSE_MIN_DIMENSION:
                    stats['filtered_by_dimensions'] += 1
                    logger.debug(
                        f"过滤（分辨率过低）: {Path(img_info['path']).name}, "
                        f"{width}x{height} < {UserConfig.IMAGE_LOOSE_MIN_DIMENSION}x{UserConfig.IMAGE_LOOSE_MIN_DIMENSION}"
                    )
                    continue

                if height == 0:
                    stats['filtered_by_aspect_ratio'] += 1
                    logger.debug(f"过滤（高度为0）: {Path(img_info['path']).name}")
                    continue
                aspect_ratio = width / height
                max_ratio = UserConfig.IMAGE_LOOSE_MAX_ASPECT_RATIO
                min_ratio = 1 / max_ratio
                if aspect_ratio > max_ratio or aspect_ratio < min_ratio:
                    stats['filtered_by_aspect_ratio'] += 1
                    logger.debug(
                        f"过滤（宽高比异常）: {Path(img_info['path']).name}, "
                        f"ratio={aspect_ratio:.2f}"
                    )
                    continue

                color_richness = self._calculate_color_richness(img)
                if color_richness < UserConfig.IMAGE_LOOSE_MIN_COLOR_RICHNESS:
                    stats['filtered_by_color'] += 1
                    logger.debug(
                        f"过滤（纯色块）: {Path(img_info['path']).name}, "
                        f"丰富度={color_richness:.2%} < {UserConfig.IMAGE_LOOSE_MIN_COLOR_RICHNESS:.0%}"
                    )
                    continue

                img_info['width'] = width
                img_info['height'] = height
                img_info['color_richness'] = round(color_richness, 4)

                filtered.append(img_info)
                stats['passed'] += 1

            except Exception as e:
                stats['filtered_by_error'] += 1
                logger.error(f"处理图片时出错 {img_info.get('path', 'unknown')}: {e}")
                continue

        logger.info(
            f"宽松过滤完成: 保留 {stats['passed']}/{stats['total']} 张图片 "
            f"({stats['passed']/stats['total']*100 if stats['total'] > 0 else 0:.1f}%)"
        )

        return filtered, stats

    def _get_default_config(self):
        class DefaultConfig:
            IMAGE_MIN_FILE_SIZE = 50 * 1024
            IMAGE_MIN_WIDTH = 800
            IMAGE_MIN_HEIGHT = 600
            IMAGE_MIN_COLOR_RICHNESS = 0.20

            IMAGE_SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'bmp', 'tiff', 'tif']
            IMAGE_EXCLUDE_FORMATS = ['webp']

        return DefaultConfig()

"""
规则图片处理器 - 基于规则的图片选择、匹配和图注生成（无需Vision API）

适用场景：
- 大批量处理需要极致速度
- 图片描述不重要
- Vision API配额有限
- 网络带宽受限

核心功能：
1. 封面选择：基于图片质量评分（分辨率×色彩丰富度）
2. 图片匹配：基于页面邻近度和垂直位置
3. 图注生成：基于位置信息的描述

作者：Claude
创建时间：2025-12-16
"""

class RuleBasedCoverSelector:

    def select_cover(self, candidate_images: List[Dict], config) -> Optional[Dict]:
        if not candidate_images:
            logger.warning("没有候选封面图片")
            return None

        strategy = config.IMAGE_RULE_BASED_CONFIG['cover_selection']
        logger.info(f"封面选择策略: {strategy}, 候选数量: {len(candidate_images)}")

        if strategy == 'first_qualified':
            selected = candidate_images[0]
            logger.info(f"选择首张合格图片作为封面: {Path(selected['path']).name}")
            return selected

        elif strategy == 'largest':
            selected = max(
                candidate_images,
                key=lambda img: img.get('width', 0) * img.get('height', 0)
            )
            area = selected.get('width', 0) * selected.get('height', 0)
            logger.info(f"选择最大图片作为封面: {Path(selected['path']).name}, 面积: {area}px²")
            return selected

        elif strategy == 'highest_quality':
            def quality_score(img):
                area = img.get('width', 800) * img.get('height', 600)
                color_richness = img.get('color_richness', 0.5)
                return area * color_richness

            selected = max(candidate_images, key=quality_score)
            score = quality_score(selected)
            logger.info(f"选择最高质量图片作为封面: {Path(selected['path']).name}, 质量分: {score:.0f}")
            return selected

        else:
            logger.warning(f"未知策略 '{strategy}'，使用默认策略（首张）")
            return candidate_images[0]

class RuleBasedCaptionGenerator:

    def generate_caption(self, image: Dict, article: Dict, config) -> str:
        strategy = config.IMAGE_RULE_BASED_CONFIG['caption_strategy']

        if strategy == 'position_based':
            page_num = image.get('page', 0)
            vertical_pos = image.get('vertical_position', 'middle')

            pos_map = {
                'top': '顶部',
                'middle': '中部',
                'bottom': '底部'
            }
            pos_cn = pos_map.get(vertical_pos, '中部')

            caption = f"图片来源: 第{page_num}页{pos_cn}"
            logger.debug(f"生成位置图注: {caption}")
            return caption

        elif strategy == 'filename':
            filename = Path(image.get('path', '')).stem
            caption = f"图片: {filename}"
            logger.debug(f"生成文件名图注: {caption}")
            return caption

        elif strategy == 'none':
            logger.debug("图注策略为none，不生成图注")
            return ""

        else:
            logger.warning(f"未知图注策略 '{strategy}'，使用默认（无图注）")
            return ""

class RuleBasedImageMatcher:

    def match_images_to_articles(
        self,
        images: List[Dict],
        articles: List[Dict],
        config
    ) -> Dict[int, List[Dict]]:
        if not images or not articles:
            logger.info("没有图片或文章需要匹配")
            return {}

        strategy = config.IMAGE_RULE_BASED_CONFIG['matching_strategy']
        logger.info(f"图片匹配策略: {strategy}, 图片数: {len(images)}, 文章数: {len(articles)}")

        if strategy == 'page_proximity':
            return self._match_by_page_proximity(images, articles)
        elif strategy == 'vertical_position':
            matches = self._match_by_page_proximity(images, articles)
            for article_idx, imgs in matches.items():
                imgs.sort(key=lambda x: x.get('relative_position', 0.5))
                logger.debug(f"文章#{article_idx}: {len(imgs)}张图片已按垂直位置排序")
            return matches
        else:
            logger.warning(f"未知匹配策略 '{strategy}'，不进行匹配")
            return {}

    def _match_by_page_proximity(
        self,
        images: List[Dict],
        articles: List[Dict]
    ) -> Dict[int, List[Dict]]:
        matches = {i: [] for i in range(len(articles))}
        unmatched_images = []

        seen_paths = set()
        deduped_images = []
        for img in images:
            img_path = img.get('path', '')
            if img_path and img_path not in seen_paths:
                seen_paths.add(img_path)
                deduped_images.append(img)
            elif not img_path:
                deduped_images.append(img)

        for img in deduped_images:
            img_page = img.get('page', 0)
            if img_page == 0:
                logger.warning(f"图片缺少页码信息: {img.get('path', 'unknown')}")
                unmatched_images.append(img)
                continue

            best_article_idx = None
            best_score = 0

            for idx, article in enumerate(articles):
                start_page = article.get('start_page', 0)
                end_page = article.get('end_page', 999)

                if start_page <= img_page <= end_page:
                    score = 1.0
                elif abs(img_page - start_page) <= 1 or abs(img_page - end_page) <= 1:
                    score = 0.5
                else:
                    score = 0

                if score > best_score:
                    best_score = score
                    best_article_idx = idx

            if best_article_idx is not None and best_score > 0:
                img['insert_position'] = self._calculate_insert_position(img)
                matches[best_article_idx].append(img)
                logger.debug(
                    f"图片匹配: {Path(img['path']).name} -> 文章#{best_article_idx}, "
                    f"页码:{img_page}, 分数:{best_score}, 位置:{img['insert_position']}"
                )
            else:
                unmatched_images.append(img)
                logger.debug(f"图片未匹配: {Path(img['path']).name}, 页码:{img_page}")

        matched_count = sum(len(imgs) for imgs in matches.values())
        logger.info(
            f"匹配完成: {matched_count}/{len(images)} 张图片已匹配, "
            f"{len(unmatched_images)} 张未匹配"
        )

        return matches

    def _calculate_insert_position(self, image: Dict) -> str:
        relative_pos = image.get('relative_position', 0.5)
        vertical_pos = image.get('vertical_position', 'middle')

        if vertical_pos == 'top' or relative_pos < 0.33:
            return "start"
        elif vertical_pos == 'bottom' or relative_pos > 0.67:
            return "end"
        else:
            return "middle"

