from __future__ import annotations

import re

_LEADING_TIMER = re.compile(
    r"^\s*осталось\s+\d{1,2}:\d{2}\s*",
    re.IGNORECASE,
)
_TIMER_ARTIFACT = re.compile(
    r"(?<!\w)осталось\s+\d{1,2}:\d{2}(?!\d)",
    re.IGNORECASE,
)
_TIMER_WORD = "осталось"
_PARTIAL_TIMER = re.compile(r"\d{0,2}(?::\d{0,2})?")


def strip_model_output_artifact(text: str) -> str:
    """Remove UI timers accidentally emitted before or during an answer."""
    return _TIMER_ARTIFACT.sub("", _LEADING_TIMER.sub("", text, count=1))


def clean_model_output(text: str) -> str:
    return strip_model_output_artifact(text).strip()


def _could_be_leading_timer(text: str) -> bool:
    candidate = text.lstrip().casefold()
    if len(candidate) <= len(_TIMER_WORD):
        return _TIMER_WORD.startswith(candidate)
    if not candidate.startswith(_TIMER_WORD):
        return False
    remainder = candidate[len(_TIMER_WORD) :]
    if not remainder[0].isspace():
        return False
    return bool(_PARTIAL_TIMER.fullmatch(remainder.strip()))


class ModelOutputStreamFilter:
    """Keep a possible timer prefix buffered until it can be classified."""

    def __init__(self) -> None:
        self._raw = ""
        self._emitted = ""

    def push(self, chunk: str) -> str:
        self._raw += chunk
        if not self._emitted and _could_be_leading_timer(self._raw):
            return ""

        cleaned = strip_model_output_artifact(self._raw)
        if cleaned.startswith(self._emitted):
            delta = cleaned[len(self._emitted) :]
        else:
            delta = cleaned
        self._emitted = cleaned
        return delta

    def final(self) -> str:
        return clean_model_output(self._raw)
