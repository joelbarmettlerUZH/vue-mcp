<script setup lang="ts">
import { computed } from "vue";
import { useData } from "vitepress";

const props = defineProps<{
  type: string;
  height?: number | string;
  options: Record<string, any>;
  series: any[];
}>();

const { isDark } = useData();

const themedOptions = computed(() => {
  const fg = isDark.value ? "#e5e7eb" : "#374151";
  const bg = isDark.value ? "#1e1e20" : "#ffffff";
  const grid = isDark.value ? "#2e2e32" : "#e5e7eb";

  return {
    ...props.options,
    chart: {
      ...props.options.chart,
      background: "transparent",
      foreColor: fg,
    },
    theme: { mode: isDark.value ? "dark" : "light" },
    grid: {
      ...props.options.grid,
      borderColor: grid,
    },
    tooltip: {
      ...props.options.tooltip,
      theme: isDark.value ? "dark" : "light",
    },
  };
});
</script>

<template>
  <apexchart
    :key="isDark ? 'dark' : 'light'"
    :type="type"
    :height="height ?? 350"
    :options="themedOptions"
    :series="series"
  />
</template>
