import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

function getDevProxyTarget(rawValue: string | undefined): string {
  const value = (rawValue || "").trim();
  if (!value) {
    throw new Error(
      "[vite] Missing DEV_PROXY_TARGET. Please set it in frontend/.env.development, e.g. DEV_PROXY_TARGET=http://localhost:38001"
    );
  }
  try {
    return new URL(value).toString();
  } catch {
    throw new Error(
      `[vite] Invalid DEV_PROXY_TARGET: "${value}". Expected a full URL like http://localhost:38001`
    );
  }
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devProxyTarget =
    command === "serve" ? getDevProxyTarget(env.DEV_PROXY_TARGET) : "http://localhost:38001";
  const devStorageProxyTarget =
    command === "serve"
      ? (env.DEV_STORAGE_PROXY_TARGET || "http://localhost:8000").trim()
      : "http://localhost:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    base: "/",
    build: {
      outDir: "dist",
      emptyOutDir: true,
      assetsDir: "assets",
      rollupOptions: {
        output: {
          manualChunks: undefined,
        },
      },
    },
    server: {
      host: "0.0.0.0",
      port: 3000,
      proxy: {
        "/api": {
          target: devProxyTarget,
          changeOrigin: true,
        },
        "/storage": {
          target: devStorageProxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
