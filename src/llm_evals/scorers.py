"""Checks determinísticos: cada um recebe a saída do modelo e devolve True/False."""
from __future__ import annotations

import json
import re
from typing import Callable

Scorer = Callable[[str, dict], bool]


def _contains(output: str, check: dict) -> bool:
    return check["value"].lower() in output.lower()


def _not_contains(output: str, check: dict) -> bool:
    return not _contains(output, check)


def _equals(output: str, check: dict) -> bool:
    return output.strip() == check["value"].strip()


def _regex(output: str, check: dict) -> bool:
    return re.search(check["value"], output) is not None


def _is_json(output: str, check: dict) -> bool:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False
    required = check.get("keys", [])
    return isinstance(data, dict) and all(k in data for k in required)


def _max_chars(output: str, check: dict) -> bool:
    return len(output) <= int(check["value"])


SCORERS: dict[str, Scorer] = {
    "contains": _contains,
    "not_contains": _not_contains,
    "equals": _equals,
    "regex": _regex,
    "is_json": _is_json,
    "max_chars": _max_chars,
}


def run_check(output: str, check: dict) -> bool:
    try:
        scorer = SCORERS[check["type"]]
    except KeyError:
        raise ValueError(f"tipo de check desconhecido: {check.get('type')!r}") from None
    return scorer(output, check)
