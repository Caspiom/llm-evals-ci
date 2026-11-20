"""Calibracao do juiz: compara o veredito do juiz com o rotulo humano em respostas conhecidas.

O numero que importa e o FALSO ACEITE (juiz aprova o que o humano reprova): e o erro silencioso que deixa
regressao passar no CI. Kappa de Cohen corrige o acordo pelo acaso (acordo bruto engana com classes
desbalanceadas). Com n pequeno, qualquer um destes numeros tem incerteza grande: o README diz isso.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Callable

from .judge import Judge


def carregar(path: str | Path) -> list[dict]:
    itens = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        d = json.loads(line)
        for k in ("id", "prompt", "rubric", "output", "humano_ok"):
            if k not in d:
                raise ValueError(f"{path}:{n}: campo ausente: {k}")
        itens.append(d)
    ids = [d["id"] for d in itens]
    if len(ids) != len(set(ids)):
        raise ValueError("ids duplicados na calibracao")
    return itens


def kappa(humano: list[bool], juiz: list[bool]) -> float:
    """Kappa de Cohen para duas classes. Sem variacao esperada (pe == 1) devolve 1.0 se concordam em tudo."""
    n = len(humano)
    po = sum(h == j for h, j in zip(humano, juiz)) / n
    ph, pj = sum(humano) / n, sum(juiz) / n
    pe = ph * pj + (1 - ph) * (1 - pj)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def calibrar(itens: list[dict], fabrica: Callable[[dict], Judge], min_score: int = 4) -> dict:
    humano, juiz, invalidos, falsos_aceites, falsos_rejeitos = [], [], [], [], []
    for d in itens:
        v = fabrica(d).grade(d["id"], d["prompt"], d["output"], d["rubric"])
        if v.score is None:
            invalidos.append(d["id"])
        aprovou = v.score is not None and v.score >= min_score  # invalido nunca aprova
        humano.append(bool(d["humano_ok"]))
        juiz.append(aprovou)
        if aprovou and not d["humano_ok"]:
            falsos_aceites.append(d["id"])
        if not aprovou and d["humano_ok"]:
            falsos_rejeitos.append(d["id"])
    reprovadas = sum(not h for h in humano)
    return {
        "n": len(itens),
        "acordo": round(sum(h == j for h, j in zip(humano, juiz)) / len(itens), 4),
        "kappa": round(kappa(humano, juiz), 4),
        "falso_aceite": len(falsos_aceites), "de_reprovadas": reprovadas,
        "falso_rejeito": len(falsos_rejeitos), "de_aprovadas": len(humano) - reprovadas,
        "invalidos": invalidos,
        "ids_falso_aceite": falsos_aceites, "ids_falso_rejeito": falsos_rejeitos,
    }


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


class KeywordProvider:
    """Juiz-base SEM modelo: nota 5 se todos os `termos` aparecem na resposta e nenhum `proibido` aparece.
    Le a resposta do bloco <resposta> do prompt do juiz (prova que os delimitadores funcionam). E o piso
    que um juiz LLM precisa superar, nao um juiz de verdade."""

    name = "keyword"

    def __init__(self, termos: list[str], proibidos: list[str] = ()):
        self.termos, self.proibidos = [_norm(t) for t in termos], [_norm(t) for t in proibidos]
        self.last_usage = None

    def complete(self, case_id: str, prompt: str) -> str:
        m = re.search(r"<resposta>\n(.*?)\n</resposta>", prompt, re.S)
        resposta = _norm(m.group(1)) if m else ""
        ok = all(t in resposta for t in self.termos) and not any(p in resposta for p in self.proibidos)
        return json.dumps({"score": 5 if ok else 1, "reason": "palavras-chave"})
