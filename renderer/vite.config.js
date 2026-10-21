import { defineConfig } from "vite";

// relative base: render.mjs serves dist/ from its own tiny static server
export default defineConfig({ base: "./", build: { outDir: "dist", assetsInlineLimit: 0, chunkSizeWarningLimit: 2000 } });
