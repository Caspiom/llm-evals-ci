import json
import urllib.error

import pytest
from fake_anthropic import FakeAnthropic, err, ok

from llm_evals.cases import Case
from llm_evals.cli import main as cli_main
from llm_evals.providers import AnthropicProvider, BudgetExceeded, ProviderError
from llm_evals.runner import run

KEY = "sk-ant-TESTE-nao-vazar"
PIN, POUT = 0.10, 0.50  # US$/MTok do haiku-5-5


def prov(srv, **kw):
    kw.setdefault("max_cost_usd", 1.0)
    return AnthropicProvider(api_key=KEY, base_url=srv.url, sleep=lambda s: None, **kw)


def test_resposta_usage_e_custo_exato():
    with FakeAnthropic(ok("Brasília", in_tok=1000, out_tok=200)) as srv:
        p = prov(srv)
        assert p.complete("c", "oi") == "Brasília"
    assert p.last_usage.input_tokens == 1000 and p.last_usage.output_tokens == 200
    esperado = (1000 * PIN + 200 * POUT) / 1_000_000  # 0.0002
    assert p.last_usage.cost_usd == pytest.approx(esperado) and p.spent_usd == pytest.approx(esperado)
    assert p.last_usage.stop_reason == "end_turn"


def test_formato_da_requisicao():
    with FakeAnthropic() as srv:
        prov(srv, max_tokens=77).complete("c", "pergunta")
    (r,) = srv.requests
    assert r["path"] == "/v1/messages"
    assert r["headers"]["x-api-key"] == KEY and r["headers"]["anthropic-version"] == "2023-06-01"
    b = r["body"]
    assert b["model"] == "claude-haiku-5-5" and b["max_tokens"] == 77
    assert b["thinking"] == {"type": "disabled"}  # thinking vira saída cobrada: tem que estar desligado
    assert b["messages"] == [{"role": "user", "content": "pergunta"}]
    assert not {"temperature", "top_p", "top_k"} & b.keys()  # a doc do modelo manda omitir


def test_so_blocos_de_texto_entram_na_resposta():
    blocos = [{"type": "thinking", "thinking": "SEGREDO-DE-RACIOCINIO"}, {"type": "text", "text": "A"},
              {"type": "text", "text": "B"}]
    with FakeAnthropic(ok(content=blocos)) as srv:
        assert prov(srv).complete("c", "x") == "AB"


def test_teto_menor_que_o_pior_caso_nao_chama_o_modelo():
    with FakeAnthropic() as srv:
        p = prov(srv, max_tokens=256)
        pior = p.worst_case_usd("oi")
        p.max_cost_usd = pior * 0.99
        with pytest.raises(BudgetExceeded):
            p.complete("c", "oi")
    assert srv.requests == [] and p.spent_usd == 0.0


def test_pior_caso_tem_valor_absoluto_calculado_a_mao():
    with FakeAnthropic() as srv:
        # (2 bytes + 32 de folga) * 0,10 + 256 * 0,50 = 131,4 US$/1e6 (não usa código sob teste)
        assert prov(srv, max_tokens=256).worst_case_usd("oi") == pytest.approx(131.4e-6)


def test_pior_caso_cobre_tokenizer_que_gera_1_token_por_byte():
    prompt = "ação 😀 " * 10  # bytes > caracteres: chars/4 subestimaria feio
    pior_entrada = len(prompt.encode("utf-8"))
    with FakeAnthropic(ok(in_tok=pior_entrada, out_tok=256)) as srv:
        p = prov(srv, max_tokens=256)
        p.complete("c", prompt)
        assert p.last_usage.cost_usd <= p.worst_case_usd(prompt)


def test_teto_igual_ao_pior_caso_ainda_chama():
    with FakeAnthropic(ok(in_tok=1, out_tok=1)) as srv:
        p = prov(srv, max_tokens=256)
        p.max_cost_usd = p.worst_case_usd("oi")  # fronteira: gasto + pior == teto => permitido
        assert p.complete("c", "oi") == "42"
    assert len(srv.requests) == 1


