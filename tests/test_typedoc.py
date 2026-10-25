"""Tests for TypeDoc API page support (Pinia and Vue Router)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from vue_docs_core.config import settings
from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing import typedoc
from vue_docs_core.parsing.adapters.pinia import PiniaAdapter
from vue_docs_core.parsing.adapters.vue_router import VueRouterAdapter
from vue_docs_core.parsing.extractors.pinia import PiniaEntityExtractor
from vue_docs_core.parsing.extractors.vue_router import VueRouterEntityExtractor


def _write(path: Path, text: str = "# page\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _api_tree(api: Path, files: list[str]) -> None:
    for rel in files:
        _write(api / rel)


class TestIterSymbolPages:
    def test_yields_one_symbol_per_page_named_after_the_file(self, tmp_path):
        docs = tmp_path / "docs"
        _api_tree(
            docs / "api",
            [
                "index.md",
                "functions/useRouter.md",
                "interfaces/RouterOptions.md",
                "@pinia/nuxt/interfaces/ModuleOptions.md",
            ],
        )
        found = {s: (p, k) for s, p, k in typedoc.iter_symbol_pages(docs / "api", docs)}
        assert found == {
            "useRouter": ("api/functions/useRouter.md", "functions"),
            "RouterOptions": ("api/interfaces/RouterOptions.md", "interfaces"),
            "ModuleOptions": ("api/@pinia/nuxt/interfaces/ModuleOptions.md", "interfaces"),
        }

    def test_skips_index_default_and_private_names(self, tmp_path):
        docs = tmp_path / "docs"
        _api_tree(
            docs / "api",
            ["index.md", "variables/default.md", "type-aliases/_Private.md", "functions/ok.md"],
        )
        names = [s for s, _, _ in typedoc.iter_symbol_pages(docs / "api", docs)]
        assert names == ["ok"]


class TestStripBoilerplate:
    BREADCRUMB = "[vue-router](../index.md) / useRouter\n\n"

    def test_strips_frontmatter_and_breadcrumb(self):
        raw = f"---\neditLink: false\n---\n\n{self.BREADCRUMB}# useRouter()\n\nBody"
        assert typedoc.strip_typedoc_boilerplate(raw) == "# useRouter()\n\nBody"

    def test_strips_when_the_parser_already_dropped_the_opening_delimiter(self):
        raw = f"editLink: false\n---\n\n{self.BREADCRUMB}# useRouter()\n\nBody"
        assert typedoc.strip_typedoc_boilerplate(raw) == "# useRouter()\n\nBody"

    def test_nested_breadcrumb_with_scoped_package(self):
        raw = (
            "[@pinia/root](../../index.md) / [pinia](../index.md) / storeToRefs\n\n# storeToRefs()"
        )
        assert typedoc.strip_typedoc_boilerplate(raw) == "# storeToRefs()"

    def test_hand_written_pages_are_untouched(self):
        raw = "---\ntitle: Guide\n---\n\n# Guide\n\nSee [the index](./index.md) for more."
        assert typedoc.strip_typedoc_boilerplate(raw) == raw

    def test_only_the_opening_of_the_page_is_stripped(self):
        raw = f"# Title\n\n{self.BREADCRUMB}text"
        assert typedoc.strip_typedoc_boilerplate(raw) == raw


class TestInstallPrebuiltApi:
    def _prebuilt(self, tmp_path: Path, source: str, files: list[str]) -> Path:
        root = tmp_path / "typedoc"
        _api_tree(root / source / "api", files)
        return root

    def test_copies_pages_into_the_clone(self, tmp_path):
        root = self._prebuilt(tmp_path, "pinia", ["pinia/functions/defineStore.md"])
        api_dir = tmp_path / "clone" / "packages" / "docs" / "api"
        with patch.object(settings, "typedoc_dir", str(root)):
            assert typedoc.install_prebuilt_api("pinia", api_dir) is True
        assert (api_dir / "pinia" / "functions" / "defineStore.md").exists()

    def test_refreshes_pages_that_are_already_there(self, tmp_path):
        root = self._prebuilt(tmp_path, "pinia", ["pinia/functions/defineStore.md"])
        api_dir = tmp_path / "api"
        _write(api_dir / "pinia" / "functions" / "defineStore.md", "stale")
        with patch.object(settings, "typedoc_dir", str(root)):
            typedoc.install_prebuilt_api("pinia", api_dir)
        assert (api_dir / "pinia" / "functions" / "defineStore.md").read_text() == "# page\n"

    def test_not_configured_means_not_installed(self, tmp_path):
        with patch.object(settings, "typedoc_dir", ""):
            assert typedoc.install_prebuilt_api("pinia", tmp_path / "api") is False

    def test_empty_prebuilt_dir_means_not_installed(self, tmp_path):
        (tmp_path / "typedoc" / "pinia" / "api").mkdir(parents=True)
        with patch.object(settings, "typedoc_dir", str(tmp_path / "typedoc")):
            assert typedoc.install_prebuilt_api("pinia", tmp_path / "api") is False
        assert not (tmp_path / "api").exists()


class TestGenerateApiDocs:
    def _repo(self, tmp_path: Path, with_script: bool = True) -> Path:
        docs = tmp_path / "repo" / "packages" / "docs"
        docs.mkdir(parents=True)
        if with_script:
            _write(docs / "run-typedoc.mjs", "")
        return tmp_path / "repo"

    def test_skips_when_pages_already_exist(self, tmp_path):
        repo = self._repo(tmp_path)
        _write(repo / "packages" / "docs" / "api" / "functions" / "x.md")
        with patch.object(typedoc.subprocess, "run") as run:
            typedoc.generate_api_docs(repo)
        run.assert_not_called()

    def test_skips_without_node(self, tmp_path):
        with (
            patch.object(typedoc.shutil, "which", return_value=None),
            patch.object(typedoc.subprocess, "run") as run,
        ):
            typedoc.generate_api_docs(self._repo(tmp_path))
        run.assert_not_called()

    def test_skips_without_upstream_script(self, tmp_path):
        with patch.object(typedoc.subprocess, "run") as run:
            typedoc.generate_api_docs(self._repo(tmp_path, with_script=False))
        run.assert_not_called()

    def test_runs_pnpm_install_then_the_upstream_script_without_secrets(self, tmp_path):
        repo = self._repo(tmp_path)
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            result = type("R", (), {"returncode": 0, "stderr": ""})()
            return result

        env = {"PATH": "/usr/bin", "JINA_API_KEY": "k", "DATABASE_URL": "u", "GH_TOKEN": "t"}
        with (
            patch.object(typedoc.shutil, "which", return_value="/usr/bin/x"),
            patch.object(typedoc.subprocess, "run", side_effect=fake_run),
            patch.dict(typedoc.os.environ, env, clear=True),
        ):
            typedoc.generate_api_docs(repo)

        assert [c[0][:2] for c in calls] == [["npx", "-y"], ["node", "run-typedoc.mjs"]]
        assert "--ignore-scripts" in calls[0][0] and "--frozen-lockfile" in calls[0][0]
        for _, kwargs in calls:
            assert "JINA_API_KEY" not in kwargs["env"]
            assert "DATABASE_URL" not in kwargs["env"]
            assert "GH_TOKEN" not in kwargs["env"]
            assert kwargs["env"]["PATH"] == "/usr/bin"

    def test_failed_install_does_not_run_typedoc(self, tmp_path):
        repo = self._repo(tmp_path)
        failing = type("R", (), {"returncode": 1, "stderr": "boom"})()
        with (
            patch.object(typedoc.shutil, "which", return_value="/usr/bin/x"),
            patch.object(typedoc.subprocess, "run", return_value=failing) as run,
        ):
            typedoc.generate_api_docs(repo)
        assert run.call_count == 1


class TestPiniaApiEntities:
    def _docs(self, tmp_path: Path) -> Path:
        docs = tmp_path / "docs"
        _api_tree(
            docs / "api",
            [
                "index.md",
                "pinia/functions/storeToRefs.md",
                "pinia/functions/defineStore.md",
                "pinia/interfaces/DefineStoreOptions.md",
                "pinia/type-aliases/_ActionsTree.md",
            ],
        )
        # Section headings of a generated page must not become entities
        _write(
            docs / "api" / "pinia" / "functions" / "defineStore.md",
            "# defineStore()\n\n## Parameters\n\n### id\n\n## Returns\n\n## Example\n",
        )
        _write(docs / "core-concepts" / "state.md", "# State\n\n## $patch\n\n## Resetting\n")
        return docs

    def test_seeded_apis_get_their_api_page(self, tmp_path):
        d = PiniaEntityExtractor().build_dictionary(self._docs(tmp_path))
        assert d["storeToRefs"].page_path == "api/pinia/functions/storeToRefs.md"
        assert d["defineStore"].page_path == "api/pinia/functions/defineStore.md"
        assert d["storeToRefs"].entity_type == EntityType.COMPOSABLE  # keeps the seeded type

    def test_new_symbols_are_registered_and_types_are_not_components(self, tmp_path):
        d = PiniaEntityExtractor().build_dictionary(self._docs(tmp_path))
        assert d["DefineStoreOptions"].entity_type == EntityType.OTHER
        assert d["DefineStoreOptions"].page_path == "api/pinia/interfaces/DefineStoreOptions.md"

    def test_generated_section_headings_are_not_entities(self, tmp_path):
        d = PiniaEntityExtractor().build_dictionary(self._docs(tmp_path))
        for junk in ("Parameters", "Returns", "Example", "id", "_ActionsTree"):
            assert junk not in d

    def test_seeded_api_without_a_symbol_page_links_to_the_concept_page(self, tmp_path):
        d = PiniaEntityExtractor().build_dictionary(self._docs(tmp_path))
        assert d["$patch"].page_path == "core-concepts/state.md"

    def test_api_page_wins_over_a_concept_page_mention(self, tmp_path):
        docs = self._docs(tmp_path)
        _write(docs / "core-concepts" / "state.md", "# State\n\n## defineStore\n")
        d = PiniaEntityExtractor().build_dictionary(docs)
        assert d["defineStore"].page_path == "api/pinia/functions/defineStore.md"

    def test_works_without_api_pages(self, tmp_path):
        docs = tmp_path / "docs"
        _write(docs / "core-concepts" / "state.md", "# State\n\n## $patch\n")
        d = PiniaEntityExtractor().build_dictionary(docs)
        assert "defineStore" in d and d["defineStore"].page_path == ""


class TestVueRouterApiEntities:
    def _docs(self, tmp_path: Path) -> Path:
        docs = tmp_path / "docs"
        _api_tree(
            docs / "api",
            [
                "index.md",
                "functions/useRouter.md",
                "functions/createRouter.md",
                "interfaces/RouterOptions.md",
                "enumerations/NavigationFailureType.md",
                "variables/RouterLink.md",
            ],
        )
        _write(
            docs / "api" / "functions" / "createRouter.md",
            "# createRouter()\n\n## Parameters\n\n### options\n\n## Returns\n",
        )
        return docs

    def test_seeded_apis_get_their_api_page(self, tmp_path):
        d = VueRouterEntityExtractor().build_dictionary(self._docs(tmp_path))
        assert d["useRouter"].page_path == "api/functions/useRouter.md"
        assert d["createRouter"].page_path == "api/functions/createRouter.md"
        assert d["RouterLink"].page_path == "api/variables/RouterLink.md"
        assert d["useRouter"].entity_type == EntityType.COMPOSABLE

    def test_type_pages_are_other(self, tmp_path):
        d = VueRouterEntityExtractor().build_dictionary(self._docs(tmp_path))
        assert d["RouterOptions"].entity_type == EntityType.OTHER
        assert d["NavigationFailureType"].entity_type == EntityType.OTHER

    def test_generated_section_headings_are_not_entities(self, tmp_path):
        d = VueRouterEntityExtractor().build_dictionary(self._docs(tmp_path))
        for junk in ("Parameters", "Returns", "options"):
            assert junk not in d


class TestAdaptersInstallPrebuiltPages:
    @pytest.mark.parametrize(
        ("adapter", "source", "page"),
        [
            (PiniaAdapter(), "pinia", "pinia/functions/defineStore.md"),
            (VueRouterAdapter(), "vue-router", "functions/useRouter.md"),
        ],
    )
    def test_post_clone_installs_prebuilt_pages(self, tmp_path, adapter, source, page):
        prebuilt = tmp_path / "typedoc"
        _api_tree(prebuilt / source / "api", [page])
        repo = tmp_path / "repo"
        (repo / "packages" / "docs").mkdir(parents=True)

        with (
            patch.object(settings, "typedoc_dir", str(prebuilt)),
            patch("vue_docs_core.parsing.adapters.pinia.generate_api_docs") as pinia_gen,
            patch("vue_docs_core.parsing.adapters.vue_router.generate_api_docs") as router_gen,
        ):
            adapter.post_clone(repo)

        assert (repo / "packages" / "docs" / "api" / page).exists()
        pinia_gen.assert_not_called()
        router_gen.assert_not_called()

    @pytest.mark.parametrize(
        ("adapter", "target"),
        [
            (PiniaAdapter(), "vue_docs_core.parsing.adapters.pinia.generate_api_docs"),
            (VueRouterAdapter(), "vue_docs_core.parsing.adapters.vue_router.generate_api_docs"),
        ],
    )
    def test_post_clone_falls_back_to_local_generation(self, tmp_path, adapter, target):
        repo = tmp_path / "repo"
        (repo / "packages" / "docs").mkdir(parents=True)
        with patch.object(settings, "typedoc_dir", ""), patch(target) as generate:
            adapter.post_clone(repo)
        generate.assert_called_once_with(repo)
