"""Self-enforcing architecture conventions.

These tests parse the source tree and fail the build when layering rules are
broken — they apply to new code too, including yours.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[2] / "src" / "minirail"

# Directories whose modules must never commit: they run inside a transaction
# owned by their caller (api endpoint, actor, or CLI command).
NO_COMMIT_LAYERS = {"jobs", "service", "fetcher", "models", "schemas"}


def _python_files_under_layer(layer: str) -> list[Path]:
    return [path for path in SRC_ROOT.rglob("*.py") if layer in path.relative_to(SRC_ROOT).parts]


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_no_commit_outside_api_actors_cli() -> None:
    """session.commit() belongs to the api/actors/cli layer only.

    Jobs, services and fetchers are composable units that may run inside a
    larger transaction; if one of them committed, the caller's atomicity
    would silently break.
    """
    offenders: list[str] = []
    for layer in NO_COMMIT_LAYERS:
        for path in _python_files_under_layer(layer):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
                    offenders.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")
    assert not offenders, (
        f"commit() called outside the api/actors/cli layer: {offenders}. "
        "Flush in services/jobs; commit once, in the caller that owns the transaction."
    )


def test_services_and_fetchers_do_not_import_jobs() -> None:
    """Dependency direction: jobs orchestrate services/fetchers, never the reverse."""
    offenders: list[str] = []
    for layer in ("service", "fetcher"):
        for path in _python_files_under_layer(layer):
            tree = ast.parse(path.read_text())
            for module in _imported_modules(tree):
                if ".jobs" in module or module.endswith("jobs"):
                    offenders.append(f"{path.relative_to(SRC_ROOT)} imports {module}")
    assert not offenders, f"service/fetcher modules must not import jobs: {offenders}"


def test_jobs_do_not_import_api() -> None:
    """Jobs are HTTP-agnostic: they are also called from actors and the CLI."""
    offenders: list[str] = []
    for path in _python_files_under_layer("jobs"):
        tree = ast.parse(path.read_text())
        for module in _imported_modules(tree):
            parts = module.split(".")
            if "api" in parts and module != "minirail.utils.api":
                offenders.append(f"{path.relative_to(SRC_ROOT)} imports {module}")
    assert not offenders, f"jobs must not import api modules: {offenders}"
