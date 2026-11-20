"""Calibra o juiz contra o rotulo humano: python scripts/calibrar_juiz.py --judge keyword|anthropic

keyword   : juiz-base por palavras-chave, gratis (o piso que o juiz LLM precisa superar).
anthropic : juiz LLM de verdade. GASTA: exige --max-cost-usd (teto duro) e ANTHROPIC_API_KEY no ambiente.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_evals.calibracao import KeywordProvider, calibrar, carregar  # noqa: E402
from llm_evals.judge import Judge  # noqa: E402
from llm_evals.providers import AnthropicProvider  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["keyword", "anthropic"], default="keyword")
    ap.add_argument("--data", default="evals/judge_calibracao.jsonl")
    ap.add_argument("--max-cost-usd", type=float)
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--out", default="results/calibracao-{judge}.json")
    a = ap.parse_args()
    itens = carregar(a.data)
    if a.judge == "keyword":
        fabrica = lambda d: Judge(KeywordProvider(d.get("termos", []), d.get("proibidos", [])))  # noqa: E731
        custo = lambda: 0.0  # noqa: E731
    else:
        if not a.max_cost_usd:
            ap.error("--max-cost-usd e obrigatorio com --judge anthropic (sem teto nao roda)")
        prov = AnthropicProvider(a.model, max_cost_usd=a.max_cost_usd, max_tokens=96)
        j = Judge(prov)
        fabrica = lambda d: j  # noqa: E731
        custo = lambda: prov.spent_usd  # noqa: E731
    r = calibrar(itens, fabrica)
    r["juiz"], r["custo_usd"] = a.judge, round(custo(), 8)
    out = Path(a.out.format(judge=a.judge))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if not k.startswith("ids_")}, ensure_ascii=False))
    print("falsos aceites:", r["ids_falso_aceite"], "| falsos rejeitos:", r["ids_falso_rejeito"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
