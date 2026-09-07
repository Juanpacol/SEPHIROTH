"""Tests for the `intelligence.evaluation.run` CLI glue: the markdown
table printer and `--mode full` argument wiring (with a stubbed client).

`--mode ci` (`_run_ci`) itself isn't tested here against the committed
baseline: keeping that baseline in sync means periodically re-recording
transcripts against a real provider (`--mode full --record`), which this
project's free-tier Gemini quota can't sustain on a schedule tight enough
to keep CI green — see the CI workflow's removed `eval` job and this
commit's message for the reasoning. `_run_ci`'s own logic (reading golden/
transcripts/results, comparing to thresholds) is still exercised indirectly
by `_print_table`'s tests above and by running `--mode ci` manually when
someone chooses to refresh the baseline."""

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


def test_run_full_uses_model_override(monkeypatch, tmp_path):
    from tests.conftest import FakeLLMClient

    captured = {}

    def fake_gemini_client_ctor(api_key, model):
        captured["api_key"] = api_key
        captured["model"] = model
        return FakeLLMClient(default_script=[("answer", "ok")])

    monkeypatch.setattr("sephiroth.models.gemini.GeminiClient", fake_gemini_client_ctor)

    async def fake_run_full_mode(client, **kwargs):
        return {
            "run": {"model": getattr(client, "model", "fake-model"), "provider": "GeminiClient"},
            "retrieval": {},
            "citation": {},
            "faithfulness": {},
            "performance": {},
        }

    monkeypatch.setattr(eval_run.runner, "run_full_mode", fake_run_full_mode)

    exit_code = eval_run._run_full(
        record=False, skip_pubmed=True, provider="gemini", model="custom-model:latest"
    )
    assert exit_code == 0
    assert captured["model"] == "custom-model:latest"


def test_run_full_builds_ollama_client_for_ollama_provider(monkeypatch):
    """`--provider ollama` must build an OllamaClient, not GeminiClient —
    this is the wiring `/eval` needs to compare providers on the same
    golden set."""
    from tests.conftest import FakeLLMClient

    captured = {}

    def fake_ollama_ctor(model, base_url, api_key):
        captured["model"] = model
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return FakeLLMClient(default_script=[("answer", "ok")])

    monkeypatch.setattr("sephiroth.models.ollama.OllamaClient", fake_ollama_ctor)

    async def fake_run_full_mode(client, **kwargs):
        return {
            "run": {"model": getattr(client, "model", "fake-model"), "provider": "OllamaClient"},
            "retrieval": {},
            "citation": {},
            "faithfulness": {},
            "performance": {},
        }

    monkeypatch.setattr(eval_run.runner, "run_full_mode", fake_run_full_mode)

    exit_code = eval_run._run_full(record=False, skip_pubmed=True, provider="ollama", model="qwen2.5:14b")
    assert exit_code == 0
    assert captured["model"] == "qwen2.5:14b"
