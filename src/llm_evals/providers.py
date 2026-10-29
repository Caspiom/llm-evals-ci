"""Providers = quem gera a resposta. Interface mínima: prompt + id -> texto.

`fixture` lê respostas gravadas de um JSON: grátis, determinístico, ideal p/ CI e
para validar o pipeline antes de gastar com API paga. Providers reais entram aqui depois.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class Provider(Protocol):
    name: str

    def complete(self, case_id: str, prompt: str) -> str: ...


class FixtureProvider:
    name = "fixture"

    def __init__(self, path: str | Path):
        self._answers: dict[str, str] = json.loads(Path(path).read_text(encoding="utf-8"))

    def complete(self, case_id: str, prompt: str) -> str:
        if case_id not in self._answers:
            raise KeyError(f"fixture sem resposta para o caso {case_id!r}")
        return self._answers[case_id]


def get_provider(name: str, **opts) -> Provider:
    if name == "fixture":
        return FixtureProvider(opts["fixtures"])
    raise ValueError(f"provider desconhecido: {name!r}")
