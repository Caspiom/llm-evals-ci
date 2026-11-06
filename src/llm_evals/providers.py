"""Providers = quem gera a resposta. Interface mínima: prompt + id -> texto.

`fixture` lê respostas gravadas de um JSON: grátis, determinístico, ideal p/ CI e para
validar o pipeline antes de gastar com API paga.

`anthropic` chama a Messages API (só stdlib) com TETO DE CUSTO DURO: antes de cada
chamada confere `gasto + pior caso <= teto`, onde pior caso = entrada (limite superior)
+ `max_tokens` de saída, e não chama se estourar. Depois da chamada soma o custo real.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class BudgetExceeded(Exception):
    """O pior caso da próxima chamada passaria do teto: o modelo NÃO foi chamado."""


class ProviderError(Exception):
    """Falha do provider que não é de orçamento (auth, 4xx, rede esgotada...)."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float
    stop_reason: str | None = None


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


# US$ por milhão de tokens (entrada, saída), prompts até 100k tokens.
# Fonte: https://platform.claude.com/docs/en/about-claude/pricing (conferido em 2026-11-05).
# Modelo fora desta tabela exige --price-in/--price-out: nunca assumimos um preço.
PRICES_USD_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}
PRICE_TIER_LIMIT_TOKENS = 100_000  # acima disso o preço muda: não suportado aqui
RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
NOT_SENT = (ConnectionRefusedError, socket.gaierror)  # nunca chegou ao servidor: não cobra
PROMPT_OVERHEAD_TOKENS = 32


class AnthropicProvider:
    def __init__(
        self,
        model: str = "claude-haiku-5-5",
        *,
        max_cost_usd: float,
        max_tokens: int = 256,
        price_in: float | None = None,
        price_out: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if max_cost_usd <= 0:
            raise ValueError("max_cost_usd deve ser > 0 (teto obrigatório)")
        if price_in is None or price_out is None:
            if model not in PRICES_USD_PER_MTOK:
                raise ValueError(f"preço do modelo {model!r} desconhecido: informe price_in e price_out")
            price_in, price_out = PRICES_USD_PER_MTOK[model]
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY ausente no ambiente")
        self.model, self.name = model, f"anthropic:{model}"
        self.max_cost_usd, self.max_tokens = max_cost_usd, max_tokens
        self.price_in, self.price_out = price_in, price_out
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
        self.timeout, self.retries, self._sleep = timeout, retries, sleep
        self.spent_usd = 0.0
        self.last_usage: Usage | None = None

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.price_in + output_tokens * self.price_out) / 1_000_000

    def worst_case_usd(self, prompt: str) -> float:
        """Limite superior: cada byte do prompt vira no máximo 1 token (o tokenizer novo gera
        ~30% mais tokens que o antigo, então chars/4 NÃO é limite) + a saída inteira."""
        return self._cost(self._input_bound(prompt), self.max_tokens)

    @staticmethod
    def _input_bound(prompt: str) -> int:
        return len(prompt.encode("utf-8")) + PROMPT_OVERHEAD_TOKENS

    def _precheck(self, prompt: str) -> float:
        if self._input_bound(prompt) > PRICE_TIER_LIMIT_TOKENS:
            raise ProviderError("prompt pode passar de 100k tokens: o preço muda e não é suportado")
        worst = self.worst_case_usd(prompt)
        if self.spent_usd + worst > self.max_cost_usd:
            raise BudgetExceeded(
                f"gasto US$ {self.spent_usd:.6f} + pior caso US$ {worst:.6f} > teto US$ {self.max_cost_usd:.6f}"
            )
        return worst

    def _request(self, prompt: str) -> urllib.request.Request:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "thinking": {"type": "disabled"},  # thinking é cobrado como saída: fora do teto previsível
            "messages": [{"role": "user", "content": prompt}],
        }
        return urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )

    def complete(self, case_id: str, prompt: str) -> str:
        self.last_usage = None
        attempt = 0
        while True:
            worst = self._precheck(prompt)  # a cada tentativa, inclusive retry
            wait = 0.5 * 2**attempt
            try:
                with urllib.request.urlopen(self._request(prompt), timeout=self.timeout) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as e:
                if e.code not in RETRYABLE_STATUS:
                    raise ProviderError(f"HTTP {e.code} da API") from None
                retry_after = e.headers.get("retry-after")
                if retry_after and retry_after.replace(".", "", 1).isdigit():
                    wait = min(float(retry_after), 8.0)
                err = f"HTTP {e.code} da API"
            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                if not isinstance(getattr(e, "reason", e), NOT_SENT):
                    # pode ter chegado e sido cobrado sem sabermos: assume o pior caso
                    self.spent_usd += worst
                err = f"falha de rede: {type(e).__name__}"
            else:
                return self._parse(raw, worst)
            if attempt >= self.retries:
                raise ProviderError(f"{err} após {attempt + 1} tentativas")
            self._sleep(min(wait, 8.0))
            attempt += 1

    def _parse(self, raw: bytes, worst: float) -> str:
        try:
            data = json.loads(raw)
            usage = data["usage"]
            in_tok, out_tok = int(usage["input_tokens"]), int(usage["output_tokens"])
            text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        except (ValueError, KeyError, TypeError):
            self.spent_usd += worst  # cobrada, mas não sabemos quanto: pior caso
            raise ProviderError("resposta inesperada da API") from None
        cost = self._cost(in_tok, out_tok)
        self.spent_usd += cost
        self.last_usage = Usage(in_tok, out_tok, cost, data.get("stop_reason"))
        return text


def get_provider(name: str, **opts) -> Provider:
    if name == "fixture":
        return FixtureProvider(opts["fixtures"])
    if name == "anthropic":
        return AnthropicProvider(
            opts.get("model") or "claude-haiku-5-5",
            max_cost_usd=opts["max_cost_usd"],
            max_tokens=opts.get("max_tokens") or 256,
            price_in=opts.get("price_in"),
            price_out=opts.get("price_out"),
        )
    raise ValueError(f"provider desconhecido: {name!r}")
