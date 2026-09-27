export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return Response.json({
        ok: true,
        service: "cinderclip",
        version: "0.1.0",
        runtime: "cloudflare-worker",
        processing: false,
        storage: false
      });
    }

    if (url.pathname === "/api/upload" || url.pathname === "/api/generate") {
      return Response.json(
        {
          ok: false,
          error: "The CinderClip cloud video backend is not connected yet. R2 storage and video processing are the next setup step."
        },
        { status: 501 }
      );
    }

    if (url.pathname.startsWith("/api/")) {
      return Response.json(
        { ok: false, error: "API endpoint not found." },
        { status: 404 }
      );
    }

    return env.ASSETS.fetch(request);
  }
};
