"""Tests for the `intelligence.evaluation.run` CLI glue: the markdown
table printer, `--mode ci` end-to-end (against the real committed
baseline), and `--mode full` argument wiring (with a stubbed client)."""

from intelligence.evaluation import run as eval_run


def test_print_table_writes_github_step_summary(tmp_path, monkeypatch, capsys):
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    rows = [{"metric": "recall_at_1", "value": 0.8, "threshold": 0.75, "passed": True}]
    eval_run._print_table(rows)

    captured = capsys.readouterr()
    assert "recall_at_1" in captured.out
    assert "PASS" in summary_path.read_text()


def test_print_table_handles_missing_value(capsys):
    rows = [{"metric": "faithfulness_llm_judge", "value": None, "threshold": 0.25, "passed": False}]
    eval_run._print_table(rows)
    assert "n/a" in capsys.readouterr().out


def test_run_ci_against_committed_baseline_passes():
    # Exercises the real, committed golden.json / transcripts / results /
    # thresholds — this is the same check CI runs on every PR.
    assert eval_run._run_ci() == 0


def test_main_dispatches_to_ci_mode(monkeypatch):
    monkeypatch.setattr(eval_run.sys, "argv", ["run.py", "--mode", "ci"])
    assert eval_run.main() == 0


def test_run_full_uses_model_override(monkeypatch, tmp_path):
    from tests.conftest import FakeOllamaClient

    captured = {}

    def fake_ollama_client_ctor(host, model):
        captured["host"] = host
        captured["model"] = model
        return FakeOllamaClient(default_script=[("answer", "ok")])

    monkeypatch.setattr("intelligence.llm.ollama_client.OllamaClient", fake_ollama_client_ctor)

    async def fake_run_full_mode(client, **kwargs):
        return {
            "run": {"model": getattr(client, "model", "fake-model")},
            "retrieval": {},
            "citation": {},
            "faithfulness": {},
        }

    monkeypatch.setattr(eval_run.runner, "run_full_mode", fake_run_full_mode)

    exit_code = eval_run._run_full(record=False, skip_pubmed=True, model="custom-model:latest")
    assert exit_code == 0
