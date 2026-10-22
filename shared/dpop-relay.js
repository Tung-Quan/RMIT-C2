import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

export function dpopRelay({
  adapterPath = "public/tidecloak.json",
  assetPath = "public/tide_dpop_auth.html",
} = {}) {
  return (req, res, next) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (!pathname.startsWith("/tide_dpop/")) return next();
    if (!["GET", "HEAD"].includes(req.method)) {
      res.statusCode = 405;
      return res.end();
    }
    const match =
      /^\/tide_dpop\/iss\/([0-9a-f]+)\/aud\/([0-9a-f]+)\/tide_dpop_auth\.html$/i.exec(
        pathname,
      );
    if (!match || match[1].length % 2 || match[2].length % 2) {
      res.statusCode = 400;
      return res.end("Invalid relay path");
    }
    try {
      const adapter = JSON.parse(readFileSync(adapterPath, "utf8"));
      const issuer = `${adapter["auth-server-url"].replace(/\/+$/, "")}/realms/${adapter.realm}`;
      if (
        Buffer.from(match[1], "hex").toString("utf8") !== issuer ||
        Buffer.from(match[2], "hex").toString("utf8") !== adapter.resource
      ) {
        res.statusCode = 403;
        return res.end("Unknown realm or client");
      }
      const html = readFileSync(assetPath);
      const hashes = (tag) =>
        [
          ...html
            .toString("utf8")
            .matchAll(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "gi")),
        ]
          .map(
            (m) =>
              `'sha256-${createHash("sha256").update(m[1]).digest("base64")}'`,
          )
          .join(" ");
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.setHeader(
        "Content-Security-Policy",
        `default-src 'self'; script-src 'self' ${hashes("script")}; style-src 'self' ${hashes("style")}`,
      );
      res.setHeader("Allow-CSP-From", "*");
      res.setHeader("Cache-Control", "no-store");
      res.statusCode = 200;
      res.end(req.method === "HEAD" ? undefined : html);
    } catch {
      res.statusCode = 503;
      res.end("Tide relay configuration is not ready");
    }
  };
}
