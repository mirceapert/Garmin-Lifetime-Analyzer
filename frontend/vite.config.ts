import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the API runs on :8000 (docker compose up) and Vite proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", chunkSizeWarningLimit: 1500 },
});
