import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  root: "src/client/src/renderer",
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
        index:      path.resolve(__dirname, "src/client/src/renderer/index.html"),
        overlay:    path.resolve(__dirname, "src/client/src/renderer/overlay.html"),
        onboarding: path.resolve(__dirname, "src/client/src/renderer/onboarding.html"),
        setup:      path.resolve(__dirname, "src/client/src/renderer/setup.html"),
      },
    },
  },
});
