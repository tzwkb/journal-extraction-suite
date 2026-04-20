
import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
from threading import Lock

class ProgressManager:

    ALL_STAGES = [
        'extraction', 'image_processing', 'excel_original', 'html_original',
        'pdf_original', 'docx_original', 'translation', 'excel_translated',
        'html_translated', 'pdf_translated', 'docx_translated'
    ]

    def __init__(self, progress_dir: str = "progress"):
        self.progress_dir = Path(progress_dir)
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_file = None
        self.progress_data = None
        self.save_lock = Lock()
        self.save_count = 0
        self._last_saved_hash = None
    
    def find_incomplete_sessions(self) -> List[Dict]:
        incomplete_sessions = []

        all_stages = self.ALL_STAGES

        for progress_file in self.progress_dir.glob("session_*.json"):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data.get('completed', False):
                    continue

                total_files = len(data.get('files', []))
                file_progress = data.get('file_progress', {})

                completed_no_issues = 0
                completed_with_issues = 0
                partial_no_issues = 0
                partial_with_issues = 0
                failed_count = 0
                pending_count = 0

                for file_path in data.get('files', []):
                    normalized_path = file_path.replace('\\', '/')
                    progress = file_progress.get(normalized_path, {})
                    stages = progress.get('stages', {})
                    issues = progress.get('issues', [])
                    error = progress.get('error')

                    completed_stages = sum(1 for s in all_stages if self._get_stage_status(stages, s) == 'completed')
                    failed_stages = sum(1 for s in all_stages if self._get_stage_status(stages, s) == 'failed')
                    has_issues = len(issues) > 0 or failed_stages > 0

                    in_progress_stages = sum(1 for s in all_stages
                                            if self._get_stage_status(stages, s) in ['processing', 'in_progress'])
                    pending_stages_count = sum(1 for s in all_stages
                                              if self._get_stage_status(stages, s) == 'pending')

                    if completed_stages == len(all_stages):
                        if has_issues:
                            completed_with_issues += 1
                        else:
                            completed_no_issues += 1
                    elif completed_stages > 0 or in_progress_stages > 0:
                        if has_issues:
                            partial_with_issues += 1
                        else:
                            partial_no_issues += 1
                    elif error:
                        failed_count += 1
                    else:
                        pending_count += 1

                incomplete_total = partial_no_issues + partial_with_issues + pending_count

                if incomplete_total > 0 or failed_count > 0:
                    incomplete_sessions.append({
                        'file': str(progress_file),
                        'data': data,
                        'created': data.get('start_time', ''),
                        'total_files': total_files,
                        'completed_no_issues': completed_no_issues,
                        'completed_with_issues': completed_with_issues,
                        'partial_no_issues': partial_no_issues,
                        'partial_with_issues': partial_with_issues,
                        'failed': failed_count,
                        'pending': pending_count
                    })

            except Exception as e:
                print(f"[警告] 无法读取进度文件 {progress_file}: {e}")

        incomplete_sessions.sort(key=lambda x: x['created'], reverse=True)
        return incomplete_sessions
    
    def create_session(self, files: List[str], config: Dict) -> str:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_file = self.progress_dir / f"session_{session_id}.json"
        
        normalized_files = [f.replace('\\', '/') for f in files]
        
        self.progress_data = {
            'session_id': session_id,
            'start_time': datetime.now().isoformat(),
            'config': config,
            'files': normalized_files,
            'file_progress': {},
            'completed': False,
            'last_update': datetime.now().isoformat()
        }
        
        self._save_progress()
        
        return session_id
    
    def load_session(self, session_file: str):
        self.current_session_file = Path(session_file)
        
        try:
            with open(self.current_session_file, 'r', encoding='utf-8') as f:
                self.progress_data = json.load(f)

        except (json.JSONDecodeError, IOError) as e:
            print(f"[错误] 无法加载会话文件: {e}")
            print(f"[恢复] 尝试从备份恢复...")
            
            if self.restore_from_backup(session_file):
                print(f"[恢复] ✅ 已从备份文件恢复会话")
            else:
                raise Exception("会话文件损坏且备份文件不可用")
        
        if 'files' in self.progress_data:
            self.progress_data['files'] = [f.replace('\\', '/') for f in self.progress_data['files']]
        
        if 'completed_files' in self.progress_data:
            normalized_completed = []
            for item in self.progress_data['completed_files']:
                if isinstance(item, dict):
                    if 'file' in item:
                        item['file'] = item['file'].replace('\\', '/')
                    normalized_completed.append(item)
                else:
                    normalized_completed.append({
                        'file': item.replace('\\', '/'),
                        'name': Path(item).name
                    })
            self.progress_data['completed_files'] = normalized_completed
        
        if 'file_progress' in self.progress_data:
            old_progress = self.progress_data['file_progress']
            new_progress = {}
            for file_path, data in old_progress.items():
                normalized_path = file_path.replace('\\', '/')
                new_progress[normalized_path] = data
            self.progress_data['file_progress'] = new_progress
        
        if 'partial_files' in self.progress_data:
            for item in self.progress_data['partial_files']:
                if isinstance(item, dict) and 'file' in item:
                    item['file'] = item['file'].replace('\\', '/')
        
        if 'failed_files' in self.progress_data:
            for item in self.progress_data['failed_files']:
                if isinstance(item, dict) and 'file' in item:
                    item['file'] = item['file'].replace('\\', '/')
        
        print(f"[恢复] 已加载会话: {self.progress_data['session_id']}")
        print(f"   开始时间: {self.progress_data['start_time']}")
        print(f"   总文件数: {len(self.progress_data['files'])}")
        print(f"   已完成: {len(self.progress_data.get('completed_files', []))}")
        print(f"   部分成功: {len(self.progress_data.get('partial_files', []))}")
        print(f"   完全失败: {len(self.progress_data.get('failed_files', []))}")
        
        self.validate_and_fix_progress()
    
    def restore_from_backup(self, session_file: str) -> bool:
        backup_file = Path(session_file).with_suffix('.json.bak')
        
        if not backup_file.exists():
            print(f"   [恢复] 备份文件不存在: {backup_file}")
            return False
        
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                self.progress_data = json.load(f)
            
            shutil.copy2(backup_file, session_file)
            self.current_session_file = Path(session_file)
            
            return True
        except Exception as e:
            print(f"   [恢复] 备份文件也损坏: {e}")
            return False
    
    def validate_and_fix_progress(self):
        if not self.progress_data:
            return
        
        print("\n[验证] 检查进度数据一致性...")
        
        config = self.progress_data.get('config', {})
        input_structure = config.get('input_structure', {})
        inconsistencies_found = False
        
        for file_path, progress in list(self.progress_data.get('file_progress', {}).items()):
            file_stem = Path(file_path).stem
            
            relative_folder = input_structure.get(file_path, "") or input_structure.get(file_path.replace('/', '\\'), "")
            
            def get_output_path(base_dir: str, filename: str) -> Path:
                output_dir = Path(base_dir)
                if relative_folder:
                    output_dir = output_dir / relative_folder
                return output_dir / filename
            
            json_cache_dir = get_output_path("output/json", file_stem)
            
            stages = progress.get('stages', {})
            
            extraction_status = self._get_stage_status(stages, 'extraction')
            
            if extraction_status == 'completed':
                final_exists = False
                final_file = None
                for pattern in ['final_articles_*.json', 'merged_articles_*.json']:
                    matches = list(json_cache_dir.glob(pattern))
                    if matches:
                        final_exists = True
                        final_file = matches[0]
                        break
                
                if final_exists and final_file:
                    file_size = final_file.stat().st_size / 1024
                    print(f"   ✅ {Path(file_path).name}: 缓存文件存在 ({file_size:.1f} KB)")
                else:
                    print(f"   ⚠️  {Path(file_path).name}: extraction标记为完成但缺少最终JSON文件")
                    self._set_stage_status(stages, 'extraction', 'pending')
                    inconsistencies_found = True
            
            elif extraction_status == 'in_progress':
                outline_file = json_cache_dir / 'outline' / 'journal_outline.json'
                batches_dir = json_cache_dir / 'batches'
                batch_files = list(batches_dir.glob("batch_*.json")) if batches_dir.exists() else []

                if outline_file.exists() or batch_files:
                    if outline_file.exists() and not batch_files:
                        print(f"   ✅ {Path(file_path).name}: 找到大纲文件（batch处理未开始）")
                    elif batch_files:
                        print(f"   ✅ {Path(file_path).name}: 找到大纲和 {len(batch_files)} 个batch文件" if outline_file.exists()
                              else f"   ✅ {Path(file_path).name}: 找到 {len(batch_files)} 个batch文件")
                else:
                    print(f"   ⚠️  {Path(file_path).name}: extraction标记为进行中但没有大纲或batch文件")
                    self._set_stage_status(stages, 'extraction', 'pending')
                    inconsistencies_found = True

            if self._get_stage_status(stages, 'excel_original') == 'completed':
                excel_path = get_output_path("output/excel", f"{file_stem}.xlsx")
                if not excel_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: excel_original标记为完成但文件不存在")
                    self._set_stage_status(stages, 'excel_original', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'html_original') == 'completed':
                html_path = get_output_path("output/html", f"{file_stem}.html")
                if not html_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: html_original标记为完成但文件不存在")
                    self._set_stage_status(stages, 'html_original', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'pdf_original') == 'completed':
                pdf_path = get_output_path("output/pdf", f"{file_stem}.pdf")
                if not pdf_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: pdf_original标记为完成但文件不存在")
                    self._set_stage_status(stages, 'pdf_original', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'docx_original') == 'completed':
                docx_path = get_output_path("output/docx", f"{file_stem}.docx")
                if not docx_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: docx_original标记为完成但文件不存在")
                    self._set_stage_status(stages, 'docx_original', 'pending')
                    inconsistencies_found = True
            
            translation_status = self._get_stage_status(stages, 'translation')
            
            if translation_status == 'completed':
                excel_trans_path = get_output_path("output/excel", f"(译文) {file_stem}.xlsx")
                if not excel_trans_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: translation标记为完成但译文Excel不存在")
                    self._set_stage_status(stages, 'translation', 'pending')
                    inconsistencies_found = True
            
            elif translation_status == 'in_progress':
                cache_path = json_cache_dir / ".cache" / "translation_cache"
                if cache_path.exists():
                    cache_files = list(cache_path.glob("article_*.json"))
                    if cache_files:
                        print(f"   ✅ {Path(file_path).name}: 找到 {len(cache_files)} 个翻译缓存")
                    else:
                        print(f"   ⚠️  {Path(file_path).name}: translation标记为进行中但没有翻译缓存")
                        self._set_stage_status(stages, 'translation', 'pending')
                        inconsistencies_found = True
                else:
                    batch_files = list(json_cache_dir.glob("batch_*.json"))
                    has_translation = False
                    for batch_file in batch_files[:3]:
                        try:
                            with open(batch_file, 'r', encoding='utf-8') as f:
                                articles = json.load(f)
                                if articles and articles[0].get('content_zh'):
                                    has_translation = True
                                    break
                        except:
                            pass
                    
                    if not has_translation:
                        print(f"   ⚠️  {Path(file_path).name}: translation标记为进行中但没有翻译数据")
                    self._set_stage_status(stages, 'translation', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'excel_translated') == 'completed':
                excel_trans_path = get_output_path("output/excel", f"(译文) {file_stem}.xlsx")
                if not excel_trans_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: excel_translated标记为完成但文件不存在")
                    self._set_stage_status(stages, 'excel_translated', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'html_translated') == 'completed':
                html_trans_path = get_output_path("output/html", f"(译文) {file_stem}.html")
                if not html_trans_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: html_translated标记为完成但文件不存在")
                    self._set_stage_status(stages, 'html_translated', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'pdf_translated') == 'completed':
                pdf_trans_path = get_output_path("output/pdf", f"(译文) {file_stem}.pdf")
                if not pdf_trans_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: pdf_translated标记为完成但文件不存在")
                    self._set_stage_status(stages, 'pdf_translated', 'pending')
                    inconsistencies_found = True
            
            if self._get_stage_status(stages, 'docx_translated') == 'completed':
                docx_trans_path = get_output_path("output/docx", f"(译文) {file_stem}.docx")
                if not docx_trans_path.exists():
                    print(f"   ⚠️  {Path(file_path).name}: docx_translated标记为完成但文件不存在")
                    self._set_stage_status(stages, 'docx_translated', 'pending')
                    inconsistencies_found = True
            
            progress['stages'] = stages

            if file_path in self.progress_data.get('file_progress', {}):
                completed_stages = [s for s in stages.keys() if self._get_stage_status(stages, s) == 'completed']
                pending_stages = [s for s in stages.keys() if self._get_stage_status(stages, s) == 'pending']
                failed_stages = [s for s in stages.keys() if self._get_stage_status(stages, s) == 'failed']

                if len(completed_stages) == len(stages) and len(stages) > 0:
                    self.progress_data['file_progress'][file_path]['status'] = 'completed'
                elif len(pending_stages) == len(stages) or len(stages) == 0:
                    self.progress_data['file_progress'][file_path]['status'] = 'pending'
                    if inconsistencies_found:
                        print(f"   ⚠️  {Path(file_path).name}: 状态重置为pending（所有阶段未开始）")
                elif len(failed_stages) > 0:
                    self.progress_data['file_progress'][file_path]['status'] = 'failed'
                else:
                    self.progress_data['file_progress'][file_path]['status'] = 'in_progress'
        
        if inconsistencies_found:
            print("   [验证] 发现不一致，已自动修复进度数据")
            self._save_progress()
        else:
            print("   ✅ 进度数据与文件系统一致")
        
        print()
    
    def _get_stage_status(self, stages: Dict, stage_name: str) -> str:
        stage_data = stages.get(stage_name)
        
        if isinstance(stage_data, str):
            return stage_data
        elif isinstance(stage_data, dict):
            return stage_data.get('status', 'pending')
        else:
            return 'pending'
    
    def _set_stage_status(self, stages: Dict, stage_name: str, status: str):
        stage_data = stages.get(stage_name)
        
        if isinstance(stage_data, str):
            stages[stage_name] = status
        elif isinstance(stage_data, dict):
            stage_data['status'] = status
            stage_data['updated_at'] = datetime.now().isoformat()
        else:
            stages[stage_name] = status
    
    def get_remaining_files(self) -> List[str]:
        if not self.progress_data:
            return []

        with self.save_lock:
            all_files = list(self.progress_data.get('files', []))
            import copy
            file_progress = copy.deepcopy(self.progress_data.get('file_progress', {}))

        remaining = []
        completed_count = 0
        quality_issues_count = 0
        incomplete_count = 0
        failed_count = 0
        not_started_count = 0

        all_stages = self.ALL_STAGES

        for file_path in all_files:
            normalized_path = file_path.replace('\\', '/')

            progress = file_progress.get(normalized_path, {})
            status = progress.get('status', 'pending')
            stages = progress.get('stages', {})
            issues = progress.get('issues', [])

            completed_stages = []
            pending_stages = []
            failed_stages = []

            for stage_name in all_stages:
                stage_status = self._get_stage_status(stages, stage_name)
                if stage_status == 'completed':
                    completed_stages.append(stage_name)
                elif stage_status == 'failed':
                    failed_stages.append(stage_name)
                elif stage_status == 'pending':
                    pending_stages.append(stage_name)

            all_completed = len(completed_stages) == len(all_stages)
            in_progress_stages = [s for s in all_stages
                                  if self._get_stage_status(stages, s) in ('in_progress', 'processing')]
            has_pending = len(pending_stages) > 0 or len(failed_stages) > 0 or len(in_progress_stages) > 0

            if all_completed and not issues:
                completed_count += 1
                continue

            elif all_completed and issues:
                quality_issues_count += 1
                continue

            elif status == 'failed':
                remaining.append(file_path)
                failed_count += 1

            elif has_pending:
                remaining.append(file_path)
                incomplete_count += 1

            else:
                remaining.append(file_path)
                not_started_count += 1

        if remaining or quality_issues_count > 0:
            print(f"\n   [断点续传] 文件状态分类:")
            print(f"      ✅ 完全成功: {completed_count} 个")
            print(f"      🔄 需要继续处理:")
            print(f"         - 未开始: {not_started_count} 个")
            print(f"         - 部分阶段未完成: {incomplete_count} 个")
            print(f"         - 失败需重试: {failed_count} 个")
            print(f"      ⚠️  有质量问题但已完成: {quality_issues_count} 个（不重跑，需人工检查）")
            print(f"      📊 总计需处理: {len(remaining)} 个\n")

        return remaining
    
    def mark_file_started(self, file_path: str):
        if not self.progress_data:
            return
        
        normalized_path = file_path.replace('\\', '/')
        
        self.progress_data['file_progress'][normalized_path] = {
            'status': 'processing',
            'start_time': datetime.now().isoformat(),
            'issues': [],
            'stages': {
                'extraction': 'pending',
                'image_processing': 'pending',
                'excel_original': 'pending',
                'html_original': 'pending',
                'pdf_original': 'pending',
                'docx_original': 'pending',
                'translation': 'pending',
                'excel_translated': 'pending',
                'html_translated': 'pending',
                'pdf_translated': 'pending',
                'docx_translated': 'pending'
            }
        }

        self._save_progress()
    
    def _update_file_status_list(self, file_list: List[Dict], normalized_path: str, file_name: str, data: Dict):
        existing = [item for item in file_list 
                   if isinstance(item, dict) and item.get('file') == normalized_path]
        if not existing:
            file_list.append({
                'file': normalized_path,
                'name': file_name,
                **data
            })
        else:
            existing[0].update(data)
    
    def mark_file_completed(self, file_path: str, success: bool = True,
                           error: str = None, issues: List[str] = None):
        if not self.progress_data:
            return

        normalized_path = file_path.replace('\\', '/')
        file_name = Path(normalized_path).name

        if normalized_path not in self.progress_data['file_progress']:
            self.mark_file_started(normalized_path)

        if success and not issues:
            self.progress_data['file_progress'][normalized_path]['status'] = 'completed'
            self.progress_data['file_progress'][normalized_path]['end_time'] = datetime.now().isoformat()

        elif issues:
            self.progress_data['file_progress'][normalized_path]['status'] = 'partial'
            self.progress_data['file_progress'][normalized_path]['issues'] = issues
            self.progress_data['file_progress'][normalized_path]['end_time'] = datetime.now().isoformat()

        else:
            self.progress_data['file_progress'][normalized_path]['status'] = 'failed'
            self.progress_data['file_progress'][normalized_path]['error'] = error or 'Unknown error'
            self.progress_data['file_progress'][normalized_path]['end_time'] = datetime.now().isoformat()

        self._save_progress()
    
    def mark_session_completed(self) -> bool:
        if not self.progress_data:
            return False

        total_files = len(self.progress_data.get('files', []))
        if total_files == 0:
            return False

        file_progress = self.progress_data.get('file_progress', {})
        all_stages = ['extraction', 'image_processing', 'excel_original', 'html_original', 'pdf_original', 'docx_original',
                      'translation', 'excel_translated', 'html_translated', 'pdf_translated', 'docx_translated']

        completed_count = 0

        for file_path in self.progress_data.get('files', []):
            normalized_path = file_path.replace('\\', '/')
            progress = file_progress.get(normalized_path, {})
            stages = progress.get('stages', {})
            issues = progress.get('issues', [])

            completed_stages = sum(1 for s in all_stages if self._get_stage_status(stages, s) == 'completed')

            if completed_stages == len(all_stages) and not issues:
                completed_count += 1

        if completed_count == total_files:
            self.progress_data['completed'] = True
            self.progress_data['end_time'] = datetime.now().isoformat()
            self._save_progress()
            return True
        else:
            self.progress_data['completed'] = False
            self._save_progress()
            return False
    
    def update_stage_progress(self, file_path: str, stage: str, status: str, 
                             completed_count: int = None, total_count: int = None):
        if not self.progress_data:
            return
        
        normalized_path = file_path.replace('\\', '/')
        
        if normalized_path not in self.progress_data['file_progress']:
            self.mark_file_started(file_path)
        
        if completed_count is not None or total_count is not None:
            existing = self.progress_data['file_progress'][normalized_path]['stages'].get(stage)
            
            if isinstance(existing, dict):
                stage_data = existing
            else:
                stage_data = {
                    'status': existing if isinstance(existing, str) else 'pending',
                    'started_at': datetime.now().isoformat()
                }
            
            stage_data['status'] = status
            stage_data['updated_at'] = datetime.now().isoformat()
            
            if completed_count is not None:
                stage_data['completed_count'] = completed_count
            if total_count is not None:
                stage_data['total_count'] = total_count
            
            if completed_count is not None and total_count is not None and total_count > 0:
                stage_data['progress'] = completed_count / total_count
            
            self.progress_data['file_progress'][normalized_path]['stages'][stage] = stage_data
        else:
            self.progress_data['file_progress'][normalized_path]['stages'][stage] = status
        
        self._save_progress()

    def get_file_progress(self, file_path: str) -> Dict:
        if not self.progress_data:
            return None
        
        normalized_path = file_path.replace('\\', '/')
        
        progress = self.progress_data['file_progress'].get(file_path)
        if progress:
            return progress
        
        progress = self.progress_data['file_progress'].get(normalized_path)
        if progress:
            return progress
        
        reverse_path = file_path.replace('/', '\\')
        return self.progress_data['file_progress'].get(reverse_path)
    
    def is_stage_completed(self, file_path: str, stage: str) -> bool:
        progress = self.get_file_progress(file_path)
        if progress and 'stages' in progress:
            return self._get_stage_status(progress['stages'], stage) == 'completed'
        return False
    
    def _save_progress(self):
        if not self.progress_data or not self.current_session_file:
            print(f"[调试] 跳过保存：progress_data={self.progress_data is not None}, session_file={self.current_session_file}")
            return
        
        with self.save_lock:
            import copy, hashlib
            current_hash = hashlib.md5(
                json.dumps(self.progress_data, sort_keys=True, default=str).encode()
            ).hexdigest()
            if current_hash == self._last_saved_hash:
                return
            progress_snapshot = copy.deepcopy(self.progress_data)
            progress_snapshot['last_update'] = datetime.now().isoformat()
            
            max_save_retries = 3
            for save_attempt in range(max_save_retries):
                try:
                    temp_file = self.current_session_file.with_suffix(f'.tmp{save_attempt}')
                    
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(progress_snapshot, f, ensure_ascii=False, indent=2)
                    
                    temp_size = temp_file.stat().st_size
                    if temp_size < 100:
                        print(f"[警告] 临时文件太小（{temp_size} 字节），可能保存失败")
                        if temp_file.exists():
                            temp_file.unlink()
                        continue
                    
                    if self.current_session_file.exists():
                        backup_file = self.current_session_file.with_suffix('.json.bak')
                        try:
                            with open(self.current_session_file, 'r', encoding='utf-8') as _f:
                                json.load(_f)
                            shutil.copy2(self.current_session_file, backup_file)
                        except Exception as backup_error:
                            print(f"[警告] 创建备份失败: {backup_error}")

                    import os
                    os.replace(temp_file, self.current_session_file)
                    
                    self._last_saved_hash = current_hash
                    self.save_count += 1
                    
                    if self.save_count % 100 == 1:
                        print(f"[进度] 已保存进度（第{self.save_count}次）：{self.current_session_file.name}")
                    
                    break
                    
                except PermissionError as e:
                    if save_attempt < max_save_retries - 1:
                        print(f"[警告] 保存进度失败（尝试{save_attempt+1}/{max_save_retries}）：文件被占用，1秒后重试...")
                        time.sleep(1)
                        if temp_file.exists():
                            try:
                                temp_file.unlink()
                            except:
                                pass
                    else:
                        print(f"[错误] 保存进度失败（已重试{max_save_retries}次）: {e}")
                        print(f"⚠️  可能原因：会话文件被其他程序（如编辑器）打开")
                        print(f"⚠️  建议：关闭打开该文件的程序后，程序会继续尝试保存")
                
                except Exception as e:
                    print(f"[错误] 保存进度失败: {e}")
                    import traceback
                    traceback.print_exc()
                    break
    
    def get_summary(self) -> Dict:
        if not self.progress_data:
            return {}

        total_files = len(self.progress_data.get('files', []))
        if total_files == 0:
            return {
                'total_files': 0,
                'completed_files': 0,
                'incomplete_files': 0,
                'failed_files': 0,
                'remaining_files': 0,
                'progress_percentage': 0
            }

        file_progress = self.progress_data.get('file_progress', {})
        all_stages = ['extraction', 'image_processing', 'excel_original', 'html_original', 'pdf_original', 'docx_original',
                      'translation', 'excel_translated', 'html_translated', 'pdf_translated', 'docx_translated']

        completed_count = 0
        incomplete_count = 0
        failed_count = 0

        for file_path in self.progress_data.get('files', []):
            normalized_path = file_path.replace('\\', '/')
            progress = file_progress.get(normalized_path, {})
            stages = progress.get('stages', {})
            issues = progress.get('issues', [])
            status = progress.get('status', 'pending')

            completed_stages = sum(1 for s in all_stages if self._get_stage_status(stages, s) == 'completed')

            if completed_stages == len(all_stages) and not issues:
                completed_count += 1
            elif status == 'failed':
                failed_count += 1
            else:
                incomplete_count += 1

        return {
            'total_files': total_files,
            'completed_files': completed_count,
            'incomplete_files': incomplete_count,
            'failed_files': failed_count,
            'remaining_files': incomplete_count + failed_count,
            'progress_percentage': (completed_count / total_files * 100) if total_files > 0 else 0
        }

    def cleanup_old_sessions(self, keep_days: int = 7):
        current_time = time.time()
        cutoff_time = current_time - (keep_days * 24 * 3600)
        
        for progress_file in self.progress_dir.glob("session_*.json"):
            try:
                if progress_file.stat().st_mtime < cutoff_time:
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if data.get('completed', False):
                        progress_file.unlink()
                        print(f"[清理] 已删除旧会话: {progress_file.name}")
            except Exception as e:
                print(f"[警告] 清理会话文件失败 {progress_file}: {e}")
    
    
    def save_html_fragment(self, cache_dir: str, article_idx: int, html: str, article_data: dict, is_translated: bool = False):
        try:
            subdir = "html_fragments_translated" if is_translated else "html_fragments"
            cache_path = Path(cache_dir) / ".cache" / subdir
            cache_path.mkdir(parents=True, exist_ok=True)
            
            fragment_file = cache_path / f"article_{article_idx:03d}.json"
            fragment_data = {
                'index': article_idx,
                'title': article_data.get('title', ''),
                'html': html,
                'is_translated': is_translated,
                'generated_at': datetime.now().isoformat()
            }
            
            with open(fragment_file, 'w', encoding='utf-8') as f:
                json.dump(fragment_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[警告] 保存HTML片段失败（索引{article_idx}）: {e}")

    def load_html_fragment_with_validation(self, cache_dir: str, article_idx: int, expected_title: str, is_translated: bool = False) -> Optional[str]:
        try:
            subdir = "html_fragments_translated" if is_translated else "html_fragments"
            cache_path = Path(cache_dir) / ".cache" / subdir
            fragment_file = cache_path / f"article_{article_idx:03d}.json"

            if fragment_file.exists():
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                cached_title = data.get('title', '')
                cached_html = data.get('html')

                if cached_title.strip() == expected_title.strip():
                    return cached_html
                else:
                    print(f"[警告] 缓存标题不匹配（索引{article_idx}）")
                    print(f"   期望: {expected_title[:50]}...")
                    print(f"   实际: {cached_title[:50]}...")
                    print(f"   忽略此缓存，将重新生成")
                    return None
        except Exception as e:
            print(f"[警告] 加载HTML片段失败（索引{article_idx}）: {e}")

        return None
    
    def count_html_fragments(self, cache_dir: str, is_translated: bool = False) -> int:
        try:
            subdir = "html_fragments_translated" if is_translated else "html_fragments"
            cache_path = Path(cache_dir) / ".cache" / subdir
            if cache_path.exists():
                return len(list(cache_path.glob("article_*.json")))
        except Exception:
            pass
        return 0
    
    
    def save_translation(self, cache_dir: str, article_idx: int, translation: str, article_data: dict,
                         file_signature: str = None, source_file: str = None):
        try:
            cache_path = Path(cache_dir) / ".cache" / "translation_cache"
            cache_path.mkdir(parents=True, exist_ok=True)
            
            cache_file = cache_path / f"article_{article_idx:03d}.json"
            cache_data = {
                'index': article_idx,
                'title': article_data.get('title', ''),
                'title_zh': article_data.get('title_zh', ''),
                'subtitle': article_data.get('subtitle', ''),
                'subtitle_zh': article_data.get('subtitle_zh', ''),
                'authors': article_data.get('authors', ''),
                'authors_zh': article_data.get('authors_zh', ''),
                'content_zh': translation,
                'images': article_data.get('images', []),
                'translated_at': datetime.now().isoformat()
            }

            if file_signature:
                cache_data['source_signature'] = file_signature
            if source_file:
                cache_data['source_file'] = str(source_file)
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[警告] 保存翻译缓存失败（索引{article_idx}）: {e}")
    
    def _is_valid_translation_data(self, data: dict) -> bool:
        try:
            content_zh = str(data.get('content_zh', '') or '')
            if not content_zh.strip():
                return False
            invalid_prefixes = (
                '[翻译失败',
                '[验证失败',
                '[需人工检查'
            )
            if content_zh.startswith(invalid_prefixes):
                return False
            return True
        except Exception:
            return False
    
    def load_translation(self, cache_dir: str, article_idx: int, expected_signature: Optional[str] = None) -> Optional[dict]:
        try:
            cache_path = Path(cache_dir) / ".cache" / "translation_cache"
            cache_file = cache_path / f"article_{article_idx:03d}.json"
            
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if expected_signature:
                    cached_signature = data.get('source_signature')
                    if cached_signature != expected_signature:
                        print(f"[提示] 跳过不匹配的翻译缓存: {cache_file.name}")
                        return None

                if self._is_valid_translation_data(data):
                    return {
                        'title': data.get('title', ''),
                        'title_zh': data.get('title_zh', ''),
                        'subtitle': data.get('subtitle', ''),
                        'subtitle_zh': data.get('subtitle_zh', ''),
                        'authors': data.get('authors', ''),
                        'authors_zh': data.get('authors_zh', ''),
                        'content_zh': data.get('content_zh', ''),
                        'images': data.get('images', [])
                    }
        except Exception as e:
            print(f"[警告] 加载翻译缓存失败（索引{article_idx}）: {e}")
        
        return None
    
    def count_translations(self, cache_dir: str) -> int:
        try:
            cache_path = Path(cache_dir) / ".cache" / "translation_cache"
            if not cache_path.exists():
                return 0
            count = 0
            for file in cache_path.glob("article_*.json"):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if self._is_valid_translation_data(data):
                        count += 1
                except Exception:
                    continue
            return count
        except Exception:
            return 0

