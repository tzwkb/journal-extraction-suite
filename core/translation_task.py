import threading
from enum import Enum
from typing import Optional, Callable


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranslationTask:
    """
    Non-blocking handle for translate_dataframe().
    Wraps the synchronous call in a background daemon thread.
    """

    def __init__(
        self,
        translator,
        df,
        cache_dir: Optional[str] = None,
        progress_manager=None,
        file_signature: Optional[str] = None,
        source_file: Optional[str] = None,
    ):
        self._translator = translator
        self._df = df
        self._cache_dir = cache_dir
        self._progress_manager = progress_manager
        self._file_signature = file_signature
        self._source_file = source_file

        self._state = TaskState.PENDING
        self._result = None
        self._error: Optional[Exception] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._on_complete: Optional[Callable[["TranslationTask"], None]] = None

    @property
    def state(self) -> TaskState:
        with self._lock:
            return self._state

    @property
    def result(self):
        with self._lock:
            return self._result

    @property
    def error(self) -> Optional[Exception]:
        with self._lock:
            return self._error

    @property
    def is_done(self) -> bool:
        return self.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)

    def on_complete(self, callback: Callable[["TranslationTask"], None]) -> "TranslationTask":
        self._on_complete = callback
        return self

    def start(self) -> "TranslationTask":
        with self._lock:
            if self._state != TaskState.PENDING:
                raise RuntimeError(f"Cannot start task in state {self._state}")
            self._state = TaskState.RUNNING

        self._thread = threading.Thread(target=self._run, daemon=True, name="TranslationTask")
        self._thread.start()
        return self

    def cancel(self) -> bool:
        with self._lock:
            if self._state == TaskState.RUNNING:
                self._state = TaskState.CANCELLED
                return True
            return False

    def wait(self, timeout: Optional[float] = None) -> "TranslationTask":
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        return self

    def _run(self):
        try:
            with self._lock:
                if self._state == TaskState.CANCELLED:
                    return
            df_result = self._translator.translate_dataframe(
                self._df,
                cache_dir=self._cache_dir,
                progress_manager=self._progress_manager,
                file_signature=self._file_signature,
                source_file=self._source_file,
            )
            with self._lock:
                if self._state != TaskState.CANCELLED:
                    self._result = df_result
                    self._state = TaskState.COMPLETED
        except Exception as e:
            with self._lock:
                if self._state != TaskState.CANCELLED:
                    self._error = e
                    self._state = TaskState.FAILED
        finally:
            if self._on_complete:
                try:
                    self._on_complete(self)
                except Exception:
                    pass
