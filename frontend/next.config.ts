// NextConfig is the type of the object Next.js reads.
import type { NextConfig } from "next";

// Keep Next.js from writing AGENTS.md and CLAUDE.md into the frontend.
const nextConfig: NextConfig = {
  // Disable the generated agent-rule files.
  agentRules: false,
};

// Export the config for the Next.js process.
export default nextConfig;
