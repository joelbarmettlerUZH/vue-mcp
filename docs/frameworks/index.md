# Supported Frameworks

Vue Docs MCP provides deep, structured access to the Vue ecosystem documentation. Each framework gets its own set of tools, resources, and prompts, purpose-built for that library's API surface.

## Available

| Framework | Docs | Questions Evaluated | Composite Score |
|---|---|---|---|
| [Vue.js](./vue) | [vuejs.org](https://vuejs.org) | 173 | **4.82 / 5** |
| [Vue Router](./vue-router) | [router.vuejs.org](https://router.vuejs.org) | 49 | **4.78 / 5** |
| [VueUse](./vueuse) | [vueuse.org](https://vueuse.org) | 50 | **4.89 / 5** |

## What Each Framework Provides

When a framework is enabled, your AI assistant gains:

- **3 tools** for searching, looking up APIs, and discovering related concepts
- **5+ resources** for browsing the table of contents, reading pages, and exploring the API index
- **3 prompts** for guided debugging, API comparison, and migration workflows

When two or more frameworks are active, a cross-framework `ecosystem_search` tool becomes available.

## Activating Frameworks

Only **Vue.js** is enabled by default. Call `set_framework_preferences` to activate additional frameworks for the current session:

```
set_framework_preferences(vue=true, vue_router=true, vueuse=true)
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `vue` | `boolean` | `true` | Enable Vue.js core documentation |
| `vue_router` | `boolean` | `false` | Enable Vue Router documentation |
| `vueuse` | `boolean` | `false` | Enable VueUse documentation |

After calling this, your AI assistant will have access to tools, resources, and prompts for all enabled frameworks. When more than one framework is active, an `ecosystem_search` tool becomes available that searches across all frameworks simultaneously.

Read `ecosystem://preferences` to check which frameworks are currently active. Read `ecosystem://sources` to see all supported frameworks and their status.

## Roadmap

| Framework | Status |
|---|---|
| [Vue.js](https://vuejs.org) | :white_check_mark: Available |
| [Vue Router](https://router.vuejs.org) | :white_check_mark: Available |
| [VueUse](https://vueuse.org) | :white_check_mark: Available |
| [Vite](https://vite.dev) | :calendar: Planned |
| [Vitest](https://vitest.dev) | :calendar: Planned |
| [Nuxt](https://nuxt.com) | :calendar: Planned |
| [Pinia](https://pinia.vuejs.org) | :calendar: Planned |
| [Vue DevTools](https://devtools.vuejs.org) | :calendar: Planned |
| [VitePress](https://vitepress.dev) | :calendar: Planned |
| [Pinia Colada](https://pinia-colada.esm.dev) | :calendar: Planned |
| [VeeValidate](https://vee-validate.logaretm.com/v4/) | :calendar: Planned |
| [FormKit](https://formkit.com) | :calendar: Planned |
| [shadcn-vue](https://www.shadcn-vue.com) | :calendar: Planned |
| [Nuxt UI](https://ui.nuxt.com) | :calendar: Planned |
| [TanStack Query](https://tanstack.com/query/latest/docs/framework/vue/overview) | :calendar: Planned |
| [PrimeVue](https://primevue.org) | :calendar: Planned |
| [Vuetify](https://vuetifyjs.com) | :calendar: Planned |
| [Quasar](https://quasar.dev) | :calendar: Planned |
| [Radix Vue](https://www.radix-vue.com) | :calendar: Planned |

Want to see a framework added or reprioritized? [Open an issue](https://github.com/joelbarmettlerUZH/vue-mcp/issues) on GitHub.
