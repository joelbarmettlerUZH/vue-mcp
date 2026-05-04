"""Vue Flow-specific entity extractor.

Scans Vue Flow documentation to extract its node-graph surface:
the ``<VueFlow>`` container, the ``<Handle>`` connection point, the
optional addon components (``<Background>``, ``<Controls>``, ``<MiniMap>``,
``<NodeToolbar>``, ``<NodeResizer>``), the composables (``useVueFlow``,
``useHandle``, ``useNode``, ``useEdge``, …), the edge primitives
(``BaseEdge``, ``BezierEdge``, ``StraightEdge``, ``StepEdge``,
``SmoothStepEdge``) and the path helpers (``getBezierPath``, …).
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Sourced from packages/core/src/index.ts plus the addon packages.
_KNOWN_APIS: dict[str, EntityType] = {
    # Core components
    "VueFlow": EntityType.COMPONENT,
    "Handle": EntityType.COMPONENT,
    "Panel": EntityType.COMPONENT,
    # Addon components (separate npm packages)
    "Background": EntityType.COMPONENT,
    "Controls": EntityType.COMPONENT,
    "ControlButton": EntityType.COMPONENT,
    "MiniMap": EntityType.COMPONENT,
    "MiniMapNode": EntityType.COMPONENT,
    "NodeToolbar": EntityType.COMPONENT,
    "NodeResizer": EntityType.COMPONENT,
    "NodeResizeControl": EntityType.COMPONENT,
    # Edge primitives & helpers
    "BaseEdge": EntityType.COMPONENT,
    "BezierEdge": EntityType.COMPONENT,
    "StraightEdge": EntityType.COMPONENT,
    "StepEdge": EntityType.COMPONENT,
    "SmoothStepEdge": EntityType.COMPONENT,
    "SimpleBezierEdge": EntityType.COMPONENT,
    "EdgeText": EntityType.COMPONENT,
    "EdgeLabelRenderer": EntityType.COMPONENT,
    "getBezierPath": EntityType.GLOBAL_API,
    "getSimpleBezierPath": EntityType.GLOBAL_API,
    "getSmoothStepPath": EntityType.GLOBAL_API,
    "getStraightPath": EntityType.GLOBAL_API,
    "getEdgeCenter": EntityType.GLOBAL_API,
    "getMarkerEnd": EntityType.GLOBAL_API,
    # Composables
    "useVueFlow": EntityType.COMPOSABLE,
    "useHandle": EntityType.COMPOSABLE,
    "useNode": EntityType.COMPOSABLE,
    "useEdge": EntityType.COMPOSABLE,
    "useNodeId": EntityType.COMPOSABLE,
    "useConnection": EntityType.COMPOSABLE,
    "useHandleConnections": EntityType.COMPOSABLE,
    "useNodeConnections": EntityType.COMPOSABLE,
    "useNodesData": EntityType.COMPOSABLE,
    "useEdgesData": EntityType.COMPOSABLE,
    "useNodesInitialized": EntityType.COMPOSABLE,
    "useKeyPress": EntityType.COMPOSABLE,
    "useZoomPanHelper": EntityType.COMPOSABLE,
    "useGetPointerPosition": EntityType.COMPOSABLE,
    # State helpers (commonly shown in examples for controlled flows)
    "useNodesState": EntityType.COMPOSABLE,
    "useEdgesState": EntityType.COMPOSABLE,
    # Errors / enums
    "VueFlowError": EntityType.OTHER,
    "ErrorCode": EntityType.OTHER,
    "isErrorOfType": EntityType.GLOBAL_API,
    "ConnectionMode": EntityType.OTHER,
    "ConnectionLineType": EntityType.OTHER,
    "Position": EntityType.OTHER,
    "MarkerType": EntityType.OTHER,
    "PanelPosition": EntityType.OTHER,
    "BackgroundVariant": EntityType.OTHER,
    # Common types referenced from code samples
    "Node": EntityType.OTHER,
    "Edge": EntityType.OTHER,
    "Connection": EntityType.OTHER,
    "EdgeProps": EntityType.OTHER,
    "NodeProps": EntityType.OTHER,
    "FlowExportObject": EntityType.OTHER,
    # Sub-package names (referenced in install commands)
    "@vue-flow/core": EntityType.OTHER,
    "@vue-flow/background": EntityType.OTHER,
    "@vue-flow/controls": EntityType.OTHER,
    "@vue-flow/minimap": EntityType.OTHER,
    "@vue-flow/node-toolbar": EntityType.OTHER,
    "@vue-flow/node-resizer": EntityType.OTHER,
    "@vue-flow/pathfinding-edge": EntityType.OTHER,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)\s*/?>`?$")


class VueFlowEntityExtractor:
    """Entity extractor for Vue Flow documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Seed from the curated table, then enrich with H2/H3 heading scans."""
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vue-flow",
                entity_type=entity_type,
            )

        for md_file in sorted(docs_path.rglob("*.md")):
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(
        self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]
    ) -> None:
        """Extract entities from H2/H3 headings."""
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError:
            return
        md = MarkdownIt()
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
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="vue-flow",
                        entity_type=self._classify(name),
                        page_path=rel_path,
                        section=heading_text.strip(),
                    )
            i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        text = _SLUG_RE.sub("", heading_text).strip()
        if not text:
            return None
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        m = _ANGLE_BRACKETS_RE.match(text)
        if m:
            text = m.group(1)
        text = _TRAILING_PARENS_RE.sub("", text)
        if " " in text and "." not in text:
            return None
        return text or None

    def _classify(self, name: str) -> EntityType:
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("use") and name[3:4].isupper():
            return EntityType.COMPOSABLE
        if name.startswith(("get", "create", "is")):
            return EntityType.GLOBAL_API
        if name and name[0].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Vue Flow ships as a scoped namespace: ``@vue-flow/core`` plus
        addon packages (``@vue-flow/background``, …)."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vue-flow/[\w-]+['\"]"),
        ]
