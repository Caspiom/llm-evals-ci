import pytest

from llm_evals.scorers import run_check


@pytest.mark.parametrize(
    "output,check,esperado",
    [
        ("A capital é Brasília.", {"type": "contains", "value": "brasília"}, True),
        ("A capital é Rio.", {"type": "contains", "value": "Brasília"}, False),
        ("sem senha aqui", {"type": "not_contains", "value": "senha123"}, True),
        (" 42 ", {"type": "equals", "value": "42"}, True),
        ("CPF 123.456.789-00", {"type": "regex", "value": r"\d{3}\.\d{3}"}, True),
        ('{"nome": "Ana", "idade": 3}', {"type": "is_json", "keys": ["nome"]}, True),
        ('{"nome": "Ana"}', {"type": "is_json", "keys": ["idade"]}, False),
        ("isso não é json", {"type": "is_json"}, False),
        ("curto", {"type": "max_chars", "value": 10}, True),
        ("longo demais", {"type": "max_chars", "value": 5}, False),
    ],
)
def test_checks(output, check, esperado):
    assert run_check(output, check) is esperado


def test_tipo_desconhecido_falha_alto():
    with pytest.raises(ValueError):
        run_check("x", {"type": "inventado"})
