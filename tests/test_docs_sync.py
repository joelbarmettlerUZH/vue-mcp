"""Tests for syncing the upstream docs clones (real git repos, no network)."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_ingestion.cli import _clone_or_pull


def _git(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def _commit(repo: Path, rel: str, text: str, message: str, amend: bool = False) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", *(["--amend"] if amend else []), "-m", message)


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "docs/guide.md", "# Guide\n\nv1\n", "first")
    return repo


@pytest.fixture(autouse=True)
def _no_adapter_hooks(monkeypatch):
    """The demo source has no registered adapter; only the git sync is under test."""
    monkeypatch.setattr(
        "vue_docs_ingestion.cli.get_adapter",
        lambda name: SimpleNamespace(post_clone=lambda r: None),
    )


def _source(upstream: Path) -> SourceDefinition:
    return SourceDefinition(
        name="demo",
        display_name="Demo",
        git_url=f"file://{upstream}",
        docs_subpath="docs",
        base_url="https://example.com",
        gemini_context="Demo docs",
    )


def _guide(data: Path) -> str:
    return (data / "demo-docs" / "docs" / "guide.md").read_text()


def test_clones_then_picks_up_new_commits(tmp_path, upstream):
    data = tmp_path / "data"
    source = _source(upstream)
    _clone_or_pull(source, data)
    assert "v1" in _guide(data)

    _commit(upstream, "docs/guide.md", "# Guide\n\nv2\n", "second")
    _clone_or_pull(source, data)
    assert "v2" in _guide(data)


def test_picks_up_a_rewritten_upstream_history(tmp_path, upstream):
    """A plain `git pull` refuses to reconcile this ("divergent branches") and the stale
    checkout used to be indexed silently."""
    data = tmp_path / "data"
    source = _source(upstream)
    _clone_or_pull(source, data)

    _commit(upstream, "docs/guide.md", "# Guide\n\nrewritten\n", "first", amend=True)
    _clone_or_pull(source, data)

    assert "rewritten" in _guide(data)


def test_unreachable_upstream_raises_instead_of_serving_stale_docs(tmp_path, upstream):
    data = tmp_path / "data"
    source = _source(upstream)
    _clone_or_pull(source, data)

    broken = source.model_copy(update={"git_url": f"file://{tmp_path}/does-not-exist"})
    _git(data / "demo-docs", "remote", "set-url", "origin", broken.git_url)
    with pytest.raises(subprocess.CalledProcessError):
        _clone_or_pull(broken, data)


def test_untracked_generated_files_survive_a_sync(tmp_path, upstream):
    """TypeDoc pages are untracked files inside the clone and must not be wiped."""
    data = tmp_path / "data"
    source = _source(upstream)
    _clone_or_pull(source, data)
    generated = data / "demo-docs" / "docs" / "api" / "x.md"
    generated.parent.mkdir(parents=True)
    generated.write_text("generated")

    _commit(upstream, "docs/guide.md", "# Guide\n\nv2\n", "second")
    _clone_or_pull(source, data)

    assert generated.read_text() == "generated"
    assert "v2" in _guide(data)
