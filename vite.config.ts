import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  root: "src/client/renderer",
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: path.resolve(__dirname, "dist/renderer"),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index:      path.resolve(__dirname, "src/client/renderer/index.html"),
        onboarding: path.resolve(__dirname, "src/client/renderer/onboarding.html"),
        setup:      path.resolve(__dirname, "src/client/renderer/setup.html"),
      },
    },
  },
});
