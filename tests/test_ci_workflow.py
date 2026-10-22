"""The CI keeps the shape AB#47 gave it.

Branch protection lists three required checks by name, so renaming a job would leave a
check no PR can satisfy. And the speed-up depends on every expensive step being gated by
`scripts/ci_scope.py` while the cheap safety steps (secret scan, lint, commit format) never
are. These tests read the workflow and fail if either stops being true.
"""

from pathlib import Path

import pytest
import yaml  # a dependency of requirements.txt: if it is ever missing, fail, do not skip

WORKFLOW = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text()
)
JOBS = WORKFLOW["jobs"]

# What branch protection requires (see the note at the top of ci.yml).
REQUIRED = {"quality", "test", "deploy-smoke"}

# Each job's scope output, and the steps that must wait for it. Anything not listed here runs
# every time: it is cheap and it is what keeps a skipped job honest.
GATED = {
    "quality": ("frontend", ["setup-node", "frontend lint + unit tests + build"]),
    "test": (
        "backend",
        [
            "setup-python",
            "pip install -r",
            "pip install -e",
            "Migrate + seed",
            "Run tests",
            "Contract schema",
            "upload-artifact",
        ],
    ),
    "deploy-smoke": (
        "image",
        ["Build image", "Boot (development)", "Boot (production", "Assert bad config", "Trivy"],
    ),
}
ALWAYS = {"quality": ["gitleaks", "ruff", "bandit", "Validate commit messages", "No merge commits"]}


def steps(job):
    return JOBS[job]["steps"]


def label(step):
    return str(step.get("name") or step.get("uses") or step.get("run") or "")


def find(job, fragment):
    return [s for s in steps(job) if fragment in label(s)]


def test_the_three_required_checks_keep_their_names():
    assert set(JOBS) == REQUIRED


@pytest.mark.parametrize("job", sorted(REQUIRED))
def test_every_job_has_a_time_limit_so_a_hung_step_cannot_hold_a_pr(job):
    limit = JOBS[job].get("timeout-minutes")
    assert limit is not None and limit <= 25


def test_a_newer_push_cancels_the_pr_run_but_never_a_run_on_main():
    concurrency = WORKFLOW["concurrency"]
    assert "github.ref" in concurrency["group"]
    assert "pull_request" in str(concurrency["cancel-in-progress"])
    assert "push" not in str(concurrency["cancel-in-progress"])


@pytest.mark.parametrize("job", sorted(REQUIRED))
def test_every_job_asks_the_scope_script_first(job):
    scope = [s for s in steps(job) if s.get("id") == "scope"]
    assert len(scope) == 1
    assert "scripts/ci_scope.py" in scope[0]["run"]
    assert "--all" in scope[0]["run"], "a push to main must run everything"
    # Needs history to diff against.
    checkout = next(s for s in steps(job) if "actions/checkout" in s.get("uses", ""))
    assert checkout["with"]["fetch-depth"] == 0
    assert steps(job).index(scope[0]) == steps(job).index(checkout) + 1


@pytest.mark.parametrize("job", sorted(GATED))
def test_the_expensive_steps_wait_for_their_scope(job):
    output, fragments = GATED[job]
    for fragment in fragments:
        found = find(job, fragment)
        assert found, f"{job}: no step matches {fragment!r}"
        for step in found:
            assert f"steps.scope.outputs.{output} == 'true'" in step.get("if", ""), f"{job}: {label(step)}"


def test_the_cheap_safety_steps_never_wait():
    for job, fragments in ALWAYS.items():
        for fragment in fragments:
            found = find(job, fragment)
            assert found, f"{job}: no step matches {fragment!r}"
            for step in found:
                condition = step.get("if", "")
                assert "scope" not in condition, f"{job}: {label(step)} must always run"


@pytest.mark.parametrize("job", sorted(GATED))
def test_a_skipped_job_says_so_in_its_log(job):
    output, _ = GATED[job]
    notes = [s for s in steps(job) if s.get("if") == f"steps.scope.outputs.{output} != 'true'"]
    assert len(notes) == 1
    assert "skipped" in notes[0]["run"]
