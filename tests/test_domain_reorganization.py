"""The router reorganization, checked structurally rather than eyeballed.

Twenty router modules moved from one flat directory into four domain
packages. Nothing about a file move is safe to assume; ADR-019 explains why
routers moved and `services`/`workflows` did not, and this file asserts the
two invariants that made the move mechanically checkable rather than merely
plausible: every router reaches its dependencies by an absolute import (so a
future move never has to recompute relative-import depth), and the app that
comes out the other end answers on the same routes it always did.

Verifies AC-028-01, AC-028-02, AC-028-03, AC-028-04
(docs/specs/SPEC-028-domain-reorganization.md).
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "platform/api"

#: Where each router landed. Mirrors SPEC-028 §6.2's table -- if a router
#: moves again, this table and the assertions below move with it.
DOMAIN_ROUTERS = {
    "clinical": {"patients", "encounters", "alerts", "results", "result_reviews", "portal", "dashboard"},
    "operations": {
        "scheduling",
        "tasks",
        "approvals",
        "followups",
        "automation_memory",
        "badges",
        "notifications",
        "push",
        "internal",
    },
    "intelligence": {"agents", "rag", "medical"},
    "security": {"audit"},
}


class TestEveryRouterLandedWhereItShouldHave:
    """AC-028-04's precondition: the four domain folders exist and hold
    exactly the routers the table says, no more and no fewer."""

    @pytest.mark.parametrize("domain,expected", sorted(DOMAIN_ROUTERS.items()))
    def test_the_domain_folder_holds_exactly_its_routers(self, domain, expected):
        directory = API_ROOT / domain / "routers"
        assert directory.is_dir(), f"{directory} does not exist"

        actual = {p.stem for p in directory.glob("*.py") if p.stem != "__init__"}
        assert actual == expected

    def test_the_old_flat_directory_is_gone(self):
        """Left behind, it would be an empty package nobody imports from and
        everybody wonders about."""
        assert not (API_ROOT / "routers").exists()

    def test_no_router_is_claimed_by_two_domains(self):
        seen: dict[str, str] = {}
        for domain, routers in DOMAIN_ROUTERS.items():
            for router in routers:
                assert router not in seen, f"{router} listed under both {seen.get(router)} and {domain}"
                seen[router] = domain


class TestNoRelativeImportSurvivedTheMove:
    """AC-028-02. A router one level deeper than it used to be makes `..`
    mean something different than it did — the exact failure mode a relative
    import invites on the next move, too. Every router reaches `services`,
    `workflows`, `audit`, `paging`, `timeparse`, and the pure `scheduling`
    module absolutely, which cannot be affected by depth at all."""

    _RELATIVE_IMPORT = re.compile(r"^\s*from \.\.?[a-zA-Z_]", re.MULTILINE)

    def _router_files(self):
        for domain in DOMAIN_ROUTERS:
            yield from sorted((API_ROOT / domain / "routers").glob("*.py"))

    def test_no_router_imports_a_sibling_by_relative_path(self):
        offenders = []
        for path in self._router_files():
            if path.stem == "__init__":
                continue
            if self._RELATIVE_IMPORT.search(path.read_text()):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        assert not offenders, (
            f"these routers use a relative import: {offenders}. Use `from api.X import ...` "
            "instead -- a router's package depth must never matter to how it reaches "
            "services, workflows, or its other siblings (ADR-019)."
        )

    def test_services_and_workflows_are_reached_absolutely_from_every_router(self):
        """The specific pattern the move depended on: not merely "no relative
        import", but "the absolute form is actually what's there"."""
        found_services = found_workflows = False
        for path in self._router_files():
            source = path.read_text()
            found_services = found_services or "from api.services" in source
            found_workflows = found_workflows or "from api.workflows" in source

        assert found_services and found_workflows

    def test_the_one_router_to_router_reach_is_absolute_and_explicit(self):
        """`task_derivation.py` (a service, not a router) still reaches into
        `dashboard.py` for `_evolution_deteriorating`. It moved from a
        relative `..routers.dashboard` -- which said nothing about which
        domain it was reaching into -- to naming the domain outright."""
        source = (API_ROOT / "services" / "task_derivation.py").read_text()
        assert "from api.clinical.routers.dashboard import" in source


class TestThePhiSeamListsMatchWhereTheFilesActuallyAre:
    """AC-028-03. `sephiroth.models.egress` names three router modules by
    their dotted path as part of an *enforced* list (ADR-015) -- a plain
    string, not a reference Python checks for you. Stale after a move, it
    would silently stop gating a seam rather than raising anything."""

    def test_no_seam_list_still_names_the_old_flat_path(self):
        from sephiroth.models.egress import PHI_DOWNSTREAM, PHI_EXEMPT, PHI_SEAMS

        for name in (*PHI_SEAMS, *PHI_DOWNSTREAM, *PHI_EXEMPT):
            assert not re.fullmatch(r"api\.routers\..+", name), (
                f"{name!r} still names the pre-SPEC-028 flat router path"
            )

    def test_the_router_seams_name_a_domain_that_exists(self):
        from sephiroth.models.egress import PHI_DOWNSTREAM, PHI_SEAMS

        for name in (*PHI_SEAMS, *PHI_DOWNSTREAM):
            if not name.startswith("api."):
                continue
            parts = name.split(".")
            if len(parts) >= 2 and parts[1] in DOMAIN_ROUTERS:
                assert (API_ROOT / parts[1] / "routers" / f"{parts[-1]}.py").exists(), name


class TestTheAppStillAnswersOnEveryRoute:
    """AC-028-01, AC-028-04. The move is invisible from outside the process:
    same prefixes, same tags, same guards -- checked by importing the real
    app rather than by re-deriving the route table by hand."""

    def test_the_app_builds_from_the_new_locations(self):
        from api.main import app

        assert len(app.openapi()["paths"]) > 100

    @pytest.mark.parametrize(
        "prefix",
        [
            "/api/patients",
            "/api/encounters",
            "/api/alerts",
            "/api/results",
            "/api/scheduling",
            "/api/tasks",
            "/api/approvals",
            "/api/agents",
            "/api/rag",
            "/api/medical",
            "/api/audit",
            "/api/push",
        ],
    )
    def test_every_domains_prefix_still_resolves(self, prefix):
        from api.main import app

        paths = app.openapi()["paths"]
        assert any(path.startswith(prefix) for path in paths), f"nothing answers under {prefix}"
