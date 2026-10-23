# Prompts

Prompts are guided workflows that structure how your AI assistant approaches common tasks. Each enabled framework registers its own prompts.

::: info
Prompt support varies by MCP client. Claude Desktop and Claude Code support prompts natively. Other clients may expose them differently or not at all.
:::

## Prompts

Three prompts cover every framework. Each takes a required `framework` argument:

| Prompt | Purpose |
|---|---|
| `debug_issue` | Systematic debugging workflow for framework-specific issues |
| `compare_apis` | Side-by-side comparison of APIs or patterns |
| `migrate_pattern` | Step-by-step migration guide between patterns |

See the framework pages for parameters and examples:
- [Vue.js prompts](/frameworks/vue#prompts)
- [Vue Router prompts](/frameworks/vue-router#prompts)

## How Prompts Work

### Debug Workflow

Given a symptom and optional code snippet, the assistant will:

1. Identify the concept involved
2. Search the documentation with `docs_search`
3. Look up specific APIs using `api_lookup`
4. Explore related patterns with `get_related`
5. Explain the root cause with documentation references
6. Provide a fix and prevention tip

### Compare Workflow

Given a comma-separated list of APIs or patterns, the assistant produces a structured comparison covering purpose, reactivity behavior, performance, decision criteria, code examples, and common mistakes.

### Migrate Workflow

Given a source and target pattern, the assistant produces a migration guide with: why migrate, concept mapping table, step-by-step before/after code examples, and common gotchas.
