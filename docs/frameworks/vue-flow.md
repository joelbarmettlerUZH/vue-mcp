# Vue Flow

<span style="color: var(--vp-c-brand-1); font-weight: 600;">3.88 / 5 composite score</span> &middot; 75.5% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Vue Flow documentation](https://vueflow.dev), covering the node-based diagram library: the `<VueFlow>` container, the `<Handle>` connection point, the addon packages (`Background`, `Controls`, `MiniMap`, `NodeToolbar`, `NodeResizer`), the composables (`useVueFlow`, `useNode`, `useEdge`, `useHandle`, `useNodesData`, `useNodesInitialized`, `useKeyPress`, ...), the edge primitives + path helpers (`BaseEdge`, `BezierEdge`, `getBezierPath`, `getSmoothStepPath`), controlled-flow patterns, custom node/edge authoring, theming, and the worked examples (drag-and-drop, dagre/elk auto-layout, validation, helper lines, multi-step wizards).

## Activation

Vue Flow is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vue_flow=true)
```

## Tools

### `vue_flow_docs_search`

Semantic search over Vue Flow documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `examples`

### `vue_flow_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | API name to look up (e.g. `VueFlow`, `useVueFlow`, `Handle`, `BaseEdge`) |

### `vue_flow_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vue-flow://topics` | Full table of contents |
| `vue-flow://topics/{section}` | TOC for a specific section (e.g. `vue-flow://topics/guide`) |
| `vue-flow://pages/{path}` | Raw markdown of any doc page (e.g. `vue-flow://pages/guide/node`) |
| `vue-flow://api/index` | Complete API entity index |
| `vue-flow://api/entities/{name}` | Details for a specific API (e.g. `vue-flow://api/entities/useVueFlow`) |
| `vue-flow://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vue_flow_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow |
| `compare_vue_flow_apis` | `items` (comma-separated) | Side-by-side comparison (e.g. `BezierEdge, SmoothStepEdge, StraightEdge`) |
| `migrate_vue_flow_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns |

## Coverage

| Area | What's indexed |
|---|---|
| Core | `<VueFlow>` container, `<Handle>` connection point, `<Panel>` overlay |
| Addon components | `<Background>`, `<Controls>`, `<ControlButton>`, `<MiniMap>`, `<MiniMapNode>`, `<NodeToolbar>`, `<NodeResizer>`, `<NodeResizeControl>` |
| Edges | `<BaseEdge>`, `<BezierEdge>`, `<SmoothStepEdge>`, `<StepEdge>`, `<StraightEdge>`, `<EdgeLabelRenderer>` and the path helpers `getBezierPath`, `getSimpleBezierPath`, `getSmoothStepPath`, `getStraightPath`, `getEdgeCenter`, `getMarkerEnd` |
| Composables | `useVueFlow`, `useNode`, `useEdge`, `useHandle`, `useNodeId`, `useConnection`, `useHandleConnections`, `useNodeConnections`, `useNodesData`, `useEdgesData`, `useNodesInitialized`, `useKeyPress`, `useZoomPanHelper`, `useGetPointerPosition` |
| Controlled flow | `useNodesState`, `useEdgesState`, `applyNodeChanges`, `applyEdgeChanges` |
| Errors / enums | `VueFlowError`, `ErrorCode`, `isErrorOfType`, `ConnectionMode`, `ConnectionLineType`, `Position`, `MarkerType`, `PanelPosition`, `BackgroundVariant` |
| Examples | drag-and-drop, dagre/ELK auto-layout (simple + animated), connection validation, connection radius, custom connection line, edge markers, loopback, updatable edges, helper lines, multi-step interaction, hidden nodes, confirm-on-delete |
| Concepts | Theming via CSS custom properties, save/restore via `FlowExportObject`, multi-instance via `id` scoping, viewport configuration, troubleshooting |

## Benchmarks vs Context7

Evaluated on 49 Vue Flow questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

::: info Methodology
Each question has a ground-truth answer with expected API names and documentation paths. Both providers receive the same question and return documentation context. The judge scores the retrieved context on relevance, completeness, correctness, API coverage, and conciseness. See the `eval/` directory in the repository for the full evaluation framework.
:::

### Overall Scores

<ClientOnly>
<ApexChart
  type="radar"
  height="400"
  :options="{
    chart: { toolbar: { show: false } },
    xaxis: { categories: ['Relevance', 'Completeness', 'Correctness', 'API Coverage', 'Conciseness'] },
    yaxis: { min: 0, max: 5, tickAmount: 5 },
    colors: ['#42b883', '#f97316'],
    legend: { position: 'bottom' },
    markers: { size: 4 },
  }"
  :series="[
    { name: 'Vue Docs MCP', data: [4.29, 3.29, 3.86, 3.27, 4.71] },
    { name: 'Context7', data: [4.16, 3.22, 3.86, 3.04, 4.53] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.29** | 4.16 |
| Completeness | **3.29** | 3.22 |
| Correctness | 3.86 | 3.86 |
| API Coverage | **3.27** | 3.04 |
| Conciseness | **4.71** | 4.53 |
| **Composite** | **3.88** | **3.76** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **83.7%** | 64.3% |
| API Recall | **75.5%** | 75.1% |
| Avg Response Tokens | 4,082 | **1,132** |
| Avg Latency | **0.71s** | 1.72s |
| P95 Latency | **1.08s** | 2.07s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- Vue Flow's API reference is generated by TypeDoc into `docs/src/typedocs/` at build time; we skip running TypeDoc during ingestion (it requires the full pnpm install of the docs workspace plus the typedoc-plugin-markdown chain). The seed entity dictionary covers the public surface from each `@vue-flow/*` package's `index.ts`. Both providers face the same prose-only source for the conceptual guide pages.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
