"""Carrega casos de avaliação de arquivos JSONL (um caso por linha)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    checks: list[dict] = field(default_factory=list)  # ex.: {"type": "contains", "value": "Brasília"}


def load_cases(path: str | Path) -> list[Case]:
    cases: list[Case] = []
    seen: set[str] = set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        for key in ("id", "prompt", "checks"):
            if key not in raw:
                raise ValueError(f"{path}:{n}: campo obrigatório ausente: {key}")
        if raw["id"] in seen:
            raise ValueError(f"{path}:{n}: id duplicado: {raw['id']}")
        seen.add(raw["id"])
        cases.append(Case(id=raw["id"], prompt=raw["prompt"], checks=raw["checks"]))
    return cases