def test_gasto_nunca_passa_do_teto_mesmo_no_pior_caso():
    # servidor gasta o máximo possível por chamada (saída = max_tokens)
    with FakeAnthropic(ok(in_tok=34, out_tok=256)) as srv:
        p = prov(srv, max_tokens=256)
        por_chamada = p.worst_case_usd("oi")
        p.max_cost_usd = por_chamada * 2.5
        feitas = 0
        for _ in range(5):
            try:
                p.complete("c", "oi")
                feitas += 1
            except BudgetExceeded:
                break
            assert p.spent_usd <= p.max_cost_usd
    assert feitas == 2 and len(srv.requests) == 2


def test_retry_429_respeita_retry_after_e_depois_funciona():
    esperas = []
    with FakeAnthropic(err(429, {"retry-after": "3"}), err(529), ok("ok")) as srv:
        p = AnthropicProvider(api_key=KEY, base_url=srv.url, max_cost_usd=1.0, sleep=esperas.append)
        assert p.complete("c", "x") == "ok"
    assert len(srv.requests) == 3
    assert esperas == [3.0, 1.0]  # retry-after do 1º; backoff exponencial (0.5*2^1) no 2º


def test_retries_esgotados_limitam_as_tentativas():
    with FakeAnthropic(err(503)) as srv:
        p = prov(srv, retries=2)
        with pytest.raises(ProviderError):
            p.complete("c", "x")
    assert len(srv.requests) == 3 and p.spent_usd == 0.0  # erro HTTP não é cobrado


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_erro_de_cliente_nao_tenta_de_novo(status):
    with FakeAnthropic(err(status)) as srv:
        with pytest.raises(ProviderError):
            prov(srv).complete("c", "x")
    assert len(srv.requests) == 1


def test_timeout_cobra_o_pior_caso_e_o_teto_barra_o_retry():
    with FakeAnthropic({**ok(), "delay": 0.6}) as srv:
        p = AnthropicProvider(api_key=KEY, base_url=srv.url, timeout=0.15, max_cost_usd=1.0, sleep=lambda s: None)
        pior = p.worst_case_usd("x")
        p.max_cost_usd = pior * 1.5  # cabe UMA tentativa; depois do timeout (cobrado) o retry não cabe
        with pytest.raises(BudgetExceeded):
            p.complete("c", "x")
    assert p.spent_usd == pytest.approx(pior) and len(srv.requests) == 1


def test_resposta_malformada_cobra_o_pior_caso():
    with FakeAnthropic({"status": 200, "body": b"nao-e-json"}) as srv:
        p = prov(srv)
        with pytest.raises(ProviderError):
            p.complete("c", "x")
    assert p.spent_usd == pytest.approx(p.worst_case_usd("x"))


