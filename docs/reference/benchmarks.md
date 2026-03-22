# Benchmarks

We evaluate Vue Docs MCP against [Context7](https://context7.com), a general-purpose documentation MCP server supporting 9000+ libraries, using 173 Vue.js questions scored by an LLM judge.

::: info Methodology
Each question has a ground-truth answer with expected API names and documentation paths. Both providers receive the same question and return documentation context. A Gemini judge (temperature 0) scores the retrieved context on 5 dimensions (1-5 scale). API recall measures whether expected API names appear in the response. See the `eval/` directory in the repository for the full evaluation framework.
:::

## Overall Scores

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
    { name: 'Vue Docs MCP', data: [4.93, 4.83, 4.87, 4.53, 4.95] },
    { name: 'Context7', data: [2.09, 1.67, 1.86, 1.90, 4.55] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.93** :trophy: | 2.09 |
| Completeness | **4.83** :trophy: | 1.67 |
| Correctness | **4.87** :trophy: | 1.86 |
| API Coverage | **4.53** :trophy: | 1.90 |
| Conciseness | 4.95 | 4.55 |
| **Composite** | **4.82** :trophy: | **2.41** |

## Scores by Difficulty

<ClientOnly>
<ApexChart
  type="bar"
  height="350"
  :options="{
    chart: { toolbar: { show: false } },
    plotOptions: { bar: { horizontal: false, columnWidth: '55%', borderRadius: 4 } },
    xaxis: { categories: ['Easy', 'Medium', 'Hard', 'Extreme'] },
    yaxis: { min: 0, max: 5, title: { text: 'Composite Score' } },
    colors: ['#42b883', '#f97316'],
    legend: { position: 'bottom' },
    dataLabels: { enabled: true, formatter: function(val) { return val.toFixed(1) } },
  }"
  :series="[
    { name: 'Vue Docs MCP', data: [4.87, 4.84, 4.89, 4.69] },
    { name: 'Context7', data: [2.75, 2.24, 2.20, 2.58] },
  ]"
/>
</ClientOnly>

| Difficulty | Questions | Vue Docs MCP | Context7 |
|---|---|---|---|
| Easy | 29 | **4.87** :trophy: | 2.75 |
| Medium | 27 | **4.84** :trophy: | 2.24 |
| Hard | 66 | **4.89** :trophy: | 2.20 |
| Extreme | 51 | **4.69** :trophy: | 2.58 |

## Scores by Question Type

<ClientOnly>
<ApexChart
  type="bar"
  height="350"
  :options="{
    chart: { toolbar: { show: false } },
    plotOptions: { bar: { horizontal: true, barHeight: '60%', borderRadius: 4 } },
    xaxis: { min: 0, max: 5, title: { text: 'Composite Score' } },
    yaxis: { categories: ['API Lookup', 'How-To', 'Debugging', 'Comparison', 'Conceptual'] },
    colors: ['#42b883', '#f97316'],
    legend: { position: 'bottom' },
    dataLabels: { enabled: true, formatter: function(val) { return val.toFixed(1) } },
  }"
  :series="[
    { name: 'Vue Docs MCP', data: [4.93, 4.86, 4.82, 4.83, 4.65] },
    { name: 'Context7', data: [2.17, 2.43, 2.17, 2.75, 2.56] },
  ]"
/>
</ClientOnly>

| Intent | Questions | Vue Docs MCP | Context7 |
|---|---|---|---|
| API Lookup | 18 | **4.93** :trophy: | 2.17 |
| How-To | 62 | **4.86** :trophy: | 2.43 |
| Debugging | 41 | **4.82** :trophy: | 2.17 |
| Comparison | 20 | **4.83** :trophy: | 2.75 |
| Conceptual | 30 | **4.65** :trophy: | 2.56 |

## Judge Dimension Breakdown

<ClientOnly>
<ApexChart
  type="heatmap"
  height="300"
  :options="{
    chart: { toolbar: { show: false } },
    xaxis: { categories: ['Relevance', 'Completeness', 'Correctness', 'API Coverage', 'Conciseness'] },
    colors: ['#42b883'],
    dataLabels: { enabled: true, style: { fontSize: '14px' } },
    plotOptions: { heatmap: { radius: 4, colorScale: { ranges: [
      { from: 0, to: 2, color: '#ef4444', name: 'Poor' },
      { from: 2, to: 3, color: '#f97316', name: 'Fair' },
      { from: 3, to: 4, color: '#eab308', name: 'Good' },
      { from: 4, to: 5, color: '#42b883', name: 'Excellent' },
    ] } } },
  }"
  :series="[
    { name: 'Context7', data: [
      { x: 'Relevance', y: 2.09 }, { x: 'Completeness', y: 1.67 }, { x: 'Correctness', y: 1.86 }, { x: 'API Coverage', y: 1.90 }, { x: 'Conciseness', y: 4.55 }
    ] },
    { name: 'Vue Docs MCP', data: [
      { x: 'Relevance', y: 4.93 }, { x: 'Completeness', y: 4.83 }, { x: 'Correctness', y: 4.87 }, { x: 'API Coverage', y: 4.53 }, { x: 'Conciseness', y: 4.95 }
    ] },
  ]"
/>
</ClientOnly>

## Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **98.7%** :trophy: | 53.1% |
| Avg Response Tokens | 4,213 | **1,739** |
| Avg Latency | **1.44s** :trophy: | 1.72s |
| P95 Latency | 3.61s | **2.10s** |
| Cost per Query (internal) | $0.0003 | N/A |
| Cost per Query (user-facing) | **Free** :trophy: | $0.002 |

## Pass Rates

Percentage of questions where **all** judge dimensions scored at or above the threshold:

<ClientOnly>
<ApexChart
  type="line"
  height="300"
  :options="{
    chart: { toolbar: { show: false } },
    xaxis: { categories: ['All >= 5', 'All >= 4', 'All >= 3', 'All >= 2'], title: { text: 'Threshold' } },
    yaxis: { min: 0, max: 100, title: { text: 'Pass Rate (%)' }, labels: { formatter: function(val) { return val + '%' } } },
    colors: ['#42b883', '#f97316'],
    legend: { position: 'bottom' },
    markers: { size: 5 },
    stroke: { width: 3 },
    dataLabels: { enabled: true, formatter: function(val) { return val + '%' } },
  }"
  :series="[
    { name: 'Vue Docs MCP', data: [83.8, 86.7, 88.4, 90.8] },
    { name: 'Context7', data: [6.4, 9.2, 13.3, 23.7] },
  ]"
/>
</ClientOnly>

| Threshold | Vue Docs MCP | Context7 |
|---|---|---|
| All dimensions >= 5 | **83.8%** :trophy: | 6.4% |
| All dimensions >= 4 | **86.7%** :trophy: | 9.2% |
| All dimensions >= 3 | **88.4%** :trophy: | 13.3% |
| All dimensions >= 2 | **90.8%** :trophy: | 23.7% |

## Notes on Fairness

- **Path recall** (97% vs 0.6%) is excluded from headline comparisons because our ground truth uses `vuejs.org` paths. Context7 returns `context7.com` URLs, making this metric structurally unfair.
- **Context7 returns Vue 2 content** for some Vue 3 questions, which legitimately affects its scores.
- Context7 is a **general-purpose** service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem. The comparison shows the quality advantage of specialization.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce these results.
