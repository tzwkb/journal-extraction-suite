import threading
from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict


@dataclass
class MetricsSnapshot:
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_by_category: Dict[str, int] = field(default_factory=dict)
    error_by_status: Dict[str, int] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe, lightweight metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total = 0
        self._success = 0
        self._failure = 0
        self._latencies_ms: List[float] = []
        self._error_by_category: Dict[str, int] = defaultdict(int)
        self._error_by_status: Dict[str, int] = defaultdict(int)
        self._max_latency_samples = 1000

    def record(self, result: "TranslationResult") -> None:
        with self._lock:
            self._total += 1
            if result.is_success:
                self._success += 1
            else:
                self._failure += 1
                if result.error:
                    self._error_by_category[result.error.category.value] += 1
                    self._error_by_status[result.error.status.value] += 1

            if result.latency_ms > 0:
                self._latencies_ms.append(result.latency_ms)
                if len(self._latencies_ms) > self._max_latency_samples:
                    self._latencies_ms = self._latencies_ms[-self._max_latency_samples:]

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            latencies = sorted(self._latencies_ms) if self._latencies_ms else []
            n = len(latencies)
            return MetricsSnapshot(
                total_requests=self._total,
                success_count=self._success,
                failure_count=self._failure,
                average_latency_ms=sum(latencies) / n if n > 0 else 0.0,
                p95_latency_ms=_percentile(latencies, 95) if n > 0 else 0.0,
                p99_latency_ms=_percentile(latencies, 99) if n > 0 else 0.0,
                error_by_category=dict(self._error_by_category),
                error_by_status=dict(self._error_by_status),
            )

    @property
    def total_requests(self) -> int:
        with self._lock:
            return self._total

    def success_rate(self) -> float:
        with self._lock:
            return self._success / self._total if self._total > 0 else 0.0


def _percentile(sorted_data: List[float], pct: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * pct / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    if c == f:
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
