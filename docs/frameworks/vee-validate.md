# VeeValidate

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.26 / 5 composite score</span> &middot; 78.8% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [VeeValidate documentation](https://vee-validate.logaretm.com/v4), covering Vue's leading form-validation library: the components API (`<Form>`, `<Field>`, `<FieldArray>`, `<ErrorMessage>`), the composition API (`useForm`, `useField`, `useFieldArray`, plus 20+ granular helpers), schema integrations (yup, zod, valibot, joi), the `defineRule` / `configure` global helpers, the i18n package, the Nuxt module, and migration paths from v3.

## Activation

VeeValidate is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vee_validate=true)
```

## Tools

### `vee_validate_docs_search`

Semantic search over VeeValidate documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `api`, `tutorials`, `examples`, `integrations`

### `vee_validate_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | API name to look up (e.g. `useField`, `useForm`, `Form`, `defineRule`, `useResetForm`) |

### `vee_validate_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vee-validate://topics` | Full table of contents |
| `vee-validate://topics/{section}` | TOC for a specific section (e.g. `vee-validate://topics/api`) |
| `vee-validate://pages/{path}` | Raw markdown of any doc page (e.g. `vee-validate://pages/api/use-field`) |
| `vee-validate://api/index` | Complete API entity index grouped by type |
| `vee-validate://api/entities/{name}` | Details for a specific API (e.g. `vee-validate://api/entities/useField`) |
| `vee-validate://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vee_validate_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_vee_validate_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `useField, Field`) |
| `migrate_vee_validate_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. v3 directives to v4 components) |

## Coverage

| Area | What's indexed |
|---|---|
| Components API | `<Form>`, `<Field>`, `<FieldArray>`, `<ErrorMessage>` with full slot-scope reference |
| Composition API | `useForm`, `useField`, `useFieldArray`, `useFormContext` |
| Field selectors | `useFieldValue`, `useFieldError`, `useIsFieldDirty`, `useIsFieldTouched`, `useIsFieldValid`, `useValidateField` |
| Form selectors | `useFormValues`, `useFormErrors`, `useIsFormDirty`, `useIsFormTouched`, `useIsFormValid`, `useIsSubmitting`, `useIsValidating`, `useValidateForm`, `useSubmitCount` |
| Programmatic setters | `useSetFieldError`, `useSetFieldTouched`, `useSetFieldValue`, `useSetFormErrors`, `useSetFormTouched`, `useSetFormValues`, `useResetForm`, `useSubmitForm` |
| Global helpers | `defineRule`, `configure`, `getConfig`, `validate`, `validateObject`, `normalizeRules`, `toTypedSchema` |
| Schema integrations | `@vee-validate/yup`, `@vee-validate/zod`, `@vee-validate/valibot`, `@vee-validate/joi` |
| Built-in rules | `@vee-validate/rules` (the full `all` rules registry) |
| i18n | `@vee-validate/i18n` with locale registration and `setLocale` |
| Nuxt | `@vee-validate/nuxt` module setup |
| Concepts | Cross-field validation, async validation, nested objects/arrays, custom inputs, UI library integration, multistep forms, value formatting, checkboxes/radios, dynamic forms |
| Migration | v3 directives + ValidationProvider/Observer to v4 components and composition API |

## Benchmarks vs Context7

Evaluated on 49 VeeValidate questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.71, 3.90, 4.29, 3.90, 4.51] },
    { name: 'Context7', data: [4.43, 3.55, 4.06, 3.31, 4.39] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.71** | 4.43 |
| Completeness | **3.90** | 3.55 |
| Correctness | **4.29** | 4.06 |
| API Coverage | **3.90** | 3.31 |
| Conciseness | **4.51** | 4.39 |
| **Composite** | **4.26** | **3.95** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **81.3%** | 61.2% |
| API Recall | **78.8%** | 69.6% |
| Avg Response Tokens | 6,590 | 1,266 |
| Avg Latency | **1.18s** | 1.73s |
| P95 Latency | 2.47s | **2.12s** |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- VeeValidate's docs cover advanced topics like multistep wizards and value formatting through example pages with live demos. Both providers can only index the prose; live demos are dropped during cleaning.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
