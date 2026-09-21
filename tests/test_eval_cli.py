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


def _async_returning(value):
    """`_run_ci` now does `asyncio.run(runner.run_ci_mode())` — a plain
    `lambda: value` monkeypatch would hand `asyncio.run` a dict, not an
    awaitable. Wrap the stubbed result in a coroutine function instead."""

    async def _stub(*args, **kwargs):
        return value

    return _stub


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


def test_print_table_renders_ungated_metric_as_skipped(capsys):
    """SKIPPED, never PASS. A metric the run could not measure must not read as
    one that cleared its threshold — that would make the table actively
    misleading, which is worse than omitting the row."""
    rows = [
        {"metric": "recall_at_1", "value": 0.9, "threshold": 0.87, "passed": True, "gated": True},
        {
            "metric": "faithfulness_llm_judge",
            "value": None,
            "threshold": 0.25,
            "passed": True,
            "gated": False,
        },
    ]
    eval_run._print_table(rows)

    out = capsys.readouterr().out
    assert "| faithfulness_llm_judge | n/a | 0.2500 | SKIPPED |" in out
    assert "| recall_at_1 | 0.9000 | 0.8700 | PASS |" in out


def _ci_result(**overrides):
    base = {
        "passed": True,
        "n_cases": 101,
        "stale_results": False,
        "dataset_stale": False,
        "transcripts_stale": False,
        "ungated_metrics": [],
        "embeddings_artifact_stale": False,
        "embeddings_artifact_warning": None,
        "threshold_rows": [],
    }
    return {**base, **overrides}


def test_run_ci_warns_loudly_when_transcripts_are_stale(monkeypatch, capsys):
    """Transcript drift means the replayed metrics describe answers that no
    longer exist, so nothing in the run is trustworthy: hard failure."""
    monkeypatch.setattr(
        eval_run.runner, "run_ci_mode", _async_returning(_ci_result(passed=False, transcripts_stale=True))
    )
    exit_code = eval_run._run_ci()

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "transcripts/" in err


def test_run_ci_passes_with_a_stale_dataset_but_names_what_it_stopped_gating(monkeypatch, capsys):
    """Dataset drift leaves the transcripts valid, so the live metrics still
    gate and the run can pass — but the warning has to say which metrics went
    ungated, or a green run quietly means less than it did yesterday."""
    monkeypatch.setattr(
        eval_run.runner,
        "run_ci_mode",
        _async_returning(_ci_result(dataset_stale=True, ungated_metrics=["faithfulness_llm_judge"])),
    )
    exit_code = eval_run._run_ci()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "faithfulness_llm_judge" in captured.err
    assert "NOT" in captured.err
    assert "Overall: PASS" in captured.out


def test_run_ci_surfaces_a_stale_embeddings_artifact(monkeypatch, capsys):
    monkeypatch.setattr(
        eval_run.runner,
        "run_ci_mode",
        _async_returning(
            _ci_result(
                passed=False,
                embeddings_artifact_stale=True,
                embeddings_artifact_warning="corpus hash changed",
            )
        ),
    )
    exit_code = eval_run._run_ci()

    assert exit_code == 1
    assert "corpus hash changed" in capsys.readouterr().err


def test_main_dispatches_ci_mode(monkeypatch):
    """`main` is the only thing that turns argv into a mode, and a wiring
    mistake there would silently run the wrong evaluation."""
    monkeypatch.setattr("sys.argv", ["run", "--mode", "ci"])
    monkeypatch.setattr(eval_run, "_run_ci", lambda: 0)
    assert eval_run.main() == 0


def test_main_passes_full_mode_flags_through(monkeypatch):
    captured = {}

    def fake_full(record, skip_pubmed, provider, model):
        captured.update(record=record, skip_pubmed=skip_pubmed, provider=provider, model=model)
        return 0

    monkeypatch.setattr(
        "sys.argv",
        ["run", "--mode", "full", "--record", "--skip-pubmed", "--provider", "ollama", "--model", "m"],
    )
    monkeypatch.setattr(eval_run, "_run_full", fake_full)

    assert eval_run.main() == 0
    assert captured == {"record": True, "skip_pubmed": True, "provider": "ollama", "model": "m"}


def test_git_sha_degrades_to_unknown_outside_a_repo(monkeypatch):
    """Recorded in every baseline, so it must never raise — a missing git is a
    label problem, not a reason to lose the run."""

    def boom(*_args, **_kwargs):
        raise OSError("no git here")

    monkeypatch.setattr(eval_run.subprocess, "check_output", boom)
    assert eval_run._git_sha() == "unknown"


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
