import json

from llm_evals.cases import Case
from llm_evals.runner import compare, run


class Fake:
    name = "fake"

    def __init__(self, answers):
        self.answers = answers

    def complete(self, case_id, prompt):
        return self.answers[case_id]


CASES = [
    Case("a", "p", [{"type": "contains", "value": "ok"}]),
    Case("b", "p", [{"type": "equals", "value": "1"}]),
]


def test_pass_rate():
    rep = run(CASES, Fake({"a": "ok", "b": "2"}))
    assert rep.pass_rate == 0.5
    assert rep.results[1].failed_checks == ["equals"]


def test_gate_detecta_regressao(tmp_path):
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps(run(CASES, Fake({"a": "ok", "b": "1"})).to_dict()))
    piorou = run(CASES, Fake({"a": "ok", "b": "2"}))
    problems = compare(piorou, base)
    assert len(problems) == 1 and "b" in problems[0]


def test_gate_sem_baseline_usa_minimo(tmp_path):
    rep = run(CASES, Fake({"a": "ok", "b": "2"}))
    assert compare(rep, tmp_path / "nao-existe.json", min_pass_rate=0.4) == []
    assert compare(rep, tmp_path / "nao-existe.json", min_pass_rate=0.9) != []
