.PHONY: setup test demo all

setup:
	python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"

test:
	.venv/bin/pytest -q

# o gate tem que ABRIR com o bom e FECHAR (exit 1) com a regressão: se não fechar, o gate está quebrado
demo:
	.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/bom.json --min-pass-rate 0.8
	! .venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/regressao.json --out results/demo-regressao.json

all: test demo
