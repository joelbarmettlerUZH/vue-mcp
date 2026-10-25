import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  root: import.meta.dirname,
  plugins: [vue()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:3100" } },
  build: { outDir: "dist", emptyOutDir: true },
});
