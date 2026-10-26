import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // minimal server for the Docker image (web/Dockerfile)
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // The dev server's file-system cache kept serving an old globals.css after its tokens changed (seen 2026-10-26,
    // also across restarts), so dev builds from scratch on each start; production builds are unaffected.
    turbopackFileSystemCacheForDev: false,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
