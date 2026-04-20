
import os
import sys
import json
import signal
import atexit
import traceback
from pathlib import Path
from typing import List, Dict

Path("logs").mkdir(parents=True, exist_ok=True)

try:
    from config import UserConfig
    from extractors.pdf_extractor import PDFArticleExtractor
    from extractors.docx_extractor import DOCXArticleExtractor
    from generators.output_generator import ExcelGenerator
    from processors.translator import ArticleTranslator
    from generators.html_generator import AIHTMLGenerator
    from generators.output_generator import PDFGenerator, DOCXGenerator
    from pipeline.progress_manager import ProgressManager
except Exception as e:
    print(f"致命错误: 无法导入必要模块")
    print(f"错误详情: {e}")
    traceback.print_exc()
    input("\n按回车键退出...")
    sys.exit(1)

class MagazineWorkflow:
    
    def __init__(self):
        self.input_files = []
        self.input_structure = {}
        self.source_lang = "English"
        self.target_lang = "Chinese"
        self.generate_translation = True
        self.pages_per_batch = 6
        self.glossary_file = None
        self.generate_pdf = True
        self.generate_docx = True
        self.output_language_mode = "both"

        self.glossary = {}

        self.progress_manager = ProgressManager()
        self.resume_mode = False

        self.executor_mode = "parallel"
        self.executor_preset = None
    
    def get_output_path_with_structure(self, base_dir: str, filename: str, input_file: str) -> str:
        normalized_input = input_file.replace('\\', '/')
        
        relative_folder = self.input_structure.get(normalized_input, "")
        
        output_dir = Path(base_dir)
        if relative_folder:
            output_dir = output_dir / relative_folder
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return str(output_dir / filename)
    
    def ask_translation_preference(self) -> bool:
        print("[翻译] 步骤2: 配置AI翻译")
        print("\n是否需要AI翻译？")
        print("  y. 是 - 生成译文版本（Excel + HTML + PDF + DOCX）")
        print("  n. 否 - 仅提取和生成原文，跳过翻译")
        
        choice = input("\n是否需要翻译? (y/n, 默认y): ").strip().lower()
        
        if choice == 'n':
            self.generate_translation = False
            print("[OK] 已跳过翻译，仅处理原文\n")
            return True
        else:
            self.generate_translation = True
            print("[OK] 已启用翻译功能\n")
            return True
    
    def select_glossary(self) -> bool:
        print("[术语库] 步骤3: 选择术语库（可选）")
        terminology_dir = Path("terminology")
        if not terminology_dir.exists():
            print("[提示] 未找到 terminology 文件夹，跳过术语库配置")
            return True
        
        glossary_files = list(terminology_dir.glob("*.xlsx")) + list(terminology_dir.glob("*.xls"))
        
        if not glossary_files:
            print("[提示] 未找到术语库文件(.xlsx/.xls)，跳过术语库配置")
            return True
        
        print(f"找到 {len(glossary_files)} 个术语库文件:\n")
        for i, file_path in enumerate(glossary_files, 1):
            file_name = file_path.name
            file_size = file_path.stat().st_size / 1024
            print(f"  {i}. {file_name} ({file_size:.1f} KB)")
        
        print(f"\n  0. 不使用术语库")
        
        while True:
            try:
                choice = input(f"\n请选择术语库 (0-{len(glossary_files)}, 默认1): ").strip()
                
                if not choice:
                    choice = "1"
                
                idx = int(choice)
                
                if idx == 0:
                    print("[OK] 跳过术语库\n")
                    self.glossary_file = None
                    self.glossary = {}
                    return True

                if 1 <= idx <= len(glossary_files):
                    self.glossary_file = str(glossary_files[idx - 1])
                    print(f"[OK] 已选择: {glossary_files[idx - 1].name}")

                    try:
                        self.glossary = self._load_glossary()
                        if self.glossary:
                            print(f"     ✓ 已加载 {len(self.glossary)} 个术语")
                        else:
                            print(f"     ⚠ 术语库为空或格式不匹配")
                    except Exception as e:
                        print(f"     ⚠ 术语库加载失败: {e}")
                        self.glossary = {}

                    return True
                else:
                    print(f"[错误] 请输入 0-{len(glossary_files)} 之间的数字")
                    
            except ValueError:
                print("[错误] 请输入有效的数字")
            except Exception as e:
                print(f"[错误] 错误: {e}")
        
        return False
    
    def _load_glossary(self) -> Dict[str, str]:
        if not self.glossary_file:
            return {}
        
        import pandas as pd
        
        try:
            df = pd.read_excel(self.glossary_file)
            
            lang_codes = {
                'english': 'en',
                'chinese': 'zh', 
                'russian': 'ru'
            }
            
            source_lang_lower = self.source_lang.lower()
            target_lang_lower = self.target_lang.lower()
            
            source_code = lang_codes.get(source_lang_lower, source_lang_lower[:2])
            target_code = lang_codes.get(target_lang_lower, target_lang_lower[:2])
            
            possible_source_cols = [source_code, source_code.upper(), self.source_lang, self.source_lang.lower()]
            possible_target_cols = [target_code, target_code.upper(), self.target_lang, self.target_lang.lower()]
            
            source_col = None
            target_col = None
            
            for col in possible_source_cols:
                if col in df.columns:
                    source_col = col
                    break
            
            for col in possible_target_cols:
                if col in df.columns:
                    target_col = col
                    break
            
            if source_col and target_col:
                glossary = dict(zip(df[source_col].fillna(''), df[target_col].fillna('')))
                glossary = {k: v for k, v in glossary.items() if str(k).strip() and str(v).strip()}
                return glossary
            else:
                available_cols = ', '.join(df.columns.tolist())
                print(f"[警告] 警告: 术语库格式不匹配")
                print(f"   需要列: '{source_code}' (源) 和 '{target_code}' (目标)")
                print(f"   可用列: {available_cols}")
                print(f"   [提示] 提示: 列名可以是 en/EN/English, zh/ZH/Chinese, ru/RU/Russian")
                return {}
        except Exception as e:
            print(f"[警告] 警告: 无法读取术语库: {e}")
            return {}
    
    def find_files_with_structure(self, pattern: str, search_dirs: List[str] = None) -> tuple:
        if search_dirs is None:
            search_dirs = ["."]
        
        found_files = {}
        file_structure = {}
        
        for search_dir in search_dirs:
            search_path = Path(search_dir)
            if search_path.exists():
                for file in search_path.rglob(pattern):
                    if file.is_file():
                        file_str = str(file)
                        if 'output' in file_str or 'cache' in file_str or '__pycache__' in file_str:
                            continue
                        
                        abs_path = str(file.absolute())
                        if abs_path not in found_files:
                            normalized_path = str(file).replace('\\', '/')
                            found_files[abs_path] = normalized_path
                            
                            try:
                                relative_path = file.relative_to(search_path)
                                if relative_path.parent != Path('.'):
                                    relative_folder = str(relative_path.parent).replace('\\', '/')
                                else:
                                    relative_folder = ""
                                file_structure[normalized_path] = relative_folder
                            except ValueError:
                                file_structure[normalized_path] = ""
        
        sorted_files = sorted(found_files.values(), 
                            key=lambda x: (str(Path(x).parent), str(Path(x).name)))
        return sorted_files, file_structure
    
    def find_files(self, pattern: str, search_dirs: List[str] = None) -> List[str]:
        files, _ = self.find_files_with_structure(pattern, search_dirs)
        return files
    
    def select_input_file(self):
        print("[文件] 步骤1: 选择输入PDF/DOCX文件")
        pdf_files, pdf_structure = self.find_files_with_structure("*.pdf", ["input", "."])
        docx_files, docx_structure = self.find_files_with_structure("*.docx", ["input", "."])
        
        all_files = pdf_files + docx_files
        file_structure = {**pdf_structure, **docx_structure}
        
        if not all_files:
            print("[错误] 未找到PDF或DOCX文件")
            print("[提示] 提示: 请将PDF/DOCX期刊放入 input/ 文件夹")
            manual_input = input("或手动输入文件路径: ").strip()
            if manual_input and Path(manual_input).exists():
                self.input_files = [manual_input]
                self.input_structure = {manual_input: ""}
                return True
            else:
                print("[错误] 文件不存在")
                return False
        
        pdf_files = all_files
        
        folders = {}
        for file_path in pdf_files:
            folder = file_structure.get(file_path, "")
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(file_path)
        
        print(f"找到 {len(pdf_files)} 个文件 (PDF/DOCX):\n")
        
        file_index = 1
        file_map = {}
        
        for folder in sorted(folders.keys()):
            if folder:
                print(f"[文件夹] {folder}/")
            else:
                print("[文件夹] 根目录:")
            
            for file_path in folders[folder]:
                file_name = Path(file_path).name
                file_size = Path(file_path).stat().st_size / 1024
                if folder:
                    print(f"  {file_index}. {file_name} ({file_size:.1f} KB)")
                else:
                    print(f"  {file_index}. {file_name} ({file_size:.1f} KB)")
                file_map[file_index] = file_path
                file_index += 1

        print(f"  a. 全选所有文件")
        print(f"  0. 手动输入文件路径")
        print(f"\n[提示] 提示: 支持多选，用逗号分隔（如: 1,3）或范围（如: 1-3）")
        print(f"[提示] 输出将按输入文件夹结构自动分类")
        
        while True:
            try:
                choice = input(f"\n请选择文件 (1-{len(pdf_files)}, a=全选, 0=手动输入): ").strip().lower()
                
                if choice == "a" or choice == "all":
                    self.input_files = pdf_files
                    self.input_structure = {f: file_structure.get(f, "") for f in pdf_files}
                    print(f"[OK] 已选择全部 {len(self.input_files)} 个文件\n")
                    return True
                
                if choice == "0":
                    manual_input = input("请输入文件路径: ").strip()
                    if manual_input and Path(manual_input).exists():
                        self.input_files = [manual_input]
                        self.input_structure = {manual_input: ""}
                        return True
                    else:
                        print("[错误] 文件不存在，请重新输入")
                        continue
                
                selected_indices = set()
                for part in choice.split(','):
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = map(int, part.split('-'))
                            selected_indices.update(range(start, end + 1))
                        except ValueError:
                            print(f"[错误] 无效的范围: {part}")
                            continue
                    else:
                        try:
                            idx = int(part)
                            if 1 <= idx <= len(file_map):
                                selected_indices.add(idx)
                            else:
                                print(f"[错误] 数字 {part} 超出范围")
                        except ValueError:
                            print(f"[错误] 无效的输入: {part}")
                            continue
                
                if selected_indices:
                    self.input_files = [file_map[i] for i in sorted(selected_indices)]
                    self.input_structure = {f: file_structure.get(f, "") for f in self.input_files}
                    print(f"\n[OK] 已选择 {len(self.input_files)} 个文件:")
                    for f in self.input_files:
                        folder = self.input_structure.get(f, "")
                        if folder:
                            print(f"   - {folder}/{Path(f).name}")
                        else:
                            print(f"   - {Path(f).name}")
                    return True
                else:
                    print("[错误] 未选择任何文件，请重新输入")
                    
            except Exception as e:
                print(f"[错误] 输入错误: {e}")
    
    def configure_translation(self):
        print("[配置] 步骤4: 高级设置")

        print("\n▸ 源语言设置:")
        print("  1. English (英文) [默认]")
        print("  2. Russian (俄文)")

        if self.generate_translation:
            lang_choice = input("\n请选择源语言 (1/2, 默认1): ").strip()
            if lang_choice == "2":
                self.source_lang = "Russian"
            else:
                self.source_lang = "English"

            self.target_lang = "Chinese"
        else:
            lang_choice = input("\n请选择期刊语言 (1/2, 默认1): ").strip()
            if lang_choice == "2":
                self.source_lang = "Russian"
            else:
                self.source_lang = "English"
            self.target_lang = "Chinese"

        if self.generate_translation:
            print("\n▸ 输出内容设置:")
            print("  1. 生成原文+译文 (两套完整文件) [默认]")
            print("  2. 仅生成译文")
            output_choice = input("\n请选择输出内容 (1/2, 默认1): ").strip()
            if output_choice == "2":
                self.output_language_mode = "translated_only"
            else:
                self.output_language_mode = "both"
        else:
            self.output_language_mode = "original_only"

        print("\n▸ 输出格式设置:")
        print("  1. 完整格式 (Excel + HTML + PDF + DOCX) [默认]")
        print("  2. 仅Web格式 (Excel + HTML，跳过PDF/DOCX生成)")
        print("     提示: 选择Web格式可大幅节省处理时间")
        format_choice = input("\n请选择输出格式 (1/2, 默认1): ").strip()
        if format_choice == "2":
            self.generate_pdf = False
            self.generate_docx = False
            print("  [OK] 已选择Web格式，将跳过PDF/DOCX生成")
        else:
            self.generate_pdf = True
            self.generate_docx = True
            print("  [OK] 已选择完整格式")

        print("\n▸ 批处理设置:")
        print(f"  当前: 每批处理 {self.pages_per_batch} 页")
        print("  [提示] 页数越少越稳定，但耗时越长")
        adjust_pages = input("\n是否调整批处理页数? (y/n, 默认n): ").strip().lower()
        if adjust_pages == 'y':
            try:
                pages = int(input(f"  请输入每批页数 (5-20, 默认{self.pages_per_batch}): ").strip() or self.pages_per_batch)
                if 5 <= pages <= 20:
                    self.pages_per_batch = pages
                    print(f"  [OK] 已设置为每批 {self.pages_per_batch} 页")
                else:
                    print("  [警告] 页数超出范围，使用默认值")
            except ValueError:
                print("  [警告] 输入无效，使用默认值")

        print("\n▸ 批处理设置:")
        print(f"  当前: 每批处理 {self.pages_per_batch} 页")
        print("  [提示] 页数越少越稳定，但耗时越长")
        adjust_pages = input("\n是否调整批处理页数? (y/n, 默认n): ").strip().lower()
        if adjust_pages == 'y':
            try:
                pages = int(input(f"  请输入每批页数 (5-20, 默认{self.pages_per_batch}): ").strip() or self.pages_per_batch)
                if 5 <= pages <= 20:
                    self.pages_per_batch = pages
                    print(f"  [OK] 已设置为每批 {self.pages_per_batch} 页")
                else:
                    print("  [警告] 页数超出范围，使用默认值")
            except ValueError:
                print("  [警告] 输入无效，使用默认值")

    def select_executor_mode(self):
        print("[执行器] 步骤5: 选择处理模式")

        print("\n▸ 处理模式:")
        print("  1. 批量并发模式 (推荐用于少量文件)")
        print("     - 多文件并发处理，速度快")
        print("     - 适合: < 50 个文件")
        print("     - 资源占用: 高")
        print("  2. 单文件顺序模式 (推荐用于大批量文件)")
        print("     - 文件级别控制，稳定可靠")
        print("     - 适合: 50+ 文件，尤其是 1000+ 文件")
        print("     - 资源占用: 可控（防止内存爆炸）")
        print("     - 特性: 全局 API 限流、防饿死保障、看门狗监控")

        mode_choice = input("\n请选择处理模式 (1/2, 默认1): ").strip()

        if mode_choice == "2":
            self.executor_mode = "sequential"

            print("\n▸ 顺序模式预设:")
            print("  1. Conservative (保守) - 1000+ 文件")
            print("     - 文件并发: 2, API 并发: 50")
            print("     - 最稳定，适合超大批量")
            print("  2. Balanced (均衡) - 100-500 文件 [默认]")
            print("     - 文件并发: 4, API 并发: 75")
            print("     - 平衡速度与稳定性")
            print("  3. Aggressive (激进) - < 100 文件")
            print("     - 文件并发: 8, API 并发: 100")
            print("     - 最快速度，需要充足资源")

            preset_choice = input("\n请选择预设 (1/2/3, 默认2): ").strip()

            if preset_choice == "1":
                self.executor_preset = "conservative"
            elif preset_choice == "3":
                self.executor_preset = "aggressive"
            else:
                self.executor_preset = "balanced"

            print(f"\n[OK] 已选择: 单文件顺序模式 ({self.executor_preset})")
        else:
            self.executor_mode = "parallel"
            self.executor_preset = None
            print(f"\n[OK] 已选择: 批量并发模式")

    def confirm_and_execute(self):
        pdf_api_key = UserConfig.PDF_API_KEY or os.getenv("OPENAI_API_KEY")
        pdf_base_url = UserConfig.PDF_API_BASE_URL
        pdf_model = UserConfig.PDF_API_MODEL
        
        trans_api_key = UserConfig.TRANSLATION_API_KEY or os.getenv("OPENAI_API_KEY")
        trans_base_url = UserConfig.TRANSLATION_API_BASE_URL
        trans_model = UserConfig.TRANSLATION_API_MODEL
        
        if not pdf_api_key or pdf_api_key == "your-api-key-here":
            print("\n[警告] 警告: 未检测到有效的API密钥")
            print("请在 config.py 的 UserConfig 类中配置，或设置环境变量 OPENAI_API_KEY")
            
            manual_key = input("\n是否现在手动输入API密钥? (y/n): ").strip().lower()
            if manual_key == 'y':
                pdf_api_key = input("请输入API密钥: ").strip()
                if not pdf_api_key:
                    print("[错误] API密钥不能为空")
                    return False
            else:
                return False
        
        pages_per_batch = UserConfig.PAGES_PER_BATCH
        overlap_pages = UserConfig.OVERLAP_PAGES
        max_retries = UserConfig.MAX_RETRIES
        retry_delay = UserConfig.RETRY_DELAY
        request_interval = UserConfig.REQUEST_INTERVAL
        max_workers = UserConfig.MAX_WORKERS
        outline_pages_per_segment = UserConfig.OUTLINE_PAGES_PER_SEGMENT
        
        prompts = {}

        extractor = PDFArticleExtractor(
            api_key=pdf_api_key,
            api_url=pdf_base_url,
            model=pdf_model,
            pages_per_batch=pages_per_batch,
            overlap_pages=overlap_pages,
            max_retries=max_retries,
            retry_delay=retry_delay,
            request_interval=request_interval,
            max_workers=max_workers,
            outline_pages_per_segment=outline_pages_per_segment,
            prompts=prompts,
            source_language=self.source_lang,
            progress_manager=self.progress_manager
        )
        
        docx_extractor = DOCXArticleExtractor(
            api_key=pdf_api_key,
            api_url=pdf_base_url,
            model=pdf_model,
            max_retries=max_retries,
            retry_delay=retry_delay,
            request_interval=request_interval,
            prompts=prompts,
            source_language=self.source_lang
        )

        excel_generator = ExcelGenerator()

        from template_manager import HTMLTemplateManager
        template_manager = HTMLTemplateManager()
        selected_template = template_manager.select_template_interactive()

        html_generator = AIHTMLGenerator(template_name=selected_template)

        pdf_generator = None
        docx_generator = None
        
        if self.generate_pdf:
            try:
                pdf_generator = PDFGenerator()
            except RuntimeError as e:
                print(f"\n[警告] PDF生成器初始化失败: {e}")
                print("   将跳过PDF生成")
                self.generate_pdf = False
        
        if self.generate_docx:
            try:
                docx_generator = DOCXGenerator()
            except RuntimeError as e:
                print(f"\n[警告] DOCX生成器初始化失败: {e}")
                print("   将跳过DOCX生成")
                self.generate_docx = False
        
        translator = None
        if self.generate_translation:
            case_sensitive = UserConfig.CASE_SENSITIVE
            whole_word_only = UserConfig.WHOLE_WORD_ONLY
            
            if self.glossary:
                print(f"\n[术语库] 术语库配置:")
                print(f"   术语数量: {len(self.glossary)} 个")
                print(f"   区分大小写: {'是' if case_sensitive else '否'}")
                print(f"   完整单词匹配: {'是' if whole_word_only else '否'}")
                print(f"   示例术语:")
                for en, zh in list(self.glossary.items())[:5]:
                    print(f"      • {en} → {zh}")
                if len(self.glossary) > 5:
                    print(f"      ... 还有 {len(self.glossary) - 5} 个")
            else:
                print(f"\n[提示] 未加载术语库，将不进行术语替换")
            
            translator = ArticleTranslator(
                api_key=trans_api_key,
                api_url=trans_base_url,
                model=trans_model,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                glossary=self.glossary,
                case_sensitive=case_sensitive,
                whole_word_only=whole_word_only
            )
        
        from datetime import datetime
        import time
        from file_processor import BatchFileProcessor
        from file_processor import SequentialFileProcessor

        if not self.resume_mode:
            session_config = {
                'source_lang': self.source_lang,
                'target_lang': self.target_lang,
                'generate_translation': self.generate_translation,
                'pages_per_batch': self.pages_per_batch,
                'glossary_file': self.glossary_file,
                'generate_pdf': self.generate_pdf,
                'generate_docx': self.generate_docx,
                'input_structure': self.input_structure,
                'html_enable_sensitive_filter': UserConfig.HTML_ENABLE_SENSITIVE_WORDS_FILTER,
                'html_enable_ad_removal': UserConfig.HTML_ENABLE_AD_REMOVAL
            }
            session_id = self.progress_manager.create_session(self.input_files, session_config)
            print(f"\n[进度] 已创建会话: {session_id}")
            print(f"   进度文件将自动保存，支持断点续传\n")
        else:
            print(f"\n[进度] 继续未完成的会话")
            print(f"   剩余文件: {len(self.input_files)} 个\n")

        total_files = len(self.input_files)

        if total_files == 0:
            print("⚠️  警告：没有文件需要处理")
            print("\n可能原因：")
            print("  1. 所有文件已处理完成")
            print("  2. 会话恢复时没有剩余文件")
            print("  3. 文件选择时未选择任何文件")
            print("\n建议：")
            print("  - 开始新任务重新选择文件")
            print("  - 或检查进度文件状态\n")
            return

        start_time = time.time()
        start_datetime = datetime.now()

        print(f"\n[开始处理] 共 {total_files} 个文件")
        print(f"   开始时间: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")

        report_path = Path("logs/failed_files.jsonl")

        if self.executor_mode == "sequential":
            preset_config = {
                'max_concurrent_files': 4,
                'file_min_api_guarantee': 8,
                'global_api_concurrency': 40,
                'per_file_max_workers': 12,
                'global_task_queue_size': 400,
                'queue_overflow_strategy': 'delay',
                'enable_watchdog': True,
                'watchdog_timeout': 300,
                'log_executor_stats': True,
                'stats_interval': 30,
            }

            batch_processor = SequentialFileProcessor(
                extractor=extractor,
                excel_generator=excel_generator,
                html_generator=html_generator,
                pdf_generator=pdf_generator,
                docx_generator=docx_generator,
                translator=translator,
                input_structure=self.input_structure,
                generate_pdf=self.generate_pdf,
                generate_docx=self.generate_docx,
                generate_translation=self.generate_translation,
                output_language_mode=self.output_language_mode,
                docx_extractor=docx_extractor,
                progress_manager=self.progress_manager,
                config=preset_config
            )

            max_concurrent_files = preset_config['max_concurrent_files']

        else:
            batch_processor = BatchFileProcessor(
                extractor=extractor,
                excel_generator=excel_generator,
                html_generator=html_generator,
                pdf_generator=pdf_generator,
                docx_generator=docx_generator,
                translator=translator,
                input_structure=self.input_structure,
                generate_pdf=self.generate_pdf,
                generate_docx=self.generate_docx,
                generate_translation=self.generate_translation,
                output_language_mode=self.output_language_mode,
                docx_extractor=docx_extractor,
                progress_manager=self.progress_manager
            )

            max_concurrent_files = UserConfig.MAX_CONCURRENT_PDF_FILES

        try:

            success_files, partial_files, failed_files = batch_processor.process_files(
                self.input_files,
                max_workers=max_concurrent_files
            )
            
            total_elapsed = time.time() - start_time
            end_datetime = datetime.now()
            
            success_count = len(success_files)
            partial_count = len(partial_files)
            failed_count = len(failed_files)
            
            success_rate = (success_count / total_files * 100) if total_files > 0 else 0
            effective_success_rate = ((success_count + partial_count) / total_files * 100) if total_files > 0 else 0
            problem_completion_rate = (partial_count / total_files * 100) if total_files > 0 else 0
            
            hours = int(total_elapsed // 3600)
            minutes = int((total_elapsed % 3600) // 60)
            seconds = int(total_elapsed % 60)
            
            print("✅ 批量处理完成！")

            if total_files > 0:
                print(f"   ├─ ✅ 完全成功: {success_count} 个 ({success_rate:.1f}%)")
                print(f"   ├─ ⚠️  部分成功: {partial_count} 个 ({partial_count/total_files*100:.1f}%)")
                print(f"   └─ ❌ 完全失败: {failed_count} 个 ({failed_count/total_files*100:.1f}%)")
            else:
                print(f"   ⚠️  没有文件被处理")

            if success_files:
                print(f"\n[OK] 完全成功的文件 ({success_count}个):")
                for idx, item in enumerate(success_files[:10], 1):
                    print(f"   {idx}. {item['name']}")
                if success_count > 10:
                    print(f"   ... 还有 {success_count - 10} 个")

            if partial_files:
                print(f"\n[警告]  有质量问题的文件 ({partial_count}个) - 所有阶段已完成，但AI处理有问题:")
                print(f"        ⚠️  这些文件不需要重新运行，需要人工检查和处理")
                for idx, item in enumerate(partial_files, 1):
                    print(f"   {idx}. {item['name']}")
                    for issue in item['issues']:
                        print(f"      - {issue}")

            if failed_files:
                print(f"\n[错误] 完全失败的文件 ({failed_count}个):")
                for idx, failed in enumerate(failed_files, 1):
                    print(f"   {idx}. {failed['name']}")
                    print(f"      原因: {failed['error'][:100]}...")

            if failed_files or partial_files:
                print(f"\n📄 详细报告: {report_path}")


            if self.progress_manager.mark_session_completed():
                print("[进度] 会话已完成并保存\n")
            else:
                print("[进度] 会话未完成，已保存当前快照\n")
            
            self.progress_manager.cleanup_old_sessions(keep_days=7)
            
            return True
            
        except Exception as e:
            print(f"\n[错误] 处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _open_file(self, file_path: str):
        try:
            if sys.platform == 'win32':
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{file_path}"')
            else:
                os.system(f'xdg-open "{file_path}"')
        except Exception as e:
            print(f"[警告] 无法自动打开: {e}")
    
    def run(self):
        incomplete_sessions = self.progress_manager.find_incomplete_sessions()
        if incomplete_sessions:
            session = incomplete_sessions[0]
            total = session['total_files']
            completed_no_issues = session.get('completed_no_issues', 0)
            completed_with_issues = session.get('completed_with_issues', 0)
            partial_no_issues = session.get('partial_no_issues', 0)
            partial_with_issues = session.get('partial_with_issues', 0)
            failed = session.get('failed', 0)
            pending = session.get('pending', 0)
            completed_total = completed_no_issues + completed_with_issues
            partial_total = partial_no_issues + partial_with_issues

            print("💡 发现未完成的处理会话")
            print(f"\n会话时间: {session['created']}")
            print(f"  - 总文件: {total}")
            print(f"  - 已完成: {completed_total} (无问题: {completed_no_issues}, 有问题: {completed_with_issues})")
            print(f"  - 部分完成: {partial_total} (无问题: {partial_no_issues}, 有问题: {partial_with_issues})")
            print(f"  - 失败: {failed}, 未处理: {pending}")
            
            print("\n是否恢复此会话?")
            print("  [y] 是，继续处理")
            print("  [n] 否，开始新任务 (默认)")
            
            choice = input("\n请选择 (y/N): ").strip().lower()
            
            if choice == 'y':
                try:
                    self.progress_manager.load_session(session['file'])
                    
                    data = session['data']
                    config = data.get('config', {})
                    
                    self.source_lang = config.get('source_lang', 'English')
                    self.target_lang = config.get('target_lang', 'Chinese')
                    self.generate_translation = config.get('generate_translation', True)
                    self.pages_per_batch = config.get('pages_per_batch', 5)
                    self.glossary_file = config.get('glossary_file')
                    self.generate_pdf = config.get('generate_pdf', True)
                    self.generate_docx = config.get('generate_docx', True)
                    self.output_language_mode = config.get('output_language_mode', 'both')
                    
                    self.input_structure = config.get('input_structure', {})
                    
                    if self.generate_translation and self.glossary_file:
                        if not Path(self.glossary_file).exists():
                            print(f"   ⚠️  原术语库文件不存在: {self.glossary_file}")
                            terminology_dir = Path("terminology")
                            if terminology_dir.exists():
                                glossary_files = list(terminology_dir.glob("*.xlsx")) + list(terminology_dir.glob("*.xls"))
                                if glossary_files:
                                    self.glossary_file = str(glossary_files[0])
                                    print(f"   ✅ 自动使用 terminology 中的术语库: {glossary_files[0].name}")
                                else:
                                    print(f"   ⚠️  terminology 文件夹中未找到术语库，将不使用术语库")
                                    self.glossary_file = None
                            else:
                                print(f"   ⚠️  terminology 文件夹不存在，将不使用术语库")
                                self.glossary_file = None
                    
                    self.input_files = self.progress_manager.get_remaining_files()
                    
                    all_files = data.get('files', [])
                    missing_files = []
                    for file_path in all_files:
                        if not Path(file_path).exists():
                            missing_files.append(file_path)
                    
                    if missing_files:
                        print(f"\n⚠️  警告：发现 {len(missing_files)} 个输入文件已删除或移动:")
                        for f in missing_files[:3]:
                            print(f"   - {f}")
                        if len(missing_files) > 3:
                            print(f"   ... 还有 {len(missing_files) - 3} 个")
                        
                        print("\n无法恢复此会话（输入文件不可用）")
                        print("[提示] 将开始新任务")
                    else:
                        self.resume_mode = True
                        
                        print(f"\n[OK] 已恢复会话，剩余 {len(self.input_files)} 个文件待处理")

                        self.glossary = self._load_glossary()
                        self.confirm_and_execute()
                        return
                    
                except Exception as e:
                    print(f"\n[错误] 恢复会话失败: {e}")
                    print("[提示] 将开始新任务")
            else:
                print("\n[OK] 开始新任务")

        if not self.select_input_file():
            return
        
        if not self.ask_translation_preference():
            return
        
        if self.generate_translation:
            if not self.select_glossary():
                return
        else:
            self.glossary_file = None
            self.glossary = {}
        
        self.configure_translation()

        self.select_executor_mode()

        self.confirm_and_execute()

def setup_directories():
    directories = [
        "input",
        "output",
        "output/excel",
        "output/html",
        "output/pdf",
        "output/docx",
        "output/json",
        "output/image",
        "logs",
        "terminology",
        "progress"
    ]

    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print("[文件夹] 已创建必要的文件夹结构")

def main():
    try:
        print("正在启动期刊处理工具...")
        setup_directories()
        
        workflow = MagazineWorkflow()
        workflow.run()
        
    except KeyboardInterrupt:
        print("\n\n[中断] 用户中断操作")
        input("\n按回车键退出...")
        sys.exit(0)
    except Exception as e:
        print(f"\n[错误] 发生严重错误!")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("\n详细错误信息:")
        traceback.print_exc()
        
        try:
            error_file = Path("logs") / "crash_error.log"
            error_file.parent.mkdir(parents=True, exist_ok=True)
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("程序崩溃错误报告\n")
                f.write("=" * 80 + "\n")
                f.write(f"错误类型: {type(e).__name__}\n")
                f.write(f"错误信息: {str(e)}\n\n")
                f.write("详细堆栈信息:\n")
                f.write(traceback.format_exc())
                f.write("\n" + "=" * 80 + "\n")
            print(f"\n错误详情已保存到: {error_file}")
        except Exception as log_error:
            print(f"无法保存错误日志: {log_error}")
        
        print("\n常见问题排查:")
        print("1. 检查是否缺少必要文件（_internal文件夹）")
        print("2. 检查是否有足够的磁盘空间")
        print("3. 检查logs文件夹中的错误日志")
        print("4. 尝试以管理员身份运行")
        
        input("\n按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[致命错误] 程序启动失败: {e}")
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)
