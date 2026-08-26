import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    const infoContentSecurityPolicy = {
      key: "Content-Security-Policy",
      value:
        "default-src 'self'; connect-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; form-action 'none'; object-src 'none'; base-uri 'none'; frame-src 'none'",
    };
    const securityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), browsing-topics=()" },
      ...(process.env.NODE_ENV === "production"
        ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
        : []),
    ];
    return [
      { source: "/info", headers: [infoContentSecurityPolicy] },
      { source: "/info/:path*", headers: [infoContentSecurityPolicy] },
      { source: "/:path*", headers: securityHeaders },
    ];
  },
  async redirects() {
    return [
      { source: "/market/trends", destination: "/trend", permanent: true },
      { source: "/account/supplier-review", destination: "/admin/suppliers", permanent: false },
      { source: "/account/resource-review", destination: "/admin/resources", permanent: false },
      { source: "/account/moderation", destination: "/admin/moderation", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/info", destination: "/info/index.html" }];
  },
};

export default nextConfig;
