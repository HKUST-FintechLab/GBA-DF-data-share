import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: {
    outDir: "../static/game",
    emptyOutDir: true,
    sourcemap: false,
  },
});
