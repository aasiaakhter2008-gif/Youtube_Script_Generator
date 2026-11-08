import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for Docker (server.js + minimal node_modules)
  output: "standalone",
};

export default nextConfig;
