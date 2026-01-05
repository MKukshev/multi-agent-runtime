import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow requests to backend APIs
  async rewrites() {
    return [];
  },
};

export default nextConfig;
