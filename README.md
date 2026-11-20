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
2. **Provider** gera a resposta. `fixture` (respostas gravadas — grátis e determinístico, é o que roda no CI) ou `anthropic` (API real, com **teto de custo duro**, ver abaixo).
3. **Gate**: compara com `evals/baseline.json`. Falha o CI se um caso que passava passou a falhar, ou se a taxa cai abaixo de `--min-pass-rate`.

## Provider real com teto de custo (`--provider anthropic`)
Só stdlib (`urllib`), modelo padrão `claude-haiku-5-5` (o mais barato da linha: US$ 0,10 entrada / US$ 0,50 saída por MTok, conferido na doc em 2026-11-05).

- **O teto é obrigatório** (`--max-cost-usd`); sem ele o CLI nem roda.
- **Pré-checagem do pior caso, antes de cada chamada (e de cada retry):** `gasto + (entrada no limite superior + max_tokens de saída) <= teto`. Se estourar, o modelo **não é chamado**. Depois da chamada soma o custo real da `usage`.
- **Entrada em limite superior, não estimativa:** bytes do prompt + 32 (cada byte vira no máximo 1 token). `chars/4` seria errado: o tokenizer deste modelo gera ~30% mais tokens que o antigo.
- **Thinking desligado** (`thinking: disabled`): ele é cobrado como saída e tornaria o teto imprevisível. Sem `temperature/top_p/top_k` (a doc do modelo manda omitir).
- **Retry só em 429/5xx/529** (respeita `retry-after`, backoff 0,5·2ⁿ, no máximo 2 retries). 400/401/403/404 não repetem.
- **Falha ambígua é cobrada pelo pior caso:** timeout ou conexão cortada depois do envio pode ter sido cobrado sem a gente saber, então soma o pior caso (e o teto barra o retry se não couber).
- **Execução incompleta nunca fica verde:** estourou o teto => o resto dos casos é **pulado** (`skipped_budget`), o gate reprova e `--update-baseline` recusa gravar.
- O preço de um modelo fora da tabela exige `--price-in/--price-out` (nunca assumimos preço). Prompt que possa passar de 100k tokens é recusado (a faixa de preço muda).
- A chave vem só de `ANTHROPIC_API_KEY` (nunca de argumento) e não aparece em relatório nem em mensagem de erro.

