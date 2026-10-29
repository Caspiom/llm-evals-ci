# PROGRESSO — llm-evals-ci

Último ponto onde parei (atualize ao fim de cada sessão de 1h):

- **Data:** 2026-10-29
- **Onde parei:** esqueleto pronto — loader JSONL, 6 scorers, provider `fixture`, gate de regressão vs baseline, CLI e workflow do GitHub Actions. 18 testes passando; demo de regressão (fixture `regressao.json`) derruba o gate com exit 1.
- **Próximo passo:** adicionar provider real (barato, com teto de custo) e medir latência/custo por caso; depois um check LLM-as-judge.
