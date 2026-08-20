import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  reactStrictMode: true,
  async redirects() {
    return [
      { source: "/account/supplier-review", destination: "/admin/suppliers", permanent: false },
      { source: "/account/resource-review", destination: "/admin/resources", permanent: false },
      { source: "/account/moderation", destination: "/admin/moderation", permanent: false },
    ];
  },
};

export default nextConfig;
