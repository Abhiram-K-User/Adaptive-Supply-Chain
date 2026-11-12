import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/llm": "http://127.0.0.1:8000",
      "/registry": "http://127.0.0.1:8000",
      "/network": "http://127.0.0.1:8000",
      "/evidence": "http://127.0.0.1:8000",
      "/events": "http://127.0.0.1:8000",
      "/feeds": "http://127.0.0.1:8000",
      "/ingest": "http://127.0.0.1:8000",
      "/plans": "http://127.0.0.1:8000",
      "/decisions": "http://127.0.0.1:8000",
      "/traces": "http://127.0.0.1:8000",
      "/whatif": "http://127.0.0.1:8000",
      "/outcomes": "http://127.0.0.1:8000"
    }
  }
});

