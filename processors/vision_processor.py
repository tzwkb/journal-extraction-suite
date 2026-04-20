
import json
import base64
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import fitz
import requests
from core.logger import get_logger, ConsoleOutput, NetworkErrorHandler, UnifiedRetryPolicy
from config import UserConfig, Constants
from core.logger import JSONLWriter

logger = get_logger(__name__)

class VisionLLMClient:
    def __init__(self, api_key: str, api_url: str, model: str, log_dir: str = None, api_semaphore = None):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/').replace('/v1', '')
        self.model = model
        self.chat_endpoint = f"{self.api_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        self.log_dir = Path(log_dir) if log_dir else None
        self.api_semaphore = api_semaphore

    def call_vision(self, images: List[str], prompt: str, temperature: float = None, response_format: str = "json", max_retries: int = None, retry_delay: int = None) -> str:
        if temperature is None:
            temperature = UserConfig.VISION_API_TEMPERATURE
        if max_retries is None:
            max_retries = UserConfig.VISION_API_MAX_RETRIES
        if retry_delay is None:
            retry_delay = UserConfig.VISION_API_RETRY_DELAY

        if not hasattr(self, '_last_error_log_time'):
            self._last_error_log_time = {}

        parts = [{"text": prompt}]

        for img_path in images:
            try:
                with open(img_path, 'rb') as f:
                    img_bytes = f.read()

                if img_path.lower().endswith('.png'):
                    mime_type = "image/png"
                elif img_path.lower().endswith('.jpg') or img_path.lower().endswith('.jpeg'):
                    mime_type = "image/jpeg"
                else:
                    mime_type = "image/jpeg"

                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(img_bytes).decode('utf-8')
                    }
                })
            except Exception as e:
                logger.warning(f"无法加载图片 {img_path}: {e}")

        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": UserConfig.VISION_API_MAX_OUTPUT_TOKENS,
                "responseModalities": ["TEXT"]
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        from core.logger import NetworkErrorHandler
        import time

        headers = {"Content-Type": "application/json"}
        last_error = None

        for attempt in range(max_retries):
            try:

                if self.api_semaphore:
                    with self.api_semaphore:
                        response = requests.post(
                            self.chat_endpoint,
                            headers=headers,
                            json=payload,
                            timeout=UserConfig.VISION_API_TIMEOUT
                        )
                else:
                    response = requests.post(
                        self.chat_endpoint,
                        headers=headers,
                        json=payload,
                        timeout=UserConfig.VISION_API_TIMEOUT
                    )

                response.raise_for_status()

                result = response.json()
                if 'candidates' in result and result['candidates']:
                    response_text = result['candidates'][0]['content']['parts'][0]['text']

                    try:
                        total_img_size_mb = sum(
                            Path(img_path).stat().st_size / (1024 * 1024)
                            for img_path in images
                        )

                        log_data = {
                            "model": self.model,
                            "temperature": temperature,
                            "max_output_tokens": UserConfig.VISION_API_MAX_OUTPUT_TOKENS,
                            "num_images": len(images),
                            "image_paths": images,
                            "total_image_size_mb": round(total_img_size_mb, 2),
                            "prompt": prompt,
                            "prompt_length": len(prompt),
                            "endpoint": self.chat_endpoint.split('?')[0],
                            "response": response_text,
                            "response_length": len(response_text),
                            "full_api_response": result
                        }

                        log_file = self.log_dir / "vision.jsonl" if self.log_dir else Constants.LLM_LOG_VISION
                        JSONLWriter.append(
                            log_file,
                            log_data,
                            metadata={
                                "stage": "vision_api",
                                "status": "success",
                                "num_images": len(images)
                            }
                        )

                        logger.debug(f"✅ 已保存Vision成功日志到: {log_file.name}")
                    except Exception as log_error:
                        logger.warning(f"⚠️ 保存Vision成功日志失败: {log_error}")

                    if hasattr(UserConfig, 'VISION_API_REQUEST_INTERVAL') and UserConfig.VISION_API_REQUEST_INTERVAL > 0:
                        time.sleep(UserConfig.VISION_API_REQUEST_INTERVAL)

                    return response_text
                else:
                    raise Exception(f"Vision API响应格式错误: {result}")

            except Exception as e:
                last_error = e

                should_retry, error_type = NetworkErrorHandler.is_retryable_error(e)
                error_detail = str(e)[:200]

                partial_response = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        response_text = e.response.text[:500] if e.response.text else ''
                        error_detail = f"{e.response.status_code} - {response_text}"
                        partial_response = response_text
                    except Exception as extract_error:
                        logger.debug(f"无法提取Vision API响应内容: {extract_error}")
                elif 'response' in locals() and response is not None:
                    try:
                        partial_response = response.text[:500] if hasattr(response, 'text') else None
                        if partial_response:
                            logger.warning(f"Vision API超时但已接收部分响应: {len(partial_response)} 字符")
                    except Exception as extract_error:
                        logger.debug(f"无法提取Vision API部分响应: {extract_error}")

                if self.log_dir:
                    try:
                        total_img_size_mb = sum(
                            Path(img_path).stat().st_size / (1024 * 1024)
                            for img_path in images
                        )

                        error_log_file = self.log_dir / "vision_errors.jsonl"

                        error_log_data = {
                            "model": self.model,
                            "temperature": temperature,
                            "max_output_tokens": UserConfig.VISION_API_MAX_OUTPUT_TOKENS,
                            "num_images": len(images),
                            "image_paths": images,
                            "total_image_size_mb": round(total_img_size_mb, 2),
                            "prompt": prompt[:200] + "...",
                            "prompt_length": len(prompt),
                            "endpoint": self.chat_endpoint.split('?')[0],
                            "error": error_type,
                            "error_detail": error_detail,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "should_retry": should_retry,
                            "partial_response": partial_response
                        }
                        JSONLWriter.append(
                            error_log_file,
                            error_log_data,
                            metadata={
                                "stage": "vision_api",
                                "status": "retry_error",
                                "num_images": len(images)
                            }
                        )
                        logger.debug(f"已保存Vision错误日志到: {error_log_file.name}")
                    except Exception as log_e:
                        logger.debug(f"记录Vision API错误日志失败: {log_e}")

                can_retry, retry_reason = UnifiedRetryPolicy.should_continue_retry(
                    attempt=attempt,
                    max_retries=max_retries,
                    error_type=error_type if not should_retry else None
                )

                if should_retry and can_retry:
                    wait_time = UnifiedRetryPolicy.calculate_backoff_time_by_error_type(
                        error_type=error_type,
                        attempt=attempt,
                        base_delay=retry_delay
                    )

                    current_time = time.time()
                    log_key = f"{error_type}"
                    last_log_time = self._last_error_log_time.get(log_key, 0)
                    throttle_interval = UserConfig.VISION_API_LOG_THROTTLE_INTERVAL

                    should_log = (attempt < 10) or (current_time - last_log_time >= throttle_interval)

                    if should_log:
                        retry_msg = UnifiedRetryPolicy.get_retry_message(
                            attempt=attempt,
                            max_retries=max_retries,
                            wait_time=wait_time,
                            error_type=error_type
                        )
                        logger.warning(f"Vision API{retry_msg}")
                        logger.debug(f"详情: {error_detail}")
                        self._last_error_log_time[log_key] = current_time
                    elif attempt % 20 == 0:
                        logger.info(f"Vision API持续重试中... (第{attempt + 1}次，错误类型: {error_type})")

                    time.sleep(wait_time)
                    continue
                else:
                    if not should_retry:
                        logger.error(f"Vision API调用失败 ({error_type}，不可重试): {error_detail}")
                    else:
                        logger.error(f"Vision API调用失败: {retry_reason}")
                    break

        raise Exception(f"Vision API调用失败: {str(last_error)}")

