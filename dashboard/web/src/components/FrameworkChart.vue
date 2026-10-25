<script setup lang="ts">
import type { ApexOptions } from "apexcharts";
import { computed } from "vue";
import VueApexCharts from "vue3-apexcharts";
import { numberFormat, useChartTheme } from "../theme";
import type { Overview } from "../types";

const props = defineProps<{ frameworks: Overview["frameworks"] }>();
const theme = useChartTheme();

const series = computed(() => [
  { name: "Requests", data: props.frameworks.map((f) => ({ x: f.framework, y: f.count })) },
]);
const height = computed(() => Math.max(160, props.frameworks.length * 30 + 50));

const options = computed<ApexOptions>(() => ({
  chart: {
    type: "bar",
    background: "transparent",
    foreColor: theme.value.muted,
    fontFamily: "inherit",
    toolbar: { show: false },
    animations: { enabled: true, speed: 250 },
  },
  theme: { mode: theme.value.dark ? "dark" : "light" },
  colors: [theme.value.bar],
  plotOptions: { bar: { horizontal: true, barHeight: "68%", borderRadius: 3, borderRadiusApplication: "end" } },
  dataLabels: {
    enabled: true,
    textAnchor: "start",
    offsetX: 6,
    formatter: (v: number) => numberFormat.format(v),
    style: { colors: [theme.value.text], fontWeight: 500 },
    background: { enabled: false },
  },
  grid: { borderColor: theme.value.line, strokeDashArray: 3, xaxis: { lines: { show: true } }, yaxis: { lines: { show: false } } },
  xaxis: {
    type: "category",
    labels: { formatter: (v: string) => numberFormat.format(Math.round(Number(v))) },
    axisBorder: { color: theme.value.line },
    axisTicks: { color: theme.value.line },
    title: { text: "Requests" },
  },
  yaxis: { labels: { style: { colors: theme.value.text } } },
  tooltip: { y: { formatter: (v: number) => `${numberFormat.format(v)} requests` } },
  legend: { show: false },
}));
</script>

<template>
  <VueApexCharts type="bar" :height="height" :options="options" :series="series" />
</template>
