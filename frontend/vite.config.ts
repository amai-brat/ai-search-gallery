import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В dev-режиме запросы на /api уходят на FastAPI, поэтому CORS не мешает.
const API_TARGET = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