COVER_IMAGE_SELECTION_PROMPT = """
You are analyzing the first page of a journal/magazine to select the best cover image.

INPUT:
- PDF Page 1 Screenshot: Full page image
- Extracted Images: {num_candidates} candidate images from page 1

Candidate Images:
{candidates_json}

TASK:
Identify which extracted image is most suitable as the cover image based on:
1. Size and prominence (larger, more central = better)
2. Visual appeal (professional, high quality)
3. Content relevance (represents the journal theme)
4. Position (CRITICAL: typically immediately below the title/header, upper-middle area preferred)
5. **Special theme recognition**:
   - Military journals: Look for weapons, vehicles, soldiers, combat scenes, defense equipment
   - Academic journals: Look for charts, diagrams, portraits, laboratory scenes
   - News magazines: Look for people, events, headlines, current affairs

RETURN JSON:
{{{{
  "best_cover_image": {{{{
    "image_id": "img_xxx",
    "reason": "Why this is the best cover (position, size, content, theme)",
    "confidence": 0.0-1.0,
  }}}},
  "rejected_images": [
    {{{{
      "image_id": "img_yyy",
      "reason": "Why rejected (e.g., 'Small decorative icon', 'Background pattern')"
    }}}}
  ]
}}}}

ENHANCED RULES:
- **FIRST image is PDF page 1 rendering** - use it as reference for orientation detection
- **VISUALLY compare** extracted images with PDF page to detect upside-down images
- Position matters MORE than size: centered/upper-middle (y: 0.2-0.6) beats large but off-center
- For military/defense journals: Accept aggressive imagery, weapons, uniforms, tactical scenes
- The cover image is often the FIRST major image below the title banner
- Lower confidence threshold acceptable (0.3+) if image is clearly positioned as cover
- Ignore: small logos (<100px), page numbers, decorative borders, background textures
- Prefer images that occupy >10% of the page area (lowered from 20%)
- If multiple candidates, prioritize position over size
"""

