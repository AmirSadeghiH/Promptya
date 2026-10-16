"""Lightweight, conservative anti-spam heuristics for user text.

These rules are deliberately blunt and *only* reject the single submission in
front of them — they never punish or lock an account.  That is the safe-recovery
requirement: a false positive costs the author one comment they can retype, not
their account.  Anything stronger belongs to a human moderator reviewing a
report, not to a regex deciding to ban someone.
"""

import re

#: More than this many URLs in one short comment is link spam, not conversation.
MAX_LINKS = 3

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def count_links(text):
    if not text:
        return 0
    # Collapsed runs so "https:// a . com" cannot hide behind spaces.
    return len(_URL_RE.findall(text))


def normalize(text):
    return _WHITESPACE_RE.sub(" ", (text or "").strip()).lower()


def looks_like_spam(content, *, previous_contents=None):
    """Return a short reason string when *content* looks like spam, else ``None``.

    ``previous_contents`` is an iterable of the same author's recent comment
    bodies; an exact duplicate (ignoring case and whitespace) is treated as
    flooding.
    """
    if count_links(content) > MAX_LINKS:
        return "too_many_links"

    normalized = normalize(content)
    if previous_contents and normalized:
        for previous in previous_contents:
            if normalize(previous) == normalized:
                return "duplicate"
    return None
