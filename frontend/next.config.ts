import type { NextConfig } from "next";

const config: NextConfig = {
  // Same-origin browser API keeps session cookies and CSRF protection intact.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*/",
      },
    ];
  },
  skipTrailingSlashRedirect: true,
  experimental: { proxyTimeout: 300000 },
};
export default config;
