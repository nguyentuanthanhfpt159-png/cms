import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: "/api/index.py",
      },
    ];
  },
};

export default nextConfig;
