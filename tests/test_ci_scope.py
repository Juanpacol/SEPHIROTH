"""Which parts of the CI a change needs (AB#47).

The point of `scripts/ci_scope.py` is to skip work that cannot matter, so the tests that
matter most are the ones that say it never skips work that can: every path it does not
know turns everything on.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ci_scope  # noqa: E402
from ci_scope import Scope, scope_for  # noqa: E402

ALL = Scope(True, True, True)
NONE = Scope(False, False, False)


class TestWhatEachKindOfChangeNeeds:
    def test_a_frontend_only_change_needs_the_frontend_and_nothing_of_the_backend(self):
        scope = scope_for(["platform/frontend/app/page.tsx", "platform/frontend/lib/api.ts"])

        assert scope == Scope(frontend=True, backend=False, image=False)

    def test_a_docs_only_change_needs_nothing(self):
        assert (
            scope_for(["docs/04-development/setup.md", "README.md", "CONTRIBUTING.md", ".claude/skills/x.md"])
            == NONE
        )

    def test_the_frontends_own_markdown_is_docs_too(self):
        assert (
            scope_for(["platform/frontend/CLAUDE.md", "platform/frontend/public/landing/features/README.md"])
            == NONE
        )

    def test_a_backend_change_needs_the_backend_and_the_image_but_not_the_frontend(self):
        scope = scope_for(["src/sephiroth/runtime/registry.py", "platform/api/routers/medical.py"])

        assert scope == Scope(frontend=False, backend=True, image=True)

    def test_a_test_only_change_needs_the_backend_tests_but_not_the_image(self):
        assert scope_for(["tests/test_pdf_export.py"]) == Scope(frontend=False, backend=True, image=False)

    def test_a_script_change_needs_the_backend_tests_but_not_the_image(self):
        assert scope_for(["scripts/export_contracts.py"]) == Scope(frontend=False, backend=True, image=False)

    def test_the_dockerfile_needs_the_image(self):
        assert scope_for(["Dockerfile"]) == Scope(frontend=False, backend=False, image=True)

    def test_a_migration_or_a_dependency_change_needs_the_backend_and_the_image(self):
        assert scope_for(["migrations/versions/abc_add_table.py"]) == Scope(False, True, True)
        assert scope_for(["requirements.lock.txt"]) == Scope(False, True, True)
        assert scope_for(["pyproject.toml"]) == Scope(False, True, True)

    def test_a_mixed_change_needs_the_union(self):
        scope = scope_for(["platform/frontend/app/page.tsx", "tests/test_x.py", "docs/a.md"])

        assert scope == Scope(frontend=True, backend=True, image=False)


class TestWhenInDoubtRunEverything:
    @pytest.mark.parametrize(
        "path",
        [
            "something-new/at-the-root.txt",
            ".github/workflows/deploy.yml",
            ".github/workflows/extended-checks.yml",
            ".env.example",
            "LICENSE",
            "platform/somewhere_new/module.py",
        ],
    )
    def test_a_file_it_does_not_know_turns_everything_on(self, path):
        assert scope_for([path]) == ALL

    def test_one_unknown_file_among_known_ones_is_enough(self):
        assert scope_for(["docs/a.md", "platform/frontend/app/page.tsx", "mystery.bin"]) == ALL

    @pytest.mark.parametrize("path", [".github/workflows/ci.yml", "scripts/ci_scope.py"])
    def test_a_change_to_the_ci_itself_is_proved_by_all_of_it(self, path):
        assert scope_for([path, "docs/a.md"]) == ALL

    def test_no_files_needs_nothing_but_an_unreadable_diff_does(self):
        assert scope_for([]) == NONE
        assert scope_for(["", "  "]) == NONE


class TestTheCommandLine:
    def run(self, *args, env=None, cwd=None):
        return subprocess.run(
            [sys.executable, str(Path(ci_scope.__file__)), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
        )

    def test_all_turns_everything_on(self):
        out = self.run("--all")

        assert out.stdout.split() == ["frontend=true", "backend=true", "image=true"]

    def test_explicit_files(self):
        out = self.run("--files", "platform/frontend/app/page.tsx")

        assert out.stdout.split() == ["frontend=true", "backend=false", "image=false"]

    def test_it_writes_the_github_output_file_when_asked(self, tmp_path):
        target = tmp_path / "out"
        env = {"GITHUB_OUTPUT": str(target), "PATH": "/usr/bin:/bin"}

        self.run("--files", "docs/a.md", env=env)

        assert target.read_text().split() == ["frontend=false", "backend=false", "image=false"]

    def test_a_diff_it_cannot_make_runs_everything_instead_of_nothing(self, tmp_path):
        # No repository here, so `git diff` fails.
        out = self.run("--base", "origin/main", cwd=tmp_path)

        assert out.stdout.split() == ["frontend=true", "backend=true", "image=true"]
        assert "running everything" in out.stderr

    def test_it_reads_a_real_diff(self, tmp_path):
        def git(*a):
            subprocess.run(
                ["git", *a],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                env={
                    "GIT_AUTHOR_NAME": "t",
                    "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t",
                    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                },
            )

        git("init", "-q", "-b", "main")
        (tmp_path / "README.md").write_text("x")
        git("add", ".")
        git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "feature")
        (tmp_path / "platform" / "frontend").mkdir(parents=True)
        (tmp_path / "platform" / "frontend" / "a.tsx").write_text("y")
        git("add", ".")
        git("commit", "-q", "-m", "change")

        out = self.run("--base", "main", cwd=tmp_path)

        assert out.stdout.split() == ["frontend=true", "backend=false", "image=false"]
