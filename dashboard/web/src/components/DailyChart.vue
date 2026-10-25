<script setup lang="ts">
import type { ApexOptions } from "apexcharts";
import { computed } from "vue";
import VueApexCharts from "vue3-apexcharts";
import { numberFormat, useChartTheme } from "../theme";
import type { Overview } from "../types";

const props = defineProps<{ daily: Overview["daily"] }>();
const theme = useChartTheme();

// Days arrive as "YYYY-MM-DD" in UTC; the datetime axis wants timestamps.
const at = (day: string) => Date.parse(`${day}T00:00:00Z`);

const series = computed(() => [
  { name: "Tool calls", data: props.daily.map((d) => ({ x: at(d.day), y: d.toolCalls })) },
  { name: "Resource reads", data: props.daily.map((d) => ({ x: at(d.day), y: d.resourceReads })) },
]);

const options = computed<ApexOptions>(() => ({
  chart: {
    type: "bar",
    stacked: true,
    background: "transparent",
    foreColor: theme.value.muted,
    fontFamily: "inherit",
    toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: false, reset: true } },
    zoom: { enabled: true, type: "x" },
    animations: { enabled: true, speed: 250 },
  },
  theme: { mode: theme.value.dark ? "dark" : "light" },
  colors: [theme.value.tool, theme.value.resource],
  plotOptions: { bar: { columnWidth: "72%", borderRadius: 2, borderRadiusApplication: "end", borderRadiusWhenStacked: "last" } },
  dataLabels: { enabled: false },
  stroke: { width: 0 },
  grid: { borderColor: theme.value.line, strokeDashArray: 3 },
  xaxis: {
    type: "datetime",
    labels: { datetimeUTC: true, format: "dd MMM" },
    axisBorder: { color: theme.value.line },
    axisTicks: { color: theme.value.line },
    tooltip: { enabled: false },
  },
  yaxis: {
    min: 0,
    forceNiceScale: true,
    title: { text: "Requests per day" },
    labels: { formatter: (v: number) => numberFormat.format(Math.round(v)) },
  },
  tooltip: {
    shared: true,
    intersect: false,
    x: { format: "ddd, dd MMM yyyy" },
    y: { formatter: (v: number) => numberFormat.format(v) },
  },
  legend: { position: "top", horizontalAlign: "left", markers: { size: 6 } },
  fill: { opacity: 1 },
}));
</script>

<template>
  <VueApexCharts type="bar" height="320" :options="options" :series="series" />
</template>
