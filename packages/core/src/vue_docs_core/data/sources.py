"""Source definitions for Vue ecosystem documentation frameworks."""

from typing import Annotated

from pydantic import BaseModel, Field


class SourceDefinition(BaseModel):
    """Configuration for a single documentation source in the Vue ecosystem."""

    name: Annotated[str, Field(description="Short identifier used as key (e.g. 'vue', 'nuxt')")]
    display_name: Annotated[str, Field(description="Human-readable name (e.g. 'Vue.js')")]
    git_url: Annotated[str, Field(description="Git repository URL for the documentation")]
    docs_subpath: Annotated[
        str, Field(description="Path within the cloned repo to the docs directory")
    ]
    base_url: Annotated[str, Field(description="Public base URL for the documentation site")]
    import_packages: Annotated[
        list[str],
        Field(
            description="Package names for import regex matching (e.g. ['vue', '@vue/runtime-core'])",
            default_factory=list,
        ),
    ]
    synonyms: Annotated[
        dict[str, list[str]],
        Field(
            description="Synonym table mapping phrases to API entity names",
            default_factory=dict,
        ),
    ]
    gemini_context: Annotated[
        str, Field(description="Framework name injected into Gemini prompts (e.g. 'Vue.js')")
    ]
    sidebar_config_path: Annotated[
        str | None,
        Field(description="Relative path from repo root to sidebar/nav config file"),
    ] = None


# ---------------------------------------------------------------------------
# Vue.js synonyms (moved from data/__init__.py)
# ---------------------------------------------------------------------------

VUE_SYNONYMS: dict[str, list[str]] = {
    "two-way binding": ["v-model"],
    "2-way binding": ["v-model"],
    "lifecycle": [
        "onMounted",
        "onUnmounted",
        "onBeforeMount",
        "onBeforeUnmount",
        "onUpdated",
        "onBeforeUpdate",
    ],
    "lifecycle hooks": [
        "onMounted",
        "onUnmounted",
        "onBeforeMount",
        "onBeforeUnmount",
        "onUpdated",
        "onBeforeUpdate",
    ],
    "state management": ["reactive", "ref", "Pinia"],
    "template refs": ["ref", "useTemplateRef"],
    "template reference": ["ref", "useTemplateRef"],
    "emit events": ["defineEmits", "$emit"],
    "emitting events": ["defineEmits", "$emit"],
    "child to parent": ["defineEmits", "$emit"],
    "props": ["defineProps"],
    "component props": ["defineProps", "props"],
    "prop validation": ["defineProps", "props"],
    "slots": ["defineSlots", "useSlots"],
    "named slots": ["v-slot", "defineSlots"],
    "scoped slots": ["v-slot", "defineSlots"],
    "computed property": ["computed"],
    "computed properties": ["computed"],
    "watcher": ["watch", "watchEffect"],
    "watching": ["watch", "watchEffect"],
    "watch changes": ["watch", "watchEffect"],
    "side effect": ["watchEffect"],
    "provide inject": ["provide", "inject"],
    "dependency injection": ["provide", "inject"],
    "parent to child": ["provide", "inject", "defineProps"],
    "suspense": ["Suspense"],
    "teleport": ["Teleport"],
    "portal": ["Teleport"],
    "transition": ["Transition", "TransitionGroup"],
    "animation": ["Transition", "TransitionGroup"],
    "keep alive": ["KeepAlive"],
    "cache component": ["KeepAlive"],
    "dynamic component": ["component", "is"],
    "async component": ["defineAsyncComponent"],
    "lazy loading": ["defineAsyncComponent"],
    "lazy load": ["defineAsyncComponent"],
    "custom directive": ["directive"],
    "plugin": ["app.use"],
    "composable": ["composables"],
    "composables": ["composables"],
    "reusable logic": ["composables"],
    "reactivity": ["ref", "reactive", "computed", "watch"],
    "reactive state": ["ref", "reactive"],
    "virtual dom": ["render", "h"],
    "render function": ["render", "h"],
    "jsx": ["render", "h"],
    "server side rendering": ["renderToString"],
    "ssr": ["renderToString", "useSSRContext"],
    "conditional rendering": ["v-if", "v-else", "v-show"],
    "show hide": ["v-if", "v-show"],
    "list rendering": ["v-for"],
    "loop": ["v-for"],
    "iteration": ["v-for"],
    "event handling": ["v-on"],
    "click handler": ["v-on"],
    "event listener": ["v-on"],
    "form input": ["v-model"],
    "form binding": ["v-model"],
    "class binding": ["v-bind"],
    "style binding": ["v-bind"],
    "attribute binding": ["v-bind"],
    "dynamic class": ["v-bind"],
    "next tick": ["nextTick", "$nextTick"],
    "dom update": ["nextTick", "$nextTick"],
    "force update": ["$forceUpdate"],
    "global properties": ["app.config.globalProperties"],
    "error handling": ["onErrorCaptured", "app.config.errorHandler"],
    "error boundary": ["onErrorCaptured"],
    "expose": ["defineExpose", "expose"],
    "component options": ["defineOptions"],
    "custom element": ["defineCustomElement"],
    "web component": ["defineCustomElement"],
    "shallow ref": ["shallowRef"],
    "shallow reactive": ["shallowReactive"],
    "raw object": ["toRaw", "markRaw"],
    "readonly state": ["readonly", "shallowReadonly"],
    "ref unwrap": ["unref", "toValue", "isRef"],
    "destructure": ["toRefs", "toRef"],
    "effect scope": ["effectScope", "getCurrentScope", "onScopeDispose"],
}

