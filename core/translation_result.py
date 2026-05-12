from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TranslationStatus(Enum):
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    IDENTICAL_TO_SOURCE = "identical_to_source"
    LLM_ERROR = "llm_error"
    EMPTY_INPUT = "empty_input"


class ErrorCategory(Enum):
    VALIDATION = "validation"
    IDENTICAL = "identical"
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    AUTH = "auth"
    CLIENT = "client"
    JSON_PARSE = "json_parse"
    TRUNCATION = "truncation"
    UNKNOWN = "unknown"


@dataclass
class TranslationError:
    status: TranslationStatus
    category: ErrorCategory
    message: str
    original_text: str
    detail: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.category in (ErrorCategory.AUTH,)


@dataclass
class TranslationResult:
    status: TranslationStatus
    translated_text: str
    error: Optional[TranslationError] = None
    latency_ms: float = 0.0
    retry_count: int = 0

    @property
    def is_success(self) -> bool:
        return self.status == TranslationStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status != TranslationStatus.SUCCESS and self.status != TranslationStatus.EMPTY_INPUT

    def to_legacy_string(self) -> str:
        if self.status == TranslationStatus.SUCCESS:
            return self.translated_text
        if self.status == TranslationStatus.VALIDATION_FAILED:
            return f"[验证失败-原文] {self.error.original_text}"
        if self.status == TranslationStatus.IDENTICAL_TO_SOURCE:
            return f"[需人工检查-译文与原文相同] {self.error.original_text}"
        if self.status == TranslationStatus.LLM_ERROR:
            return f"[翻译失败: {self.error.message}]"
        return self.translated_text


def success_result(text: str, latency_ms: float = 0.0, retry_count: int = 0) -> TranslationResult:
    return TranslationResult(
        status=TranslationStatus.SUCCESS,
        translated_text=text,
        latency_ms=latency_ms,
        retry_count=retry_count,
    )


def error_result(
    status: TranslationStatus,
    category: ErrorCategory,
    message: str,
    original_text: str,
    detail: Optional[str] = None,
    latency_ms: float = 0.0,
    retry_count: int = 0,
) -> TranslationResult:
    return TranslationResult(
        status=status,
        translated_text=original_text,
        error=TranslationError(
            status=status,
            category=category,
            message=message,
            original_text=original_text,
            detail=detail,
        ),
        latency_ms=latency_ms,
        retry_count=retry_count,
    )
