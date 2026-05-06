import { defineConfig } from "vite-plus";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Match Flask default from `python wsgi.py` (app.run). Override if needed:
//   set BOWLYZER_DEV_API=http://127.0.0.1:PORT && npm run dev
const BACKEND = process.env.BOWLYZER_DEV_API ?? "http://127.0.0.1:5000";

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