def test_sem_chave_nao_constroi(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        AnthropicProvider(max_cost_usd=1.0)


def test_preco_desconhecido_exige_informar():
    with pytest.raises(ValueError):
        AnthropicProvider("outro-modelo", max_cost_usd=1.0, api_key=KEY)
    p = AnthropicProvider("outro-modelo", max_cost_usd=1.0, api_key=KEY, price_in=1.0, price_out=2.0)
    assert (p.price_in, p.price_out) == (1.0, 2.0)


def test_teto_obrigatorio_e_positivo():
    with pytest.raises(ValueError):
        AnthropicProvider(max_cost_usd=0, api_key=KEY)


def test_prompt_gigante_recusado_porque_o_preco_muda():
    with FakeAnthropic() as srv:
        with pytest.raises(ProviderError):
            prov(srv).complete("c", "x" * 100_001)
    assert srv.requests == []


CASOS = [Case(f"c{i}", "p", [{"type": "contains", "value": "ok"}]) for i in range(5)]


def test_runner_pula_o_resto_quando_o_teto_acaba_e_o_gate_reprova(tmp_path):
    from llm_evals.runner import compare

    with FakeAnthropic(ok("ok", in_tok=34, out_tok=256)) as srv:
        p = prov(srv, max_tokens=256)
        p.max_cost_usd = p.worst_case_usd("p") * 2.5
        rep = run(CASOS, p)
    assert [r.status for r in rep.results] == ["ok", "ok", "skipped_budget", "skipped_budget", "skipped_budget"]
    assert len(srv.requests) == 2 and rep.cost_usd <= p.max_cost_usd
    assert rep.pass_rate == 0.4 and rep.to_dict()["not_run"] == 3
    problems = compare(rep, tmp_path / "nao-existe.json")
    assert problems and "skipped_budget" in problems[0]


def test_estourou_o_teto_o_resto_e_pulado_mesmo_que_um_prompt_menor_coubesse():
    casos = [Case("c0", "p", []), Case("c1", "p", []), Case("caro", "x" * 3000, []), Case("barato", "p", [])]
    with FakeAnthropic(ok("ok", in_tok=34, out_tok=1)) as srv:
        p = prov(srv, max_tokens=256)
        p.max_cost_usd = 200e-6  # "p" (131 us$ no pior caso) cabe; "x"*3000 (431 us$) não; depois "p" caberia de novo
        rep = run(casos, p)
    assert [r.status for r in rep.results] == ["ok", "ok", "skipped_budget", "skipped_budget"]
    assert len(srv.requests) == 2  # execução = prefixo contíguo; sem buracos no meio da suíte


def test_relatorio_tem_custo_tokens_e_latencia():
    with FakeAnthropic(ok("ok", in_tok=100, out_tok=10)) as srv:
        d = run(CASOS, prov(srv)).to_dict()
    assert d["total"] == 5 and d["passed"] == 5 and d["not_run"] == 0
    assert d["input_tokens"] == 500 and d["output_tokens"] == 50
    assert d["cost_usd"] == pytest.approx(5 * (100 * PIN + 10 * POUT) / 1e6)
    assert d["cost_per_case_usd"] == pytest.approx(d["cost_usd"] / 5)
    assert 0 < d["latency_ms_p50"] <= d["latency_ms_p95"]
    assert KEY not in json.dumps(d)


def test_erro_do_provider_nao_derruba_a_suite_e_reprova_o_caso():
    with FakeAnthropic(err(401)) as srv:
        rep = run(CASOS[:2], prov(srv))
    assert [r.status for r in rep.results] == ["error", "error"] and rep.pass_rate == 0.0
    assert KEY not in json.dumps(rep.to_dict())


def _cli(tmp_path, srv, *extra, monkeypatch=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", srv.url)
    cases = tmp_path / "c.jsonl"
    cases.write_text("\n".join(json.dumps({"id": c.id, "prompt": c.prompt, "checks": c.checks}) for c in CASOS))
    return cli_main(["run", "--cases", str(cases), "--provider", "anthropic", "--out", str(tmp_path / "r.json"),
                     "--baseline", str(tmp_path / "b.json"), *extra])


def test_cli_recusa_anthropic_sem_teto(tmp_path, monkeypatch):
    with FakeAnthropic() as srv, pytest.raises(SystemExit) as e:
        _cli(tmp_path, srv, monkeypatch=monkeypatch)
    assert e.value.code == 2 and srv.requests == []


def test_cli_roda_com_teto_e_grava_relatorio(tmp_path, monkeypatch, capsys):
    with FakeAnthropic(ok("ok", in_tok=20, out_tok=3)) as srv:
        assert _cli(tmp_path, srv, "--max-cost-usd", "0.01", monkeypatch=monkeypatch) == 0
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["provider"] == "anthropic:claude-haiku-5-5" and rep["max_cost_usd"] == 0.01 and rep["cost_usd"] > 0
    assert "custo: US$" in capsys.readouterr().out


def test_cli_nao_atualiza_baseline_com_execucao_incompleta(tmp_path, monkeypatch):
    with FakeAnthropic(ok("ok")) as srv:
        # teto minúsculo: nenhum caso cabe => tudo pulado
        rc = _cli(tmp_path, srv, "--max-cost-usd", "0.0000001", "--update-baseline", monkeypatch=monkeypatch)
    assert rc == 1 and not (tmp_path / "b.json").exists() and srv.requests == []
