import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["10.145.22.105", "10.*.*.*", "192.168.*.*", "172.16.*.*"],
};

export default nextConfig;
