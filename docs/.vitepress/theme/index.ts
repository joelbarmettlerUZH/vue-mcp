import DefaultTheme from "vitepress/theme";
import "./custom.css";
import type { Theme } from "vitepress";
import VueApexCharts from "vue3-apexcharts";
import ApexChart from "./ApexChart.vue";
import ObfuscatedEmail from "./components/ObfuscatedEmail.vue";

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.use(VueApexCharts);
    app.component("ApexChart", ApexChart);
    app.component("ObfuscatedEmail", ObfuscatedEmail);
  },
} satisfies Theme;