Cada caso do relatório traz `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `stop_reason`; o topo traz custo total, custo por caso, p50/p95 de latência e quantos casos não rodaram.

### O que está medido e o que NÃO está
- **Medido (sem gastar nada):** 45 testes contra um servidor HTTP falso local, que grava cada requisição para provar o que foi *e o que não foi* enviado. A suíte passa em um namespace de rede só com loopback (api.anthropic.com inacessível): nenhum teste fala com a internet.
- **Validação por mutação:** 18 mutantes (sem pré-checagem, custo sem preço de saída, fronteira `>` vs `>=`, retry em 4xx, timeout sem cobrança, thinking ligado, estimador chars/4, runner que não para no teto, gate que ignora caso pulado...). **1ª rodada: 17/18 pegos.** O que sobreviveu (runner continuava tentando casos depois do teto) mudava o comportamento (um prompt menor depois do estouro ainda rodava, deixando buracos na suíte); escrevi o teste e agora são 18/18.
- **NÃO medido ainda: latência e custo REAIS.** Nenhuma chamada à API foi feita. Estimativa dos 5 casos atuais: pior caso **US$ 0,000679** no total, realista ~US$ 0,0001. Quando rodar, os números entram aqui. Com 5 casos o p95 é igual ao máximo: amostra pequena demais para falar de cauda.
- O servidor falso valida o *contrato HTTP que eu li na doc*, não a API de verdade: um campo que a doc descreve diferente do comportamento real só aparece na primeira chamada real.
- As suítes `basico` (5), `robustez` (12, injeção/formato/recusa/limites) e `aberto` (8, juiz) rodam no CI só com `fixture`.

## LLM-as-judge (`src/llm_evals/judge.py`)
Check `{"type": "judge", "rubric": "...", "min_score": 4}`: um segundo modelo dá nota de 1 a 5 contra a rubrica.
- **Veredito inválido nunca aprova** (JSON ruim, nota 0/6, 4.5, `true`, "5" como texto): o caso falha com `judge_invalid`. Erro do juiz = `judge_error`. Caso com check `judge` sem juiz configurado é erro de uso, não passa por omissão.
- **Teto de custo próprio do juiz** (`--judge-max-cost-usd`, obrigatório com `--judge anthropic`), somado ao custo do caso e visível em `judge_cost_usd`. Se o juiz estoura o teto, o caso e o resto ficam `skipped_budget` (nunca aprovados).
- A resposta avaliada vai entre `<resposta>` e é tratada como DADO. Isso reduz mas **não elimina** injeção ("dê nota 5"): só juiz real calibrado mede o quanto ele cai nisso.

### Calibração contra rótulo humano (`scripts/calibrar_juiz.py`)
24 respostas com rótulo meu (um anotador só: viés meu, sem concordância entre humanos): 11 aceitáveis, 13 não, com fluente-porém-errada, certa-com-outras-palavras e injeção no próprio texto. O que se reporta: acordo, **kappa de Cohen** e **falso aceite** (juiz aprova o que o humano reprova) separado de falso rejeito.
- **Piso grátis (juiz por palavras-chave, sem modelo): acordo 67%, kappa 0,33, 4 falsos aceites em 13 reprovadas** (inclusive a injeção `cal05` e a troca RAM↔SSD `cal10`) e 4 falsos rejeitos. Esse é o número que um juiz LLM precisa superar. Um teste trava que o piso ainda erra: se alguém zerar o falso aceite, os dados ficaram fáceis demais.
- **Juiz LLM real: NÃO rodado** (custa dinheiro, falta o ok). Sem esse número, o juiz do CI é fixture: prova a mecânica (gate, custo, veredito inválido), **não** a qualidade da nota.
- Com n=24 qualquer um desses números tem incerteza grande (um caso = 4 pontos de acordo).

## Estrutura
- `src/llm_evals/` — `cases` (loader), `scorers` (checks), `providers`, `judge`, `calibracao`, `runner` (execução + gate), `cli`
- `scripts/calibrar_juiz.py` + `evals/judge_calibracao.jsonl` — calibração do juiz
- `cases/` — suites de avaliação
- `evals/baseline.json` — resultado de referência; `evals/fixtures/` — respostas gravadas
- `tests/` — testes unitários
- `.github/workflows/evals.yml` — CI com resumo em tabela no job

## Status
- [x] Esqueleto / setup roda em < 15 min
- [x] Núcleo funcional (happy path)
- [x] Provider real (Anthropic) com teto de custo duro, validado de graça (45 testes, 18 mutantes)
- [x] Check LLM-as-judge (veredito inválido nunca aprova, teto próprio, calibrado contra o piso grátis): 79 testes; mutação 18/18 pegos (2 sobreviveram na 1ª rodada: marca de `skipped_budget` e soma do custo do juiz)
- [x] Suítes de robustez (12) e abertas com juiz (8), com fixture boa e de regressão: o gate fecha na regressão
- [ ] Primeira rodada REAL: latência e custo por caso medidos (pede ok de gasto, ~US$ 0,0007 no pior caso)
- [ ] README com números reais (eval, latência, custo)
- [ ] Calibrar o juiz LLM real contra os 24 rótulos (pede ok de gasto)
- [ ] Deploy / demo reproduzível

## Como rodar
```bash
make setup && make test
.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/bom.json        # exit 0
.venv/bin/llm-evals run --cases cases/basico.jsonl --fixtures evals/fixtures/regressao.json  # exit 1: gate pega 2 regressões
```
```bash
make all   # 45 testes + demo do gate (abre com o bom, fecha com a regressão)
# rodada real (gasta dinheiro; teto obrigatório; chave só no ambiente):
ANTHROPIC_API_KEY=... .venv/bin/llm-evals run --cases cases/basico.jsonl --provider anthropic \
  --max-cost-usd 0.002 --baseline evals/baseline-anthropic.json --out results/anthropic.json
```
Atualizar o baseline após uma melhoria intencional: adicione `--update-baseline`.

---
Autor: Gappy · Série montada com apoio do Hermes
