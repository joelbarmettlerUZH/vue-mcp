import { onBeforeUnmount, onMounted, ref } from "vue";

export interface ChartTheme {
  dark: boolean;
  text: string;
  muted: string;
  line: string;
  tool: string;
  resource: string;
  bar: string;
}

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function read(): ChartTheme {
  return {
    dark: window.matchMedia("(prefers-color-scheme: dark)").matches,
    text: css("--text"),
    muted: css("--muted"),
    line: css("--line"),
    tool: css("--tool"),
    resource: css("--resource"),
    bar: css("--bar"),
  };
}

/** Chart colours taken from the page's CSS variables; updates when the OS theme changes. */
export function useChartTheme() {
  const theme = ref<ChartTheme>(read());
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  const update = () => (theme.value = read());
  onMounted(() => query.addEventListener("change", update));
  onBeforeUnmount(() => query.removeEventListener("change", update));
  return theme;
}

export const numberFormat = new Intl.NumberFormat("en-US");
