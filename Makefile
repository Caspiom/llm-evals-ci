.PHONY: setup test demo all

setup:
	python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"

test:
	.venv/bin/pytest -q

# o gate tem que ABRIR com o bom e FECHAR (exit 1) com a regressão: se não fechar, o gate está quebrado
demo:
	.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/bom.json --min-pass-rate 0.8
	! .venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/regressao.json --out results/demo-regressao.json

	.venv/bin/llm-evals run --cases cases/robustez.jsonl --fixtures evals/fixtures/robustez-bom.json --baseline evals/baseline-robustez.json --out results/robustez.json
	! .venv/bin/llm-evals run --cases cases/robustez.jsonl --fixtures evals/fixtures/robustez-regressao.json --baseline evals/baseline-robustez.json --out results/robustez-regr.json
	.venv/bin/llm-evals run --cases cases/aberto.jsonl --fixtures evals/fixtures/aberto-bom.json --judge fixture --judge-fixtures evals/fixtures/aberto-juiz-bom.json --baseline evals/baseline-aberto.json --out results/aberto.json
	! .venv/bin/llm-evals run --cases cases/aberto.jsonl --fixtures evals/fixtures/aberto-regressao.json --judge fixture --judge-fixtures evals/fixtures/aberto-juiz-regressao.json --baseline evals/baseline-aberto.json --out results/aberto-regr.json
	.venv/bin/python scripts/calibrar_juiz.py --judge keyword

all: test demo
