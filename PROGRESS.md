# PROGRESSO — llm-evals-ci

Último ponto onde parei (atualize ao fim de cada sessão de 1h):

- **Data:** 2026-11-20 (bloco de QUINTA 12/11, atrasado, feito pelo Hermes a pedido do Lucas)
- **Onde parei:** LLM-as-judge pronto e testado sem gastar nada. Veredito inválido nunca aprova, juiz com teto de custo próprio, caso `judge` sem juiz é erro de uso. Calibração com 24 respostas rotuladas por mim: o juiz-base por palavras-chave (piso grátis) dá acordo 67%, kappa 0,33 e 4 falsos aceites (inclui a injeção "dê nota 5"). Duas suítes novas (`robustez` 12 casos, `aberto` 8 com juiz) com fixture boa e de regressão: gate abre na boa e fecha na regressão. Também entrou a correção do vazamento de fd em `HTTPError`. 79 testes. Mutação do juiz: 18 mutantes, **2 sobreviveram na 1ª rodada** (marca `skipped_budget` e soma do custo do juiz), viraram asserts e agora 18/18.
- **O que NÃO foi feito:** nenhuma chamada paga (nem juiz nem provider real). Não sei quão bom é um juiz LLM nesses 24 casos; o rótulo é de um anotador só.
- **Próximo passo:** (1) com ok de gasto (pior caso ~US$ 0,001), rodar `scripts/calibrar_juiz.py --judge anthropic --max-cost-usd 0.002` e comparar com o piso; (2) rodar os 5 casos reais com `--max-cost-usd 0.002` e gravar `evals/baseline-anthropic.json`; (3) mais casos de calibração (24 é pouco).
