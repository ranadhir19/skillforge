import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, API calls go to the FastAPI service on :8000 via this proxy.
// In production builds, set VITE_API_URL to the API service's origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/graphql": "http://localhost:8000",
      "/runs": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/episodes": "http://localhost:8000",
      "/skills": "http://localhost:8000",
      "/import": "http://localhost:8000",
      "/export": "http://localhost:8000",
    },
  },
});
