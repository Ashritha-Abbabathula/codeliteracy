import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Vite's default (`localhost`) binds to IPv6 (::1) only on some systems, so a
    // plain http://127.0.0.1:5173 request (and this project's own launch.json
    // config) gets "connection refused" even though the server is running.
    host: true,
  },
});
