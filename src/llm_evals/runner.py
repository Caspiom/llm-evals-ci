"""Executa os casos num provider e compara com o baseline."""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .cases import Case
from .providers import BudgetExceeded, Provider, ProviderError
from .scorers import run_check

OK, SKIPPED_BUDGET, ERROR = "ok", "skipped_budget", "error"


@dataclass
class CaseResult:
    id: str
    passed: bool
    failed_checks: list[str]
    latency_ms: float
    output: str
    status: str = OK  # ok | skipped_budget (modelo NÃO chamado) | error
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None


def _percentile(values: list[float], p: float) -> float:
    """Nearest-rank. Com poucas amostras p95 vira o máximo: o README diz isso."""
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


@dataclass
class Report:
    provider: str
    results: list[CaseResult]
    max_cost_usd: float | None = None

    @property
    def pass_rate(self) -> float:
        # caso pulado/erro conta como NÃO passou: execução incompleta nunca fica verde
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.results)

    def to_dict(self) -> dict:
        ran = [r for r in self.results if r.status == OK]
        lat = [r.latency_ms for r in ran]
        return {
            "provider": self.provider,
            "pass_rate": round(self.pass_rate, 4),
            "total": len(self.results),
            "passed": sum(r.passed for r in self.results),
            "not_run": len(self.results) - len(ran),
            "cost_usd": round(self.cost_usd, 8),
            "max_cost_usd": self.max_cost_usd,
            "cost_per_case_usd": round(self.cost_usd / len(ran), 8) if ran else 0.0,
            "input_tokens": sum(r.input_tokens for r in self.results),
            "output_tokens": sum(r.output_tokens for r in self.results),
            "latency_ms_p50": round(_percentile(lat, 50), 2),
            "latency_ms_p95": round(_percentile(lat, 95), 2),
            "results": [asdict(r) for r in self.results],
        }


def run(cases: list[Case], provider: Provider) -> Report:
    results: list[CaseResult] = []
    budget_out = False
    for case in cases:
        if budget_out:  # teto atingido: o resto nem chega ao provider
            results.append(CaseResult(case.id, False, [SKIPPED_BUDGET], 0.0, "", SKIPPED_BUDGET))
            continue
        t0 = time.perf_counter()
        try:
            output = provider.complete(case.id, case.prompt)
        except BudgetExceeded as e:
            budget_out = True
            results.append(CaseResult(case.id, False, [SKIPPED_BUDGET], 0.0, str(e), SKIPPED_BUDGET))
            continue
        except ProviderError as e:
            latency = (time.perf_counter() - t0) * 1000
            results.append(CaseResult(case.id, False, [ERROR], round(latency, 2), str(e), ERROR))
            continue
        latency = (time.perf_counter() - t0) * 1000
        failed = [c["type"] for c in case.checks if not run_check(output, c)]
        usage = getattr(provider, "last_usage", None)
        extra = (
            dict(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                 cost_usd=usage.cost_usd, stop_reason=usage.stop_reason)
            if usage else {}
        )
        results.append(CaseResult(case.id, not failed, failed, round(latency, 2), output, **extra))
    return Report(provider.name, results, getattr(provider, "max_cost_usd", None))


def compare(report: Report, baseline_path: str | Path, min_pass_rate: float = 0.0) -> list[str]:
    """Lista de motivos de falha do gate (vazia = passou).

    Regressão = caso que passava no baseline e agora falha, ou taxa abaixo do mínimo.
    Caso que não rodou (teto de custo / erro do provider) também reprova o gate.
    """
    problems: list[str] = []
    not_run = [r for r in report.results if r.status != OK]
    if not_run:
        problems.append("casos sem resposta (" + ", ".join(f"{r.id}:{r.status}" for r in not_run) + ")")
    if report.pass_rate < min_pass_rate:
        problems.append(f"pass_rate {report.pass_rate:.2%} < mínimo {min_pass_rate:.2%}")
    path = Path(baseline_path)
    if path.exists():
        base = json.loads(path.read_text(encoding="utf-8"))
        before = {r["id"] for r in base["results"] if r["passed"]}
        for r in report.results:
            if r.status == OK and r.id in before and not r.passed:
                problems.append(f"regressão em {r.id}: falhou {r.failed_checks}")
    return problems
