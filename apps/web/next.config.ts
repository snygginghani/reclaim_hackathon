import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal production image: ships only the traced runtime deps, not node_modules.
  output: "standalone",
  // Next's dev server blocks cross-origin requests to its own internal assets
  // (HMR websocket, chunks) unless the origin is allowlisted here. Wildcard segments
  // let any device on a private LAN reach a dev server run on this machine, without
  // hardcoding one IP.
  allowedDevOrigins: ["192.168.*.*", "10.*.*.*", "172.*.*.*"],
};

export default nextConfig;
