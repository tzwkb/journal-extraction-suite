from dataclasses import dataclass
from typing import List


@dataclass
class ConfigViolation:
    severity: str       # "error" or "warning"
    attribute: str      # e.g. "PDF_API_KEY"
    message: str


class ConfigValidator:

    @staticmethod
    def validate(user_config) -> List[ConfigViolation]:
        violations = []

        _check_api_key(violations, user_config, 'PDF_API_KEY')
        _check_api_key(violations, user_config, 'TRANSLATION_API_KEY')
        _check_api_key(violations, user_config, 'HTML_API_KEY')

        _check_positive_int(violations, user_config, 'MAX_WORKERS', min_val=1)
        _check_positive_int(violations, user_config, 'TRANSLATION_MAX_WORKERS', min_val=1)
        _check_positive_int(violations, user_config, 'MAX_RETRIES', min_val=0)
        _check_positive_int(violations, user_config, 'PAGES_PER_BATCH', min_val=1, max_val=50)
        _check_positive_int(violations, user_config, 'MAX_CONCURRENT_PDF_FILES', min_val=1)
        _check_positive_int(violations, user_config, 'TRANSLATION_CONTENT_MAX_CHARS', min_val=100)
        _check_positive_int(violations, user_config, 'PDF_MAX_TOKENS', min_val=1)
        _check_positive_int(violations, user_config, 'TRANSLATION_MAX_TOKENS', min_val=1)
        _check_positive_int(violations, user_config, 'DOCX_MAX_TOKENS', min_val=1)
        _check_positive_int(violations, user_config, 'OUTLINE_PAGES_PER_SEGMENT', min_val=1)

        _check_timeout_tuple(violations, user_config, 'PDF_API_TIMEOUT')
        _check_timeout_tuple(violations, user_config, 'TRANSLATION_TIMEOUT')
        _check_timeout_tuple(violations, user_config, 'HTML_TIMEOUT')

        _check_temperature(violations, user_config, 'PDF_TEMPERATURE')
        _check_temperature(violations, user_config, 'TRANSLATION_TEMPERATURE')
        _check_temperature(violations, user_config, 'HTML_TEMPERATURE')

        _check_ratio(violations, user_config, 'TITLE_SIMILARITY_THRESHOLD')
        _check_ratio(violations, user_config, 'CONTENT_DUPLICATE_THRESHOLD')

        if hasattr(user_config, 'OVERLAP_PAGES') and hasattr(user_config, 'PAGES_PER_BATCH'):
            if user_config.OVERLAP_PAGES >= user_config.PAGES_PER_BATCH:
                violations.append(ConfigViolation(
                    "error", "OVERLAP_PAGES",
                    f"OVERLAP_PAGES ({user_config.OVERLAP_PAGES}) must be less than PAGES_PER_BATCH ({user_config.PAGES_PER_BATCH})"
                ))

        if hasattr(user_config, 'OVERLAP_PAGES') and user_config.OVERLAP_PAGES < 0:
            violations.append(ConfigViolation(
                "error", "OVERLAP_PAGES",
                f"OVERLAP_PAGES must be >= 0, got {user_config.OVERLAP_PAGES}"
            ))

        return violations


def _check_api_key(violations, cfg, attr):
    val = getattr(cfg, attr, '')
    if not val or val.strip() == '' or val == 'your-api-key-here':
        violations.append(ConfigViolation("error", attr, f"{attr} is empty or set to placeholder"))


def _check_positive_int(violations, cfg, attr, min_val=1, max_val=None):
    val = getattr(cfg, attr, None)
    if val is None:
        return
    if not isinstance(val, int) or val < min_val:
        violations.append(ConfigViolation("error", attr, f"{attr} must be int >= {min_val}, got {val}"))
    if max_val is not None and val > max_val:
        violations.append(ConfigViolation("warning", attr, f"{attr} exceeds recommended max {max_val}, got {val}"))


def _check_ratio(violations, cfg, attr):
    val = getattr(cfg, attr, None)
    if val is None:
        return
    if not isinstance(val, (int, float)) or val < 0 or val > 1:
        violations.append(ConfigViolation("error", attr, f"{attr} must be between 0 and 1, got {val}"))


def _check_timeout_tuple(violations, cfg, attr):
    val = getattr(cfg, attr, None)
    if val is None:
        return
    if not isinstance(val, tuple) or len(val) != 2:
        violations.append(ConfigViolation("error", attr, f"{attr} must be a tuple of (connect_timeout, read_timeout)"))
    elif val[0] <= 0 or val[1] <= 0:
        violations.append(ConfigViolation("error", attr, f"{attr} values must be positive"))


def _check_temperature(violations, cfg, attr):
    val = getattr(cfg, attr, None)
    if val is None:
        return
    if not isinstance(val, (int, float)) or val < 0 or val > 2:
        violations.append(ConfigViolation("warning", attr, f"{attr} should be 0-2, got {val}"))
