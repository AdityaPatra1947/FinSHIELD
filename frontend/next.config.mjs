const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000";

/** Same-origin /api proxy (spec 13.1); API_ORIGIN is server-side only. */
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};
