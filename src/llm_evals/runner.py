"""Executa os casos num provider e compara com o baseline."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .cases import Case
from .providers import Provider
from .scorers import run_check


@dataclass
class CaseResult:
    id: str
    passed: bool
    failed_checks: list[str]
    latency_ms: float
    output: str


@dataclass
class Report:
    provider: str
    results: list[CaseResult]

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "pass_rate": round(self.pass_rate, 4),
            "total": len(self.results),
            "passed": sum(r.passed for r in self.results),
            "results": [asdict(r) for r in self.results],
        }


def run(cases: list[Case], provider: Provider) -> Report:
    results = []
    for case in cases:
        t0 = time.perf_counter()
        output = provider.complete(case.id, case.prompt)
        latency = (time.perf_counter() - t0) * 1000
        failed = [c["type"] for c in case.checks if not run_check(output, c)]
        results.append(CaseResult(case.id, not failed, failed, round(latency, 2), output))
    return Report(provider.name, results)


def compare(report: Report, baseline_path: str | Path, min_pass_rate: float = 0.0) -> list[str]:
    """Lista de motivos de falha do gate (vazia = passou).

    Regressão = caso que passava no baseline e agora falha, ou taxa abaixo do mínimo.
    """
    problems: list[str] = []
    if report.pass_rate < min_pass_rate:
        problems.append(f"pass_rate {report.pass_rate:.2%} < mínimo {min_pass_rate:.2%}")
    path = Path(baseline_path)
    if path.exists():
        base = json.loads(path.read_text(encoding="utf-8"))
        before = {r["id"] for r in base["results"] if r["passed"]}
        for r in report.results:
            if r.id in before and not r.passed:
                problems.append(f"regressão em {r.id}: falhou {r.failed_checks}")
    return problems
