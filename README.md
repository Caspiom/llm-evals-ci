# llm-evals-ci

> **Pilar do portfólio — Quinta** · parte de uma série de 7 projetos de Engenharia de Software de IA (1h/dia).

## O problema
Detecta regressão de qualidade a cada commit via GitHub Actions. O diferencial que mostra mentalidade de produção.

## Por que está no portfólio
Suite de avaliação de LLM rodando em CI. Recrutadores de IA em 2026 valorizam este pilar — e o diferencial é a **execução com avaliação medida**, não só a demo.

## Stack
Python 3.11+ (núcleo só stdlib) · pytest · GitHub Actions

## Como funciona
1. **Casos** (`cases/*.jsonl`): prompt + checks determinísticos (`contains`, `not_contains`, `equals`, `regex`, `is_json`, `max_chars`).
2. **Provider** gera a resposta. Hoje: `fixture` (respostas gravadas — grátis e determinístico, valida o pipeline sem gastar API).
3. **Gate**: compara com `evals/baseline.json`. Falha o CI se um caso que passava passou a falhar, ou se a taxa cai abaixo de `--min-pass-rate`.

## Estrutura
- `src/llm_evals/` — `cases` (loader), `scorers` (checks), `providers`, `runner` (execução + gate), `cli`
- `cases/` — suites de avaliação
- `evals/baseline.json` — resultado de referência; `evals/fixtures/` — respostas gravadas
- `tests/` — testes unitários
- `.github/workflows/evals.yml` — CI com resumo em tabela no job

## Status
- [x] Esqueleto / setup roda em < 15 min
- [x] Núcleo funcional (happy path)
- [ ] Avaliação / métricas medidas
- [ ] README com números (eval, latência, custo)
- [ ] Deploy / demo reproduzível

## Como rodar
```bash
make setup && make test
.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/bom.json        # exit 0
.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/regressao.json  # exit 1: gate pega 2 regressões
```
Atualizar o baseline após uma melhoria intencional: adicione `--update-baseline`.

---
Autor: Gappy · Série montada com apoio do Hermes
