"""Logging utilities for Promptya.

Provides a filter that redacts sensitive data from log records before they
are emitted. This prevents accidental leakage of secrets, API keys, passwords,
and credit card numbers in production logs.
"""

import logging
import re
from typing import Any


# Patterns that match sensitive data we should never log.
# These are applied to the formatted message string.
_SECRET_PATTERNS = [
    # API keys (generic patterns)
    (re.compile(r"(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    # Bearer tokens
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"), "Bearer ***REDACTED***"),
    # Database URLs with passwords
    (re.compile(r"(postgres|mysql|redis)://[^:]+:[^@]+@"), r"\1://***REDACTED***@"),
    # AWS keys
    (re.compile(r"(?i)(aws[_-]?access[_-]?key|aws[_-]?secret[_-]?key)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    # Credit card numbers (basic pattern)
    (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "****-****-****-****"),
    # Email addresses in auth contexts (optional - can be PII)
    # (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "***@***.***"),
]


class RedactSecretsFilter(logging.Filter):
    """Filter that redacts sensitive information from log records.

    This filter examines the formatted log message and replaces known
    sensitive patterns with ***REDACTED*** placeholders.

    It also redacts sensitive fields from the log record's __dict__ if they
    are added via extra=... in logging calls.
    """

    SENSITIVE_KEYS = {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "sessionid",
        "csrftoken",
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "social_security",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact sensitive keys from record.__dict__ (extra fields)
        for key in list(record.__dict__.keys()):
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS):
                record.__dict__[key] = "***REDACTED***"

        # Redact sensitive patterns from the message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        # Also redact args if they are strings
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self._redact(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)

        return True

    def _redact(self, text: str) -> str:
        """Apply all redaction patterns to the text."""
        for pattern, replacement in _SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        return text