COMBINED_IMAGE_ANNOTATION_AND_MATCHING_PROMPT = """
You are analyzing images from a journal PDF. Your task: provide descriptions AND match images to articles.

INPUT:
- PDF Pages: Pages {page_range}
- Extracted Images: {num_images} images
- Articles in this batch: {num_articles} articles

Image Metadata:
{images_table}

Articles List:
{articles_json}

DUAL TASK:
For EACH image, provide:

**PART 1: IMAGE DESCRIPTION**
1. **description**: Check for native PDF captions first (e.g., "Figure 1: ...", "图1：..."). If found, use it verbatim. Otherwise, generate 2-3 sentences.
2. **relevance**: How this relates to journal content
3. **is_meaningful**: true/false - informational value
4. **has_native_caption**: true/false - whether you found a native caption (see rules below)
5. **needs_flip**: true/false - whether the image is upside down and needs 180° rotation

📌 **CRITICAL: HOW TO DETECT NATIVE CAPTIONS**
The FIRST image you receive is the **PDF page rendering** (full page screenshot). Use it to find native captions:

✅ **Native caption = Text on PDF page near the image** (set has_native_caption: true)
- Look at the PDF page rendering (first image)
- Find text near/below/above the extracted image's location
- Common patterns: "Figure 1:", "Fig. 2:", "图1：", "Photo:", etc.
- Caption text is ON THE PAGE, not inside the image itself

❌ **NOT native caption** (set has_native_caption: false)
- Text INSIDE the extracted image itself (e.g., full-page screenshots containing "Figure 1:" as part of the page layout)
- If the extracted image contains caption text but it's part of a full-page screenshot → NOT native
- Pure image content (photos, diagrams) without surrounding text on PDF page → generate description

**Examples**:
- PDF page shows a photo, and below it says "Figure 3: Soldiers in training" → has_native_caption: true, use that text
- Extracted image is a pure photo (no text), PDF page has no caption near it → has_native_caption: false, generate description
- Extracted image is a full-page screenshot containing "Figure 1:" → has_native_caption: false (it's a full-page duplicate)

**PART 2: ARTICLE MATCHING** (new)
6. **belongs_to_article**: Title of the article this image belongs to (from Articles List above), or null if unclear
7. **anchor_text**: A unique sentence/phrase from the article text where this image should be inserted (must be exact text from the article), or null
8. **insert_position**: "before" or "after" the anchor_text, or null

⭐ PRIORITY: MATCHING GUIDELINES
**CRITICAL: Every meaningful image (is_meaningful=true) MUST be matched to an article!**
- Match images to articles based on:
  * Page proximity (images near article content)
  * Topic relevance (technical diagrams → technical articles)
  * Visual clues (captions mentioning article topics)
  * Image position (top/middle/bottom of page vs article start/end)
- For **anchor_text**: Find a specific sentence in the article where the image fits naturally
  * Good: "The reactor design incorporates three main cooling loops."
  * Bad: "reactor" (too vague) or invented text not in the article
- **IMPORTANT**:
  * If is_meaningful=true → belongs_to_article MUST NOT be null (choose the most likely article)
  * If is_meaningful=false → belongs_to_article MUST be null
- Only decorative images (is_meaningful=false) should have belongs_to_article: null

🎯 BACKGROUND/DECORATIVE DETECTION:
**CRITICAL: Carefully identify decorative/meaningless images**
Set is_meaningful=false for:
- Page headers/footers, borders, watermarks, logos
- Background patterns, solid color blocks, textures, gradients
- Repeated decorative elements
- **Pure background colors**: Solid colors, color blocks, shading (no information content)
- **Texture patterns**: Repeated textures, fabric patterns, noise patterns
- **Decorative borders**: Page margins, frames, dividers, corner decorations
- **Abstract backgrounds**: Blurred backgrounds, bokeh effects, gradient fills
- **Partial crops of larger decorative elements**: Edge fragments, cut-off patterns

📝 **TEXT-HEAVY IMAGES (NEW RULE)**:
**CRITICAL: Filter out images with high text density (likely article pages/full-page text screenshots)**

Set is_meaningful=false if the image contains:
- **Large blocks of paragraph text** (multiple lines of body text)
- **High text-to-image ratio** (text occupies >50% of image area)
- **Typical article/page layout** (headers, paragraphs, columns of text)

✅ **Keep as meaningful** (is_meaningful=true):
- Pure visual content: photos, diagrams, charts, illustrations with minimal/no text
- Technical diagrams with labels/annotations (text <30% of area)
- Infographics with integrated text (text is part of visual design, not body paragraphs)
- Images with captions only (short text below/above image)

❌ **Filter out** (is_meaningful=false):
- Article pages (full text with paragraphs)
- Page screenshots containing body text
- Text documents with no visual elements
- Mixed content where text dominates (>50% text coverage)

**Examples**:
- Photo of soldiers + short caption "Figure 3: Training exercise" → is_meaningful=true (visual content dominates)
- Technical diagram with arrows and labels → is_meaningful=true (diagram is primary, text is annotations)
- Full page showing 3 paragraphs of article text + small image → is_meaningful=false (text dominates)
- Screenshot containing article title, subtitle, and body paragraphs → is_meaningful=false (page layout with text)

**HOW TO IDENTIFY DECORATIVE IMAGES**:
1. Does it contain ZERO informational content? (text, diagrams, photos, charts)
2. Is it just a color/texture/pattern with no meaningful visual elements?
3. Would removing it from the article affect understanding? (If NO → decorative)
4. Is it a background element or page decoration?
5. Does it have extremely simple visual content? (single color, simple gradient, plain texture)

**EXAMPLES OF DECORATIVE IMAGES TO MARK is_meaningful=false**:
- Solid colored rectangles (page backgrounds)
- Repeated dot patterns, line patterns, texture fills
- Page border decorations, corner ornaments
- Watermark backgrounds, semi-transparent overlays
- Cropped edges of background images (partial texture fragments)

**IF UNSURE**: When in doubt, check:
- Does the image ADD information to the article? → is_meaningful=true
- Is it PURELY decorative/aesthetic? → is_meaningful=false

RETURN JSON ARRAY:
[
  {{{{
    "image_id": "image_1",
    "description": "Figure 2: Cross-section diagram of pressurized water reactor showing primary and secondary cooling loops",
    "relevance": "Technical illustration for nuclear engineering content",
    "is_meaningful": true,
    "has_native_caption": true,
    "belongs_to_article": "Advanced Reactor Design Principles",
    "anchor_text": "The primary cooling system operates at high pressure to prevent boiling.",
    "insert_position": "after"
  }}}},
  {{{{
    "image_id": "image_2",
    "description": "Photo of military personnel in desert camouflage uniforms conducting field training",
    "relevance": "Illustrates training exercises mentioned in article",
    "is_meaningful": true,
    "has_native_caption": false,
    "belongs_to_article": "Joint Task Force Training Outcomes",
    "anchor_text": "Teams completed advanced tactical maneuvers in simulated combat conditions.",
    "insert_position": "before"
  }}}},
  {{{{
    "image_id": "image_3",
    "description": "Small publisher logo with blue and white color scheme",
    "relevance": "Branding element",
    "is_meaningful": false,
    "has_native_caption": false,
    "belongs_to_article": null,
    "anchor_text": null,
    "insert_position": null
  }}}}
]

CRITICAL RULES:
- **FIRST image is PDF page rendering** (correct orientation) - use it as visual reference for finding native captions on the page (look for text near each image's location)
- **Native captions are ON THE PDF PAGE, not inside extracted images**:
  * Look at the PDF page rendering to find caption text near each image
  * Caption text inside an extracted image does NOT count as native caption
  * Only set has_native_caption=true if caption text appears on the page around the image
- Only set needs_flip=true if the image is clearly 180° upside down compared to PDF page
- Do NOT set needs_flip=true for images rotated 90° or 270°
- **EVERY meaningful image MUST be matched to an article** (belongs_to_article cannot be null if is_meaningful=true)
- Match images to articles carefully - use page position and content relevance
- Provide exact anchor_text from the article (copy-paste, don't invent)
- Use exact image_id from input table
- Decorative images: is_meaningful=false, belongs_to_article=null
"""

