import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // minimal server for the Docker image (web/Dockerfile)
  cacheComponents: true,
  partialPrefetching: true,
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
