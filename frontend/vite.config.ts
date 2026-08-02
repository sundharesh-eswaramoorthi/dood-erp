import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Allow the app to be served through tunnels (ngrok) and any host.
    allowedHosts: true,
    // Same-origin API: proxy /api to the backend so the whole app works behind
    // a single public URL (no CORS, no second tunnel). In Docker the backend is
    // reachable as the "backend" service.
    proxy: {
      "/api": { target: "http://backend:8000", changeOrigin: true },
      // FastAPI's own docs live outside /api, so without these the tunnel
      // answered /docs with the SPA's index.html — a 200 that looked like it
      // worked and showed the app instead of the API reference.
      "/docs": { target: "http://backend:8000", changeOrigin: true },
      "/redoc": { target: "http://backend:8000", changeOrigin: true },
      "/openapi.json": { target: "http://backend:8000", changeOrigin: true },
    },
  },
});
