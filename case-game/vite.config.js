import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server: http://localhost:5173
// Requests to /api/* are forwarded to the FastAPI backend on port 8000.
// If the backend is not running, the game falls back to the static JSON in public/static/.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