# ---------------------------------------------------------------------------
# Vue Router synonyms
# ---------------------------------------------------------------------------

VUE_ROUTER_SYNONYMS: dict[str, list[str]] = {
    "routing": ["createRouter", "useRouter"],
    "router": ["createRouter", "useRouter"],
    "route params": ["useRoute"],
    "route parameters": ["useRoute"],
    "current route": ["useRoute"],
    "navigation": ["router.push", "router.replace", "router.go"],
    "programmatic navigation": ["router.push", "router.replace"],
    "navigate": ["router.push", "router.replace"],
    "redirect": ["redirect"],
    "route guard": ["beforeEach", "beforeResolve", "afterEach"],
    "navigation guard": ["beforeEach", "beforeResolve", "afterEach"],
    "route middleware": ["beforeEach", "beforeResolve"],
    "auth guard": ["beforeEach"],
    "dynamic route": ["params"],
    "dynamic segment": ["params"],
    "nested routes": ["children"],
    "child routes": ["children"],
    "named routes": ["name"],
    "named views": ["components"],
    "route meta": ["meta"],
    "route metadata": ["meta"],
    "lazy loading routes": ["component"],
    "code splitting routes": ["component"],
    "history mode": ["createWebHistory", "createWebHashHistory", "createMemoryHistory"],
    "hash mode": ["createWebHashHistory"],
    "scroll behavior": ["scrollBehavior"],
    "route transition": ["transition"],
    "router link": ["RouterLink"],
    "router view": ["RouterView"],
    "active link": ["RouterLink"],
    "route alias": ["alias"],
    "catch all route": ["pathMatch"],
    "404 route": ["pathMatch"],
    "query params": ["query"],
    "query string": ["query"],
}

# ---------------------------------------------------------------------------
# VueUse synonyms
# ---------------------------------------------------------------------------

