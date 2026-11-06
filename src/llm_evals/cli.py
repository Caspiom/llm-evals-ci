"""CLI: llm-evals run --cases ... --provider fixture|anthropic [--baseline ...]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cases import load_cases
from .providers import ProviderError, get_provider
from .runner import compare, run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="llm-evals")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="roda a suite e aplica o gate de regressão")
    r.add_argument("--cases", required=True)
    r.add_argument("--provider", default="fixture", choices=["fixture", "anthropic"])
    r.add_argument("--fixtures", help="JSON {case_id: resposta} p/ provider fixture")
    r.add_argument("--model", help="provider anthropic (padrão: claude-haiku-5-5)")
    r.add_argument("--max-cost-usd", type=float, help="TETO duro em US$ (obrigatório no provider anthropic)")
    r.add_argument("--max-tokens", type=int, default=256, help="saída máxima por caso (entra no pior caso do teto)")
    r.add_argument("--price-in", type=float, help="US$/MTok de entrada (obrigatório p/ modelo fora da tabela)")
    r.add_argument("--price-out", type=float, help="US$/MTok de saída (obrigatório p/ modelo fora da tabela)")
    r.add_argument("--baseline", default="evals/baseline.json")
    r.add_argument("--min-pass-rate", type=float, default=0.0)
    r.add_argument("--out", default="results/report.json")
    r.add_argument("--update-baseline", action="store_true", help="grava o resultado como novo baseline")
    a = p.parse_args(argv)

    if a.provider == "anthropic" and not a.max_cost_usd:
        p.error("--max-cost-usd é obrigatório com --provider anthropic (sem teto não roda)")
    if a.provider == "fixture" and not a.fixtures:
        p.error("--fixtures é obrigatório com --provider fixture")
    try:
        provider = get_provider(
            a.provider, fixtures=a.fixtures, model=a.model, max_cost_usd=a.max_cost_usd,
            max_tokens=a.max_tokens, price_in=a.price_in, price_out=a.price_out,
        )
    except (ValueError, ProviderError) as e:
        p.error(str(e))
    report = run(load_cases(a.cases), provider)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    for res in report.results:
        mark = "PASS" if res.passed else f"FAIL {res.failed_checks}"
        print(f"  {res.id:<28} {mark}")
    print(f"pass_rate: {report.pass_rate:.2%} ({sum(x.passed for x in report.results)}/{len(report.results)})")
    if report.max_cost_usd is not None:
        d = report.to_dict()
        print(f"custo: US$ {d['cost_usd']:.6f} de teto US$ {report.max_cost_usd:.6f} | "
              f"latência p50 {d['latency_ms_p50']} ms, p95 {d['latency_ms_p95']} ms")

    if a.update_baseline:
        if any(x.status != "ok" for x in report.results):
            print("baseline NÃO atualizado: há casos sem resposta (teto/erro)", file=sys.stderr)
            return 1
        Path(a.baseline).write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"baseline atualizado: {a.baseline}")
        return 0

    problems = compare(report, a.baseline, a.min_pass_rate)
    for prob in problems:
        print(f"GATE: {prob}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
