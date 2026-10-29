import pytest

from llm_evals.cases import load_cases


def test_carrega_e_ignora_comentarios(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text('# comentário\n{"id": "a", "prompt": "oi", "checks": []}\n\n', encoding="utf-8")
    cases = load_cases(f)
    assert [c.id for c in cases] == ["a"]


def test_id_duplicado(tmp_path):
    f = tmp_path / "c.jsonl"
    linha = '{"id": "a", "prompt": "oi", "checks": []}\n'
    f.write_text(linha * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicado"):
        load_cases(f)


def test_campo_ausente(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text('{"id": "a", "checks": []}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="prompt"):
        load_cases(f)
