# shadcn-vue

<span style="color: var(--vp-c-brand-1); font-weight: 600;">3.82 / 5 composite score</span> &middot; 90.7% API recall &middot; 50 questions evaluated

Vue Docs MCP provides deep access to the official [shadcn-vue documentation](https://www.shadcn-vue.com), covering the copy-paste component library built on `reka-ui` primitives: 64 documented components, the `npx shadcn-vue@latest add` CLI, `components.json` configuration, theming via Tailwind CSS variables, framework-specific installation guides (Vite, Nuxt, Astro, Laravel), form-library integration recipes (vee-validate, TanStack Form), and the custom-registry workflow.

## Activation

shadcn-vue is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(shadcn_vue=true)
```

## Tools

### `shadcn_vue_docs_search`

Semantic search over shadcn-vue documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `components`, `installation`, `forms`, `dark-mode`, `registry`

### `shadcn_vue_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation. Component names work in both kebab-case (`alert-dialog`) and PascalCase (`AlertDialog`).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | Component name to look up (e.g. `Button`, `data-table`, `Sidebar`) |

### `shadcn_vue_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | Component or concept to explore |

## Resources

| URI | Description |
|---|---|
| `shadcn-vue://topics` | Full table of contents |
| `shadcn-vue://topics/{section}` | TOC for a specific section (e.g. `shadcn-vue://topics/components`) |
| `shadcn-vue://pages/{path}` | Raw markdown of any doc page (e.g. `shadcn-vue://pages/components/button`) |
| `shadcn-vue://api/index` | Complete component index |
| `shadcn-vue://api/entities/{name}` | Details for a specific component (e.g. `shadcn-vue://api/entities/Button`) |
| `shadcn-vue://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_shadcn_vue_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow |
| `compare_shadcn_vue_apis` | `items` (comma-separated) | Side-by-side comparison (e.g. `Dialog, Sheet, Drawer`) |
| `migrate_shadcn_vue_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns |

## Coverage

| Area | What's indexed |
|---|---|
| Components | All 64 official components: Button, Dialog, DataTable, Sidebar, Combobox, Calendar, Sonner, Stepper, Chart, Resizable, ... |
| CLI | `npx shadcn-vue@latest init / add / diff / remove` plus the JavaScript API |
| Configuration | `components.json` schema (`tailwind`, `aliases`, `iconLibrary`, `framework`) |
| Theming | Tailwind v4 CSS variables, OKLCH palette, dark-mode integration |
| Framework setup | Vite, Nuxt, Astro, Laravel installation guides |
| Forms | vee-validate and TanStack Form integration with `<Form>`, `<FormField>`, `<FormControl>`, `<FormMessage>` |
| Dark mode | `useColorMode` patterns per framework |
| Registry | Custom registry schema, hosting, and consumption flow |
| Migration | v3 → v4 (Tailwind v4 + theme cleanup) |

## Benchmarks vs Context7

Evaluated on 50 shadcn-vue questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.46, 3.14, 3.74, 3.46, 4.28] },
    { name: 'Context7', data: [3.98, 3.06, 3.70, 3.24, 4.28] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.46** | 3.98 |
| Completeness | **3.14** | 3.06 |
| Correctness | **3.74** | 3.70 |
| API Coverage | **3.46** | 3.24 |
| Conciseness | 4.28 | 4.28 |
| **Composite** | **3.82** | **3.65** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **87.8%** | 66.3% |
| API Recall | **90.7%** | 79.7% |
| Avg Response Tokens | 4,701 | **1,089** |
| Avg Latency | **0.75s** | 1.79s |
| P95 Latency | **0.94s** | 2.46s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- shadcn-vue's docs are intentionally thin on prose — each component page is mostly an install snippet plus a code example, since the project's philosophy is that you copy-paste source you can read directly. This caps the absolute composite score for both providers; the relative numbers are the meaningful comparison.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
