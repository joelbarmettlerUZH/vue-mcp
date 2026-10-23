# Supported Frameworks

Vue Docs MCP provides deep, structured access to the Vue ecosystem documentation. Each framework gets its own set of tools, resources, and prompts, purpose-built for that library's API surface.

## Available

| Framework | Docs | Questions Evaluated | Composite Score |
|---|---|---|---|
| [Vue.js](./vue) | [vuejs.org](https://vuejs.org) | 173 | **4.82 / 5** |
| [Vue Router](./vue-router) | [router.vuejs.org](https://router.vuejs.org) | 49 | **4.78 / 5** |
| [VueUse](./vueuse) | [vueuse.org](https://vueuse.org) | 50 | **4.89 / 5** |
| [Vite](./vite) | [vite.dev](https://vite.dev) | 49 | **4.95 / 5** |
| [Vitest](./vitest) | [vitest.dev](https://vitest.dev) | 50 | **4.77 / 5** |
| [Nuxt](./nuxt) | [nuxt.com](https://nuxt.com) | 49 | **4.80 / 5** |
| [Pinia](./pinia) | [pinia.vuejs.org](https://pinia.vuejs.org) | 49 | **4.81 / 5** |
| [Vue DevTools](./vue-devtools) | [devtools.vuejs.org](https://devtools.vuejs.org) | 50 | **4.37 / 5** |
| [VitePress](./vitepress) | [vitepress.dev](https://vitepress.dev) | 45 | **4.58 / 5** |
| [Pinia Colada](./pinia-colada) | [pinia-colada.esm.dev](https://pinia-colada.esm.dev) | 49 | **4.83 / 5** |
| [VeeValidate](./vee-validate) | [vee-validate.logaretm.com](https://vee-validate.logaretm.com/v4) | 54 | **4.21 / 5** |
| [FormKit](./formkit) | [formkit.com](https://formkit.com) | 55 | **4.59 / 5** |
| [shadcn-vue](./shadcn-vue) | [shadcn-vue.com](https://www.shadcn-vue.com) | 50 | **4.30 / 5** |
| [Vue Flow](./vue-flow) | [vueflow.dev](https://vueflow.dev) | 50 | **4.82 / 5** |

## What Each Framework Provides

When a framework is enabled, your AI assistant gains:

- **3 tools** for searching, looking up APIs, and discovering related concepts
- **5+ resources** for browsing the table of contents, reading pages, and exploring the API index
- **3 prompts** for guided debugging, API comparison, and migration workflows

A cross-framework `ecosystem_search` tool searches all of them at once.

## Choosing a Framework

Every framework is always available. All tools and prompts take a `framework` argument naming the documentation source:

```
docs_search(framework="vue-router", query="navigation guards")
```

| `framework` | Documentation |
|---|---|
| `vue` | Vue.js |
| `vue-router` | Vue Router |
| `vueuse` | VueUse |
| `vite` | Vite |
| `vitest` | Vitest |
| `vue-devtools` | Vue DevTools |
| `pinia` | Pinia |
| `nuxt` | Nuxt |
| `vitepress` | VitePress |
| `pinia-colada` | Pinia Colada |
| `vee-validate` | VeeValidate |
| `shadcn-vue` | shadcn-vue |
| `vue-flow` | Vue Flow |
| `formkit` | FormKit |

Read `ecosystem://sources` to see all supported frameworks and their documentation URLs.

## Roadmap

| Framework | Status |
|---|---|
| [Vue.js](https://vuejs.org) | :white_check_mark: Available |
| [Vue Router](https://router.vuejs.org) | :white_check_mark: Available |
| [VueUse](https://vueuse.org) | :white_check_mark: Available |
| [Vite](https://vite.dev) | :white_check_mark: Available |
| [Vitest](https://vitest.dev) | :white_check_mark: Available |
| [Nuxt](https://nuxt.com) | :white_check_mark: Available |
| [Pinia](https://pinia.vuejs.org) | :white_check_mark: Available |
| [Vue DevTools](https://devtools.vuejs.org) | :white_check_mark: Available |
| [VitePress](https://vitepress.dev) | :white_check_mark: Available |
| [Pinia Colada](https://pinia-colada.esm.dev) | :white_check_mark: Available |
| [VeeValidate](https://vee-validate.logaretm.com/v4/) | :white_check_mark: Available |
| [FormKit](https://formkit.com) | :white_check_mark: Available |
| [shadcn-vue](https://www.shadcn-vue.com) | :white_check_mark: Available |
| [Vue Flow](https://vueflow.dev) | :white_check_mark: Available |
| [Nuxt UI](https://ui.nuxt.com) | :calendar: Planned |
| [TanStack Query](https://tanstack.com/query/latest/docs/framework/vue/overview) | :calendar: Planned |
| [PrimeVue](https://primevue.org) | :calendar: Planned |
| [Vuetify](https://vuetifyjs.com) | :calendar: Planned |
| [Quasar](https://quasar.dev) | :calendar: Planned |
| [Radix Vue](https://www.radix-vue.com) | :calendar: Planned |

Want to see a framework added or reprioritized? [Open an issue](https://github.com/joelbarmettlerUZH/vue-mcp/issues) on GitHub.
