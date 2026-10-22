import { describe, expect, it } from "vitest";
import { parseCorsOrigins } from "../lib/cors.js";

describe("parseCorsOrigins", () => {
  it("parses comma-separated origins", () => {
    expect(
      parseCorsOrigins("http://localhost:5173, http://127.0.0.1:5173"),
    ).toEqual(["http://localhost:5173", "http://127.0.0.1:5173"]);
  });

  it("preserves wildcard origins", () => {
    expect(parseCorsOrigins("*")).toBe("*");
  });

  it("uses the local development defaults for blank input", () => {
    expect(parseCorsOrigins("")).toEqual([
      "http://localhost:5173",
      "http://127.0.0.1:5173",
    ]);
  });
});
