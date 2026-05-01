import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("\\react\\") || id.includes("/react/") || id.includes("\\react-dom\\") || id.includes("/react-dom/")) {
            return "vendor-react";
          }
          if (id.includes("\\echarts\\") || id.includes("/echarts/")) {
            return "vendor-echarts";
          }
          if (id.includes("\\tabulator-tables\\") || id.includes("/tabulator-tables/")) {
            return "vendor-tabulator";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
})
