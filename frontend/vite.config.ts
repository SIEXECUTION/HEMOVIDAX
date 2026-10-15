import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const apiUrl = env.VITE_API_URL?.trim() || "https://hemovidax.onrender.com";
  if (command === "build" && !/^https:\/\/[^\s]+$/.test(apiUrl)) {
    throw new Error(
      "Configura VITE_API_URL con la URL HTTPS del backend de Render antes de compilar.",
    );
  }
  return {
    define:
      command === "build"
        ? { "import.meta.env.VITE_API_URL": JSON.stringify(apiUrl) }
        : {},
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "."),
      },
    },
    server: {
      port: 3000,
      host: "0.0.0.0",
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
      hmr: process.env.DISABLE_HMR !== "true",
      watch: process.env.DISABLE_HMR === "true" ? null : {},
    },
  };
});
