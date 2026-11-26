import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Собранный фронтенд (npm run build → dist/) раздаёт сам FastAPI вместе с API на /api.
// В dev-режиме (npm run dev) Vite проксирует /api на запущенное приложение.
const API_TARGET = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
