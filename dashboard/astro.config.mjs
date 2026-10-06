import { defineConfig } from "astro/config";

export default defineConfig({
  server: {
    host: "localhost",
    port: 4321,
  },

  vite: {
    server: {
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },

        "/auth": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  },
});