VUEUSE_SYNONYMS: dict[str, list[str]] = {
    "mouse position": ["useMouse", "useMousePressed"],
    "mouse tracking": ["useMouse", "useMouseInElement"],
    "clipboard": ["useClipboard"],
    "copy to clipboard": ["useClipboard"],
    "local storage": ["useLocalStorage", "useStorage"],
    "session storage": ["useSessionStorage", "useStorage"],
    "persist state": ["useLocalStorage", "useStorage"],
    "dark mode": ["useDark", "useColorMode", "usePreferredDark"],
    "theme": ["useDark", "useColorMode"],
    "debounce": ["useDebounceFn", "useDebounce", "refDebounced"],
    "throttle": ["useThrottleFn", "useThrottle", "refThrottled"],
    "fetch data": ["useFetch"],
    "http request": ["useFetch"],
    "api call": ["useFetch"],
    "window size": ["useWindowSize"],
    "screen size": ["useWindowSize", "useBreakpoints"],
    "responsive": ["useBreakpoints", "useMediaQuery"],
    "breakpoints": ["useBreakpoints"],
    "media query": ["useMediaQuery"],
    "intersection observer": ["useIntersectionObserver"],
    "element visibility": ["useElementVisibility", "useIntersectionObserver"],
    "scroll": ["useScroll", "useInfiniteScroll", "useScrollLock"],
    "scroll position": ["useScroll"],
    "infinite scroll": ["useInfiniteScroll"],
    "event listener": ["useEventListener"],
    "keyboard": ["useKeyModifier", "useMagicKeys", "onKeyStroke"],
    "key press": ["useMagicKeys", "onKeyStroke"],
    "hotkey": ["useMagicKeys"],
    "shortcut": ["useMagicKeys"],
    "fullscreen": ["useFullscreen"],
    "geolocation": ["useGeolocation"],
    "idle": ["useIdle"],
    "user inactive": ["useIdle"],
    "network status": ["useNetwork", "useOnline"],
    "online offline": ["useOnline"],
    "permission": ["usePermission"],
    "battery": ["useBattery"],
    "title": ["useTitle"],
    "page title": ["useTitle"],
    "favicon": ["useFavicon"],
    "drag": ["useDraggable"],
    "draggable": ["useDraggable"],
    "resize observer": ["useResizeObserver", "useElementSize"],
    "element size": ["useElementSize", "useResizeObserver"],
    "animation": ["useTransition", "useRafFn"],
    "interval": ["useInterval", "useIntervalFn"],
    "timeout": ["useTimeout", "useTimeoutFn"],
    "toggle": ["useToggle"],
    "boolean toggle": ["useToggle"],
    "v-model": ["useVModel", "useVModels"],
    "virtual list": ["useVirtualList"],
    "websocket": ["useWebSocket"],
    "web worker": ["useWebWorker", "useWebWorkerFn"],
    "eye dropper": ["useEyeDropper"],
    "color picker": ["useEyeDropper"],
    "focus": ["useFocus", "useFocusWithin"],
    "async state": ["useAsyncState"],
    "async queue": ["useAsyncQueue"],
    "counter": ["useCounter"],
    "cycle list": ["useCycleList"],
    "image loading": ["useImage"],
    "object url": ["useObjectUrl"],
    "event bus": ["useEventBus"],
    "share api": ["useShare"],
    "web share": ["useShare"],
    "text selection": ["useTextSelection"],
    "device motion": ["useDeviceMotion"],
    "device orientation": ["useDeviceOrientation"],
    "preferred languages": ["usePreferredLanguages"],
    "timestamp": ["useTimestamp", "useNow", "useDateFormat"],
    "date format": ["useDateFormat"],
    "deep clone": ["useCloned"],
    "undo redo": ["useRefHistory", "useManualRefHistory"],
    "ref history": ["useRefHistory", "useManualRefHistory"],
    "confirmation dialog": ["useConfirmDialog"],
    "stepper": ["useStepper"],
    "sorted": ["useSorted"],
    "array utilities": ["useArrayFilter", "useArrayMap", "useArrayReduce", "useArrayFind"],
    "mutation observer": ["useMutationObserver"],
    "color mode": ["useColorMode", "useDark"],
    "active element": ["useActiveElement"],
    "document visibility": ["useDocumentVisibility"],
    "page visibility": ["useDocumentVisibility"],
    "memory": ["useMemory"],
    "performance observer": ["usePerformanceObserver"],
    "request animation frame": ["useRafFn"],
    "global state": ["createGlobalState", "createSharedComposable"],
    "shared state": ["createGlobalState", "createSharedComposable"],
    "injected state": ["createInjectionState"],
}

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "vue": SourceDefinition(
        name="vue",
        display_name="Vue.js",
        git_url="https://github.com/vuejs/docs.git",
        docs_subpath="src",
        base_url="https://vuejs.org",
        import_packages=["vue", "@vue/runtime-core", "@vue/reactivity"],
        synonyms=VUE_SYNONYMS,
        gemini_context="Vue.js",
        sidebar_config_path=".vitepress/config.ts",
    ),
    "vue-router": SourceDefinition(
        name="vue-router",
        display_name="Vue Router",
        git_url="https://github.com/vuejs/router.git",
        docs_subpath="packages/docs",
        base_url="https://router.vuejs.org",
        import_packages=["vue-router"],
        synonyms=VUE_ROUTER_SYNONYMS,
        gemini_context="Vue Router",
    ),
    "vueuse": SourceDefinition(
        name="vueuse",
        display_name="VueUse",
        git_url="https://github.com/vueuse/vueuse.git",
        docs_subpath="packages",
        base_url="https://vueuse.org",
        import_packages=[
            "@vueuse/core",
            "@vueuse/shared",
            "@vueuse/math",
            "@vueuse/router",
            "@vueuse/integrations",
            "@vueuse/firebase",
            "@vueuse/rxjs",
            "@vueuse/electron",
            "@vueuse/nuxt",
        ],
        synonyms=VUEUSE_SYNONYMS,
        gemini_context="VueUse",
    ),
}


def get_enabled_sources(enabled_csv: str = "") -> list[SourceDefinition]:
    """Return SourceDefinition objects for the comma-separated enabled source names.

    If *enabled_csv* is empty or not provided, returns **all** registered sources.
    """
    names = [s.strip() for s in enabled_csv.split(",") if s.strip()]
    if not names:
        return list(SOURCE_REGISTRY.values())
    sources = []
    for name in names:
        if name in SOURCE_REGISTRY:
            sources.append(SOURCE_REGISTRY[name])
        else:
            available = ", ".join(sorted(SOURCE_REGISTRY.keys()))
            raise ValueError(f"Unknown source '{name}'. Available: {available}")
    return sources