class VisionImageProcessor:

    def __init__(self, llm_client, pdf_path: str, temp_dir: str = None):
        import uuid
        import atexit

        self.llm_client = llm_client
        self.pdf_path = pdf_path
        self.pdf_doc = fitz.open(pdf_path)

        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            self.temp_dir = Path(f"temp_page_images_{uuid.uuid4().hex[:8]}")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        atexit.register(self._cleanup_temp_dir)

        logger.info(f"VisionImageProcessor initialized for: {Path(pdf_path).name} (temp_dir: {self.temp_dir})")

    def select_cover_image(
        self,
        cover_page_images: List[Dict]
    ) -> Optional[Dict]:
        if not cover_page_images:
            logger.warning("No cover page images provided")
            return None

        for i, img in enumerate(cover_page_images):
            img['_temp_id'] = f"img_{i}"

        logger.info(f"Selecting best cover from {len(cover_page_images)} candidates...")

        logger.info("=" * 60)
        logger.info("封面候选图片详细信息:")
        for i, img in enumerate(cover_page_images, 1):
            logger.info(
                f"  候选{i}: "
                f"尺寸={img.get('width', 0)}x{img.get('height', 0)}px, "
                f"位置={img.get('vertical_position', 'N/A')}-{img.get('horizontal_position', 'N/A')}, "
                f"文件大小={img.get('size', 0) / 1024:.1f}KB, "
                f"路径={img.get('path', 'N/A')}"
            )
            if 'bbox' in img and img['bbox']:
                bbox = img['bbox']
                logger.info(f"       bbox={bbox}")
        logger.info("=" * 60)

        try:
            page_image_path = self._pdf_page_to_image(page_num=1)

            candidates_json = json.dumps([
                {
                    "image_id": img.get('_temp_id', f"img_{i}"),
                    "size": f"{img['width']}x{img['height']}",
                    "position": f"{img.get('vertical_position')}-{img.get('horizontal_position')}",
                    "file_size": f"{img.get('size', 0) / 1024:.1f}KB"
                }
                for i, img in enumerate(cover_page_images)
            ], indent=2)

            prompt = COVER_IMAGE_SELECTION_PROMPT.format(
                num_candidates=len(cover_page_images),
                candidates_json=candidates_json
            )

            image_paths = [page_image_path] + [img['path'] for img in cover_page_images]

            result = self._call_vision_api(
                images=image_paths,
                prompt=prompt
            )

            best_id = result.get('best_cover_image', {}).get('image_id')
            confidence = result.get('best_cover_image', {}).get('confidence', 0)
            reason = result.get('best_cover_image', {}).get('reason', '')

            if best_id is None:
                logger.warning(
                    f"AI判断所有候选图片都不适合做封面 (confidence: {confidence:.2f})\n"
                    f"   原因: {reason[:100] if reason else '未提供'}\n"
                    f"   → 使用兜底策略：选择最大图片"
                )
                if cover_page_images:
                    largest_img = max(cover_page_images, key=lambda x: x.get('width', 0) * x.get('height', 0))
                    largest_img['cover_metadata'] = {
                        'confidence': 0.0,
                        'reason': f"兜底策略：AI未选择，自动选择最大图片 ({largest_img.get('width')}x{largest_img.get('height')})"
                    }
                    logger.info(f"✓ 兜底选择: {largest_img.get('_temp_id', 'unknown')} (尺寸: {largest_img.get('width')}x{largest_img.get('height')})")
                    return largest_img
                return None

            cover_img = next(
                (img for img in cover_page_images if img.get('_temp_id') == best_id),
                None
            )

            if not cover_img:
                logger.warning(f"AI选择的封面图片 {best_id} 在候选列表中未找到")
                return None

            if confidence >= UserConfig.VISION_COVER_CONFIDENCE_HIGH:
                cover_img['cover_metadata'] = result['best_cover_image']
                logger.info(f"✓ Selected cover: {best_id} (confidence: {confidence:.2f}, 高置信度)")
                return cover_img

            elif confidence >= UserConfig.VISION_COVER_CONFIDENCE_LOW:
                cover_img['cover_metadata'] = result['best_cover_image']
                logger.warning(
                    f"封面置信度中等: {confidence:.2f} ({UserConfig.VISION_COVER_CONFIDENCE_LOW}-{UserConfig.VISION_COVER_CONFIDENCE_HIGH}), 仍然采用\n"
                    f"   原因: {reason[:100] if reason else '未提供'}"
                )
                logger.info(f"✓ Selected cover: {best_id} (confidence: {confidence:.2f}, 中等置信度)")
                return cover_img

            else:
                logger.warning(
                    f"封面候选图片 {best_id} 置信度过低: {confidence:.2f} < 0.3\n"
                    f"   原因: {reason[:100] if reason else '未提供'}\n"
                    f"   → 使用兜底策略：选择最大图片"
                )
                if cover_page_images:
                    largest_img = max(cover_page_images, key=lambda x: x.get('width', 0) * x.get('height', 0))
                    largest_img['cover_metadata'] = {
                        'confidence': confidence,
                        'reason': f"兜底策略：置信度过低({confidence:.2f})，选择最大图片"
                    }
                    logger.info(f"✓ 兜底选择: 最大图片 (尺寸: {largest_img.get('width')}x{largest_img.get('height')})")
                    return largest_img
                return None

        except Exception as e:
            logger.error(f"Cover image selection failed: {e}")
            return None

    def annotate_and_match_images_for_batch(
        self,
        pdf_bytes: bytes,
        images: List[Dict],
        page_range: str,
        articles: List[Dict]
    ) -> List[Dict]:
        if not images:
            logger.info(f"No images to annotate for pages {page_range}")
            return []

        if not articles:
            logger.warning(f"No articles provided for matching, falling back to annotation-only")
            return images

        logger.info(f"Annotating and matching {len(images)} images for pages {page_range}...")

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from config import UserConfig

            for idx, img in enumerate(images, 1):
                img['_temp_id'] = f"image_{idx}"

            images_per_group = UserConfig.VISION_API_IMAGES_PER_GROUP
            image_groups = []

            page_to_images = {}
            for img in images:
                page = img.get('page', 1)
                if page not in page_to_images:
                    page_to_images[page] = []
                page_to_images[page].append(img)

            for page_num, page_images in sorted(page_to_images.items()):
                for i in range(0, len(page_images), images_per_group):
                    group = page_images[i:i + images_per_group]
                    image_groups.append({
                        'page': page_num,
                        'images': group
                    })

            articles_simplified = []
            for article in articles:
                articles_simplified.append({
                    "title": article.get('title', ''),
                    "content_preview": article.get('content', '')[:500] + "..." if len(article.get('content', '')) > 500 else article.get('content', ''),
                    "page_start": article.get('start_page'),
                    "page_end": article.get('end_page')
                })
            articles_json = json.dumps(articles_simplified, ensure_ascii=False, indent=2)

            def process_image_group(group_info):
                group_images = group_info['images']
                page_num = group_info['page']

                try:
                    for idx, img in enumerate(group_images):
                        if not isinstance(img, dict):
                            logger.error(f"第{page_num}页图片{idx}不是字典类型: {type(img)}")
                            return group_images, []

                        if 'path' not in img:
                            logger.error(f"第{page_num}页图片{idx}缺少'path'字段")
                            logger.error(f"  - 实际的键: {list(img.keys())}")
                            logger.error(f"  - 图片数据: {str(img)[:200]}")
                            return group_images, []

                    images_table = self._build_image_metadata_table(group_images)

                    prompt = COMBINED_IMAGE_ANNOTATION_AND_MATCHING_PROMPT.format(
                        page_range=f"{page_num}",
                        num_images=len(group_images),
                        num_articles=len(articles),
                        images_table=images_table,
                        articles_json=articles_json
                    )

                    try:
                        page_image_path = self._pdf_page_to_image(page_num)
                        page_image_paths = [page_image_path]
                    except Exception as e:
                        logger.warning(f"Failed to convert page {page_num} to image: {e}")
                        page_image_paths = []

                    all_image_paths = page_image_paths + [img.get('path', '') for img in group_images if img.get('path')]

                    result = self._call_vision_api(
                        images=all_image_paths,
                        prompt=prompt,
                        expected_type='array'
                    )

                    return group_images, result

                except json.JSONDecodeError as e:
                    logger.error(f"第{page_num}页图片组JSON解析失败: {str(e)}")
                    logger.error(f"  - 错误位置: 第{e.lineno}行, 第{e.colno}列")
                    logger.error(f"  - 错误消息: {e.msg}")
                    logger.error(f"  - 可能原因: Vision API响应被截断或格式错误")
                    return group_images, []

                except TimeoutError as e:
                    logger.error(f"第{page_num}页图片组处理超时: {str(e)}")
                    logger.error(f"  - 图片数量: {len(group_images)}")
                    logger.error(f"  - 提示词长度: {len(prompt)}字符")
                    logger.error(f"  - 建议: 考虑减少VISION_API_TIMEOUT或简化提示词")
                    return group_images, []

                except ConnectionError as e:
                    logger.error(f"第{page_num}页图片组网络连接失败: {str(e)}")
                    logger.error(f"  - 错误类型: 网络连接问题")
                    logger.error(f"  - 建议: 检查网络连接或API服务状态")
                    return group_images, []

                except Exception as e:
                    import traceback
                    error_type = type(e).__name__
                    logger.error(f"第{page_num}页图片组处理失败 [{error_type}]: {str(e)}")
                    logger.error(f"  - 图片数量: {len(group_images)}")

                    try:
                        paths = [img.get('path', '<无路径>') for img in group_images if isinstance(img, dict)]
                        logger.error(f"  - 图片路径: {paths}")
                    except Exception as path_error:
                        logger.error(f"  - 图片路径: <无法提取路径: {path_error}>")

                    logger.error(f"  - 完整堆栈:\n{traceback.format_exc()}")
                    return group_images, []

            max_workers = min(UserConfig.VISION_API_MAX_WORKERS, len(image_groups))

            if len(image_groups) > 1:
                ConsoleOutput.info(f"使用 {max_workers} 个线程并发处理 {len(image_groups)} 组图片...", 3)

            all_results = {}

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_image_group, group): group for group in image_groups}

                for future in as_completed(futures):
                    group_images, result = future.result()

                    if result is None or not isinstance(result, list):
                        result_type = type(result).__name__ if result is not None else 'None'
                        logger.warning(f"Vision API returned invalid result type ({result_type}), using empty list")
                        result = []

                    valid_results = []
                    for idx, item in enumerate(result):
                        if not isinstance(item, dict):
                            logger.error(f"Vision API结果第{idx}项不是字典: {type(item).__name__}")
                            logger.error(f"  - 内容: {str(item)[:200]}")
                            continue

                        if 'image_id' not in item:
                            logger.warning(f"Vision API结果第{idx}项缺少image_id字段")
                            logger.warning(f"  - 实际的键: {list(item.keys())}")
                            continue

                        valid_results.append(item)

                    result_map = {item.get('image_id'): item for item in valid_results}

                    for img in group_images:
                        img_id = img.get('_temp_id')
                        if img_id and img_id in result_map:
                            all_results[img_id] = result_map[img_id]

            annotated_count = 0
            matched_count = 0

            for img in images:
                img_id = img.get('_temp_id')
                if img_id and img_id in all_results:
                    annotation = all_results[img_id]

                    img['description'] = annotation.get('description', '')
                    img['relevance'] = annotation.get('relevance', '')
                    img['is_meaningful'] = annotation.get('is_meaningful', True)
                    img['has_native_caption'] = annotation.get('has_native_caption', False)
                    annotated_count += 1

                    img['belongs_to_article'] = annotation.get('belongs_to_article')
                    img['anchor_text'] = annotation.get('anchor_text')
                    img['insert_position'] = annotation.get('insert_position')

                    if img.get('belongs_to_article') is not None:
                        matched_count += 1

            ConsoleOutput.vision_result(annotated_count, len(images), matched_count, 3)
            logger.info(f"Annotated {annotated_count}/{len(images)} images, matched {matched_count} to articles for pages {page_range}")

            for img in images:
                img.pop('_temp_id', None)

            return images

        except Exception as e:
            logger.error(f"Combined image annotation and matching failed for pages {page_range}: {e}")
            logger.warning(f"Returning images without Vision API annotations due to error")
            for img in images:
                img.pop('_temp_id', None)
                if 'description' not in img:
                    img['description'] = ''
                if 'relevance' not in img:
                    img['relevance'] = ''
                if 'is_meaningful' not in img:
                    img['is_meaningful'] = True
            return images

    def _build_image_metadata_table(self, images: List[Dict]) -> str:
        if not images:
            return "(No images)"

        lines = [
            "| Image ID | Page | Position | Size | Format |",
            "|----------|------|----------|------|--------|"
        ]

        for img in images:
            img_id = img.get('_temp_id', 'unknown')
            page = img.get('page', 'N/A')
            position = f"{img.get('vertical_position', 'N/A')}-{img.get('horizontal_position', 'N/A')}"
            width = img.get('width', 0)
            height = img.get('height', 0)
            size = f"{width}x{height}" if width and height else "N/A"
            img_format = img.get('format', 'N/A').upper()

            lines.append(f"| {img_id} | {page} | {position} | {size} | {img_format} |")

        return "\n".join(lines)

    def _pdf_page_to_image(self, page_num: int, dpi: int = None) -> str:
        if dpi is None:
            dpi = UserConfig.VISION_PAGE_SCREENSHOT_DPI

        page = self.pdf_doc[page_num - 1]
        pix = page.get_pixmap(dpi=dpi)

        temp_path = self.temp_dir / f"page_{page_num}.png"

        try:
            pix.save(str(temp_path))
            return str(temp_path)
        finally:
            pix = None

    def _call_vision_api(
        self,
        images: List[str],
        prompt: str,
        expected_type: str = 'object'
    ):
        from core.pdf_utils import JSONParser
        import traceback

        logger.debug(f"Vision API 请求: {len(images)}张图片, 提示词长度={len(prompt)}字符, 期望类型={expected_type}")

        def vision_fix_callback(_, fix_prompt):
            return self.llm_client.call_vision(
                images=images,
                prompt=fix_prompt,
                temperature=0.0,
                response_format="json"
            )

        try:
            response = self.llm_client.call_vision(
                images=images,
                prompt=prompt,
                temperature=0.1,
                response_format="json"
            )

            logger.debug(f"Vision API 原始响应长度: {len(response)}字符")
            if len(response) > 0:
                preview_start = response[:200] if len(response) > 200 else response
                preview_end = response[-200:] if len(response) > 200 else ""
                logger.debug(f"响应开头: {preview_start}")
                if preview_end:
                    logger.debug(f"响应结尾: {preview_end}")

            result = JSONParser.parse_with_llm_retry(
                initial_response=response,
                llm_fix_callback=vision_fix_callback,
                pdf_bytes=None,
                expected_type=expected_type,
                max_retries=999,
                retry_on_callback_error=True
            )

            logger.debug(f"JSON解析结果类型: {type(result).__name__}")
            if isinstance(result, dict):
                logger.debug(f"解析结果是字典，键: {list(result.keys())[:10]}")
            elif isinstance(result, list):
                logger.debug(f"解析结果是列表，长度: {len(result)}")
                if len(result) > 0:
                    first_item = result[0]
                    logger.debug(f"第一个元素类型: {type(first_item).__name__}")
                    if isinstance(first_item, dict):
                        logger.debug(f"第一个元素的键: {list(first_item.keys())}")
            else:
                logger.warning(f"解析结果是意外类型: {type(result).__name__}, 值: {str(result)[:200]}")

            if expected_type == 'array' and isinstance(result, dict):
                logger.warning("Vision API 返回单个对象而非数组，自动包装成数组")
                result = [result]

            return result

        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Vision API调用失败 [{error_type}]: {str(e)}")

            if 'response' in locals():
                preview = response[:1000] if len(response) > 1000 else response
                logger.error(f"原始响应预览（前1000字符）:\n{preview}")

                if not response.strip().endswith('}') and not response.strip().endswith(']'):
                    logger.error("⚠️ 响应可能被截断（缺少结束括号）")

                logger.error(f"响应统计: 总长度={len(response)}字符, "
                           f"起始='{response[:50]}...', "
                           f"结尾='...{response[-50:]}'")

            logger.error(f"完整堆栈跟踪:\n{traceback.format_exc()}")

            raise

    def _cleanup_temp_dir(self):
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def __del__(self):
        if hasattr(self, 'pdf_doc') and self.pdf_doc:
            self.pdf_doc.close()

        self._cleanup_temp_dir()
