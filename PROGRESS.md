# PROGRESSO — llm-evals-ci

Último ponto onde parei (atualize ao fim de cada sessão de 1h):

- **Data:** 2026-11-05 (bloco de QUINTA, feito pelo Hermes a pedido do Lucas)
- **Onde parei:** provider `anthropic` pronto (só stdlib, `claude-haiku-5-5`) com **teto de custo duro**: pré-checa o pior caso (entrada em limite superior + `max_tokens`) antes de cada chamada/retry, cobra o pior caso em falha ambígua (timeout), retry só em 429/5xx, thinking desligado, execução incompleta reprova o gate e não grava baseline. Relatório com tokens, custo e latência por caso (+ custo total, p50/p95). 45 testes contra servidor HTTP falso (também passam sem internet); 18 mutantes, **1ª rodada 17/18** (o que sobreviveu virou teste). CI continua com `fixture` (grátis).
- **O que NÃO foi feito:** nenhuma chamada real à API (o ok de gasto não veio). Logo, **sem latência/custo reais** ainda. Pior caso estimado para os 5 casos: US$ 0,000679.
- **Próximo passo:** (1) rodar os 5 casos de verdade com `--max-cost-usd 0.002` (precisa do ok do Lucas), gravar `evals/baseline-anthropic.json` e colocar latência/custo no README; (2) mais casos (5 é pouco para p95 e para o baseline); (3) check LLM-as-judge.
- **CI:** o workflow do GitHub Actions rodou de verdade pela 1ª vez no commit `06b2236` e passou (testes, gate e artefato do relatório). O `gh` já tem o escopo `workflow`.
