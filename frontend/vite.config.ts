import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development Vite serves the UI on 4151 and forwards /api to the FastAPI server on 4150.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4151,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:4150" },
  },
});
