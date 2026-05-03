import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  rewrites: async () => {
    // Chỉ sử dụng rewrite (proxy) khi chạy ở môi trường local (development)
    // Trên Vercel, chúng ta để Vercel tự động điều hướng vào thư mục /api
    if (process.env.NODE_ENV === 'development') {
      return [
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:5000/api/:path*",
        },
      ];
    }
    return [];
  },
};

export default nextConfig;
