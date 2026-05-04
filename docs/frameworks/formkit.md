# FormKit

<span style="color: var(--vp-c-brand-1); font-weight: 600;">3.92 / 5 composite score</span> &middot; 71.8% API recall &middot; 50 questions evaluated

Vue Docs MCP provides deep access to the official [FormKit documentation](https://formkit.com), covering Vue's most ergonomic form framework: `<FormKit>` and `<FormKitSchema>` components, the core node primitive, validation rules, all 42+ input types, the official plugin set (auto-animate, multi-step, local-storage, zod, floating-labels, ...), the i18n system, theming, and the full @formkit/* package surface (~320 API entries).

::: tip Big API surface
FormKit ships 12 packages. The MCP indexes them all: `@formkit/vue`, `@formkit/core`, `@formkit/inputs`, `@formkit/validation`, `@formkit/i18n`, `@formkit/icons`, `@formkit/themes`, `@formkit/utils`, `@formkit/observer`, `@formkit/schema`, `@formkit/addons`, plus the official plugin packages.
:::

## Activation

FormKit is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(formkit=true)
```

## Tools

### `formkit_docs_search`

Semantic search over FormKit documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `1.getting-started`, `2.essentials`, `3.inputs`, `4.plugins`, `5.guides`, `6.api-reference`

### `formkit_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | API name to look up (e.g. `FormKit`, `createInput`, `createNode`, `useFormKitNodeById`) |

### `formkit_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `formkit://topics` | Full table of contents |
| `formkit://topics/{section}` | TOC for a specific section (e.g. `formkit://topics/3.inputs`) |
| `formkit://pages/{path}` | Raw markdown of any doc page (e.g. `formkit://pages/3.inputs/text`) |
| `formkit://api/index` | Complete API entity index grouped by type |
| `formkit://api/entities/{name}` | Details for a specific API (e.g. `formkit://api/entities/createInput`) |
| `formkit://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_formkit_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow |
| `compare_formkit_apis` | `items` (comma-separated) | Side-by-side comparison (e.g. `group, list`) |
| `migrate_formkit_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns |

## Coverage

| Area | What's indexed |
|---|---|
| Core components | `<FormKit>`, `<FormKitSchema>`, `<FormKitMessages>`, `<FormKitIcon>`, `<FormKitSummary>` |
| Input types | All 42 official inputs: text, email, password, autocomplete, datepicker, taglist, repeater, multi-step, ... |
| Form composition | `form`, `group`, `list`, `repeater` — nested data structuring without prop drilling |
| Validation | Built-in rules, custom rules, async validation, message localization, conditional rules |
| Schema | `FormKitSchema`, `$formkit`/`$el`/`$cmp` shorthands, `if`/`for`/`bind` directives, reactive `$`-expressions |
| Core node | `createNode`, `getNode`, `useFormKitNodeById`, events (input, commit, prop, child, submit) |
| Plugins | auto-animate, auto-height-textarea, floating-labels, local-storage, multi-step, barcode, inertia, zod |
| i18n | `@formkit/i18n` locales, runtime locale switching, message overrides |
| Theming | Genesis / Regenesis themes, Tailwind theme guide, sectionsSchema overrides |
| API reference | ~320 typed API entries across 12 `@formkit/*` packages |
| Guides | Custom inputs, Tailwind themes, restructuring sections, production optimization |
| Integration | Nuxt module (`@formkit/nuxt`), SSR-safe hydration |

## Benchmarks vs Context7

Evaluated on 50 FormKit questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.66, 3.36, 4.10, 3.34, 4.12] },
    { name: 'Context7', data: [4.52, 3.44, 4.12, 3.60, 4.28] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.66** | 4.52 |
| Completeness | 3.36 | **3.44** |
| Correctness | 4.10 | **4.12** |
| API Coverage | 3.34 | **3.60** |
| Conciseness | 4.12 | **4.28** |
| **Composite** | **3.92** | **3.99** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **65.3%** | 0.0%* |
| API Recall | 71.8% | **79.3%** |
| Avg Response Tokens | 2,788 | **1,015** |
| Avg Latency | **0.57s** | 1.53s |
| P95 Latency | **0.72s** | 1.89s |
| Cost per Query (user-facing) | **Free** | $0.002 |

\* Context7's responses don't echo source file paths in a form the substring-based recall metric can match, so its path-recall is reported as 0%. This is a metric artifact of the response shape, not a measure of retrieval quality.

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- Both providers index `formkit/docs-content` (the same source markdown).
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
