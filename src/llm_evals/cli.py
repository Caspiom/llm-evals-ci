"""CLI: llm-evals run --cases ... --provider fixture --fixtures ... [--baseline ...]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cases import load_cases
from .providers import get_provider
from .runner import compare, run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="llm-evals")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="roda a suite e aplica o gate de regressão")
    r.add_argument("--cases", required=True)
    r.add_argument("--provider", default="fixture")
    r.add_argument("--fixtures", help="JSON {case_id: resposta} p/ provider fixture")
    r.add_argument("--baseline", default="evals/baseline.json")
    r.add_argument("--min-pass-rate", type=float, default=0.0)
    r.add_argument("--out", default="results/report.json")
    r.add_argument("--update-baseline", action="store_true", help="grava o resultado como novo baseline")
    a = p.parse_args(argv)

    provider = get_provider(a.provider, fixtures=a.fixtures)
    report = run(load_cases(a.cases), provider)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    for res in report.results:
        mark = "PASS" if res.passed else f"FAIL {res.failed_checks}"
        print(f"  {res.id:<28} {mark}")
    print(f"pass_rate: {report.pass_rate:.2%} ({sum(x.passed for x in report.results)}/{len(report.results)})")

    if a.update_baseline:
        Path(a.baseline).write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"baseline atualizado: {a.baseline}")
        return 0

    problems = compare(report, a.baseline, a.min_pass_rate)
    for prob in problems:
        print(f"GATE: {prob}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
