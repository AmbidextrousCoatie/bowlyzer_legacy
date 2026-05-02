import { defineConfig } from "vite-plus";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const BACKEND = "http://127.0.0.1:5050";

export default defineConfig({
  lint: { options: { typeAware: true, typeCheck: true } },
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/league": BACKEND,
      "/player": BACKEND,
      "/team": BACKEND,
      "/tournament": BACKEND,
    },
  },
});
