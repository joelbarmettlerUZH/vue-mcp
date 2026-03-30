"""Vitest-specific entity extractor.

Scans Vitest documentation to extract test framework APIs: test/describe runners,
lifecycle hooks (beforeEach, afterEach), expect matchers, vi utility methods
(mocking, timers, spies), and configuration options.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Vitest APIs with their types
_KNOWN_APIS: dict[str, EntityType] = {
    # Test API
    "test": EntityType.GLOBAL_API,
    "it": EntityType.GLOBAL_API,
    "describe": EntityType.GLOBAL_API,
    "suite": EntityType.GLOBAL_API,
    "bench": EntityType.GLOBAL_API,
    "test.skip": EntityType.GLOBAL_API,
    "test.only": EntityType.GLOBAL_API,
    "test.todo": EntityType.GLOBAL_API,
    "test.fails": EntityType.GLOBAL_API,
    "test.concurrent": EntityType.GLOBAL_API,
    "test.sequential": EntityType.GLOBAL_API,
    "test.each": EntityType.GLOBAL_API,
    "test.for": EntityType.GLOBAL_API,
    "test.extend": EntityType.GLOBAL_API,
    "test.scoped": EntityType.GLOBAL_API,
    "describe.skip": EntityType.GLOBAL_API,
    "describe.only": EntityType.GLOBAL_API,
    "describe.todo": EntityType.GLOBAL_API,
    "describe.concurrent": EntityType.GLOBAL_API,
    "describe.sequential": EntityType.GLOBAL_API,
    "describe.shuffle": EntityType.GLOBAL_API,
    "describe.each": EntityType.GLOBAL_API,
    "bench.skip": EntityType.GLOBAL_API,
    "bench.only": EntityType.GLOBAL_API,
    "bench.todo": EntityType.GLOBAL_API,
    # Lifecycle hooks
    "beforeEach": EntityType.LIFECYCLE_HOOK,
    "afterEach": EntityType.LIFECYCLE_HOOK,
    "beforeAll": EntityType.LIFECYCLE_HOOK,
    "afterAll": EntityType.LIFECYCLE_HOOK,
    "aroundEach": EntityType.LIFECYCLE_HOOK,
    "aroundAll": EntityType.LIFECYCLE_HOOK,
    "onTestFailed": EntityType.LIFECYCLE_HOOK,
    "onTestFinished": EntityType.LIFECYCLE_HOOK,
    # Expect / Assert
    "expect": EntityType.GLOBAL_API,
    "expect.soft": EntityType.GLOBAL_API,
    "expect.poll": EntityType.GLOBAL_API,
    "expect.extend": EntityType.GLOBAL_API,
    "expectTypeOf": EntityType.GLOBAL_API,
    "assert": EntityType.GLOBAL_API,
    "assertType": EntityType.GLOBAL_API,
    # Vi utility - mocking
    "vi": EntityType.UTILITY,
    "vi.fn": EntityType.UTILITY,
    "vi.mock": EntityType.UTILITY,
    "vi.unmock": EntityType.UTILITY,
    "vi.doMock": EntityType.UTILITY,
    "vi.doUnmock": EntityType.UTILITY,
    "vi.spyOn": EntityType.UTILITY,
    "vi.hoisted": EntityType.UTILITY,
    "vi.importActual": EntityType.UTILITY,
    "vi.importMock": EntityType.UTILITY,
    "vi.mocked": EntityType.UTILITY,
    "vi.isMockFunction": EntityType.UTILITY,
    # Vi utility - modules
    "vi.resetModules": EntityType.UTILITY,
    "vi.dynamicImportSettled": EntityType.UTILITY,
    # Vi utility - mock management
    "vi.resetAllMocks": EntityType.UTILITY,
    "vi.restoreAllMocks": EntityType.UTILITY,
    "vi.clearAllMocks": EntityType.UTILITY,
    # Vi utility - globals/env
    "vi.stubGlobal": EntityType.UTILITY,
    "vi.unstubAllGlobals": EntityType.UTILITY,
    "vi.stubEnv": EntityType.UTILITY,
    "vi.unstubAllEnvs": EntityType.UTILITY,
    # Vi utility - timers
    "vi.useFakeTimers": EntityType.UTILITY,
    "vi.useRealTimers": EntityType.UTILITY,
    "vi.advanceTimersByTime": EntityType.UTILITY,
    "vi.advanceTimersByTimeAsync": EntityType.UTILITY,
    "vi.advanceTimersToNextTimer": EntityType.UTILITY,
    "vi.advanceTimersToNextTimerAsync": EntityType.UTILITY,
    "vi.runAllTimers": EntityType.UTILITY,
    "vi.runAllTimersAsync": EntityType.UTILITY,
    "vi.runOnlyPendingTimers": EntityType.UTILITY,
    "vi.runOnlyPendingTimersAsync": EntityType.UTILITY,
    "vi.setSystemTime": EntityType.UTILITY,
    "vi.getMockedSystemTime": EntityType.UTILITY,
    "vi.getRealSystemTime": EntityType.UTILITY,
    "vi.isFakeTimers": EntityType.UTILITY,
    "vi.getTimerCount": EntityType.UTILITY,
    # Vi utility - async helpers
    "vi.waitFor": EntityType.UTILITY,
    "vi.waitUntil": EntityType.UTILITY,
    # Config functions
    "defineConfig": EntityType.GLOBAL_API,
    "defineProject": EntityType.GLOBAL_API,
    "defineWorkspace": EntityType.GLOBAL_API,
    "mergeConfig": EntityType.GLOBAL_API,
    "configDefaults": EntityType.GLOBAL_API,
    # Config options
    "include": EntityType.OPTION,
    "exclude": EntityType.OPTION,
    "includeSource": EntityType.OPTION,
    "globals": EntityType.OPTION,
    "environment": EntityType.OPTION,
    "environmentOptions": EntityType.OPTION,
    "testTimeout": EntityType.OPTION,
    "hookTimeout": EntityType.OPTION,
    "teardownTimeout": EntityType.OPTION,
    "pool": EntityType.OPTION,
    "coverage": EntityType.OPTION,
    "reporters": EntityType.OPTION,
    "outputFile": EntityType.OPTION,
    "setupFiles": EntityType.OPTION,
    "globalSetup": EntityType.OPTION,
    "forceRerunTriggers": EntityType.OPTION,
    "testNamePattern": EntityType.OPTION,
    "retry": EntityType.OPTION,
    "bail": EntityType.OPTION,
    "sequence": EntityType.OPTION,
    "typecheck": EntityType.OPTION,
    "browser": EntityType.OPTION,
    "snapshotFormat": EntityType.OPTION,
    "snapshotSerializers": EntityType.OPTION,
    "resolveSnapshotPath": EntityType.OPTION,
    "css": EntityType.OPTION,
    "deps": EntityType.OPTION,
    "alias": EntityType.OPTION,
    "maxConcurrency": EntityType.OPTION,
    "maxWorkers": EntityType.OPTION,
    "fileParallelism": EntityType.OPTION,
    "cache": EntityType.OPTION,
    "clearMocks": EntityType.OPTION,
    "mockReset": EntityType.OPTION,
    "restoreMocks": EntityType.OPTION,
    "unstubEnvs": EntityType.OPTION,
    "unstubGlobals": EntityType.OPTION,
    "allowOnly": EntityType.OPTION,
    "passWithNoTests": EntityType.OPTION,
    "silent": EntityType.OPTION,
    "logHeapUsage": EntityType.OPTION,
    "slowTestThreshold": EntityType.OPTION,
    "chaiConfig": EntityType.OPTION,
    "watch": EntityType.OPTION,
    "watchTriggerPatterns": EntityType.OPTION,
    "root": EntityType.OPTION,
    "dir": EntityType.OPTION,
    "name": EntityType.OPTION,
    "server": EntityType.OPTION,
    "runner": EntityType.OPTION,
    "benchmark": EntityType.OPTION,
    "provide": EntityType.OPTION,
    "ui": EntityType.OPTION,
    "open": EntityType.OPTION,
    "api": EntityType.OPTION,
    "isolate": EntityType.OPTION,
    "mode": EntityType.OPTION,
    "env": EntityType.OPTION,
    "execArgv": EntityType.OPTION,
    "vmMemoryLimit": EntityType.OPTION,
    "projects": EntityType.OPTION,
    "experimental": EntityType.OPTION,
    "diff": EntityType.OPTION,
    "faketimers": EntityType.OPTION,
    "printConsoleTrace": EntityType.OPTION,
    "snapshotEnvironment": EntityType.OPTION,
    "disableConsoleIntercept": EntityType.OPTION,
    "dangerouslyIgnoreUnhandledErrors": EntityType.OPTION,
    "onConsoleLog": EntityType.OPTION,
    "onStackTrace": EntityType.OPTION,
    "onUnhandledError": EntityType.OPTION,
    "includeTaskLocation": EntityType.OPTION,
    "expandSnapshotDiff": EntityType.OPTION,
    "hideSkippedTests": EntityType.OPTION,
    "attachmentsDir": EntityType.OPTION,
    "strictTags": EntityType.OPTION,
    "tags": EntityType.OPTION,
    "update": EntityType.OPTION,
    "detectAsyncLeaks": EntityType.OPTION,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class VitestEntityExtractor:
    """Entity extractor for Vitest documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Vitest docs.

        Combines known API list with heading-based extraction from API and config docs.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vitest",
                entity_type=entity_type,
            )

        # Scan API doc files
        api_dir = docs_path / "api"
        if api_dir.exists():
            for md_file in sorted(api_dir.rglob("*.md")):
                self._scan_headings(md_file, docs_path, dictionary)

        # Scan config files
        config_dir = docs_path / "config"
        if config_dir.exists():
            for md_file in sorted(config_dir.rglob("*.md")):
                if md_file.name == "index.md":
                    continue
                self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]):
        """Extract entities from H2/H3 headings in a markdown file."""
        md = MarkdownIt()
        raw = md_file.read_text(encoding="utf-8")
        tokens = md.parse(raw)
        rel_path = str(md_file.relative_to(docs_path))

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open" and tok.tag in ("h2", "h3") and i + 1 < len(tokens):
                inline = tokens[i + 1]
                heading_text = inline.content if inline.type == "inline" else ""
                name = self._clean_heading(heading_text)
                if name and name not in dictionary:
                    entity_type = self._classify(name)
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="vitest",
                        entity_type=entity_type,
                        page_path=rel_path,
                        section=heading_text.strip(),
                    )
            i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        """Clean an API heading into an entity name."""
        text = _SLUG_RE.sub("", heading_text).strip()
        if not text:
            return None
        # Strip backticks
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        # Strip angle brackets
        m = _ANGLE_BRACKETS_RE.match(text)
        if m:
            text = m.group(1)
        # Strip trailing ()
        text = _TRAILING_PARENS_RE.sub("", text)
        # Skip prose headings (multiple words without dots)
        if " " in text and "." not in text:
            return None
        if not text:
            return None
        return text

    def _classify(self, name: str) -> EntityType:
        """Classify an entity by name pattern."""
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        # Vi utility methods
        if name.startswith("vi."):
            return EntityType.UTILITY
        # Dotted test/describe/bench modifiers
        if name.startswith(("test.", "describe.", "bench.")):
            return EntityType.GLOBAL_API
        # Expect matchers
        if name.startswith("expect."):
            return EntityType.GLOBAL_API
        # Lifecycle hooks
        if name.startswith(("before", "after", "around", "onTest")):
            return EntityType.LIFECYCLE_HOOK
        # Factory/config functions
        if name.startswith(("define", "merge")):
            return EntityType.GLOBAL_API
        # PascalCase = component or class
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for vitest."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vitest['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vitest/config['\"]"),
        ]
