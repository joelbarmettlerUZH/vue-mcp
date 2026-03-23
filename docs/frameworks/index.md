# Supported Frameworks

Vue Docs MCP provides deep, structured access to the Vue ecosystem documentation. Each framework gets its own set of tools, resources, and prompts, purpose-built for that library's API surface.

## Available

| Framework | Docs | Questions Evaluated | Composite Score |
|---|---|---|---|
| [Vue.js](./vue) | [vuejs.org](https://vuejs.org) | 173 | **4.82 / 5** |
| [Vue Router](./vue-router) | [router.vuejs.org](https://router.vuejs.org) | 49 | **4.78 / 5** |

## What Each Framework Provides

When a framework is enabled, your AI assistant gains:

- **3 tools** for searching, looking up APIs, and discovering related concepts
- **5+ resources** for browsing the table of contents, reading pages, and exploring the API index
- **3 prompts** for guided debugging, API comparison, and migration workflows

When two or more frameworks are active, a cross-framework `ecosystem_search` tool becomes available.

## Default Configuration

Only **Vue.js** is enabled by default. To activate additional frameworks, call `set_framework_preferences`:

```
set_framework_preferences(vue=true, vue_router=true)
```

Read `ecosystem://preferences` to check which frameworks are currently active.

## Roadmap

| Framework | Status | Description |
|---|---|---|
| [Vue.js](https://vuejs.org) | :white_check_mark: Available | Core framework |
| [Vue Router](https://router.vuejs.org) | :white_check_mark: Available | Official router |
| [Pinia](https://pinia.vuejs.org) | :calendar: Planned | Official state management |
| [VueUse](https://vueuse.org) | :calendar: Planned | Composition API utilities |
| [Nuxt](https://nuxt.com) | :calendar: Planned | Full-stack framework |
| [Vuetify](https://vuetifyjs.com) | :calendar: Planned | Material Design component library |
| [Vite](https://vite.dev) | :calendar: Planned | Build tool |
| [Vitest](https://vitest.dev) | :calendar: Planned | Unit testing framework |
| [VitePress](https://vitepress.dev) | :calendar: Planned | Static site generator |

Want to see a framework added? [Open an issue](https://github.com/joelbarmettlerUZH/vue-mcp/issues) on GitHub.
