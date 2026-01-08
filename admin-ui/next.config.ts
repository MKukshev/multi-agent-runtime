import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for Docker deployment
  output: 'standalone',
  
  // Allow requests to backend APIs
  async rewrites() {
    return [];
  },
};

export default nextConfig;
