import { beforeEach, describe, expect, it, vi } from "vitest";
import jwt from "jsonwebtoken";
import { createHash, randomUUID } from "node:crypto";

const mocks = vi.hoisted(() => ({ nonce: vi.fn(), list: vi.fn(), create: vi.fn(), get: vi.fn() }));
vi.mock("../lib/redis.js", () => ({ consumeGatewayNonce: mocks.nonce }));
vi.mock("../repositories/chatRepository.js", () => ({ usersRepo: { list: mocks.list, create: mocks.create, getById: mocks.get }, safeUser: u => { const { password, ...rest } = u; return rest; } }));
import { authorizeTideSocket, resolveTideChatUser, verifyGateway } from "../middleware/tideGateway.js";

const secret = "isolated-chat-gateway-test-secret-not-used-in-production";
const identity = { tide_issuer: "urn:test:tide", tide_subject: "test-subject", person_id: "test-person", full_name: "Synthetic Chat Tester", email: null };
function ticket(audience = "careers-chat-connect", extra = {}) {
  const now = Math.floor(Date.now() / 1000);
  return jwt.sign({ ...identity, sub: identity.person_id, iss: "fairenrol-careers-gateway", aud: audience, iat: now, exp: now + 30, jti: randomUUID(), ...extra }, secret, { algorithm: "HS256" });
}
beforeEach(() => {
  process.env.FAIRENROL_GATEWAY_SECRET = secret;
  vi.resetAllMocks(); mocks.nonce.mockResolvedValue(true); mocks.list.mockResolvedValue([]); mocks.create.mockImplementation(async x => x);
});

describe("private Tide chat assertions", () => {
  it("requires an authenticated, short-lived ticket of the correct audience", async () => {
    await expect(verifyGateway(undefined, "careers-chat-connect")).rejects.toThrow();
    await expect(verifyGateway(ticket("careers-api"), "careers-chat-connect")).rejects.toThrow();
    await expect(verifyGateway(ticket(undefined, { exp: Math.floor(Date.now()/1000) - 1 }), "careers-chat-connect")).rejects.toThrow();
    await expect(verifyGateway(ticket(), "careers-chat-connect")).resolves.toMatchObject(identity);
  });
  it("rejects a ticket when the shared replay store reports it consumed", async () => {
    mocks.nonce.mockResolvedValue(false);
    await expect(verifyGateway(ticket(), "careers-chat-connect")).rejects.toThrow("replay");
  });
  it("binds REST assertions to method, original path and exact body bytes", async () => {
    const request = { method: "POST", originalUrl: "/api/messages/send/person", rawBody: Buffer.from('{"text":"synthetic"}') };
    const token = ticket("careers-chat", { method: request.method, path: request.originalUrl, body_sha256: createHash("sha256").update(request.rawBody).digest("hex") });
    await expect(verifyGateway(token, "careers-chat", request)).resolves.toMatchObject(identity);
    await expect(verifyGateway(token, "careers-chat", { ...request, method: "DELETE" })).rejects.toThrow("mismatch");
    await expect(verifyGateway(token, "careers-chat", { ...request, rawBody: Buffer.from("tampered") })).rejects.toThrow("mismatch");
  });
  it("never links a different issuer/subject through matching email or display name", async () => {
    mocks.list.mockResolvedValue([{ _id: "victim", appUserId: "other-identity", email: "same@example.invalid", displayName: identity.full_name }]);
    const user = await resolveTideChatUser({ ...identity, email: "same@example.invalid" });
    expect(user._id).not.toBe("victim"); expect(user.appUserId).toMatch(/^tide:[a-f0-9]{64}$/); expect(user.password).toBeUndefined();
  });
  it("sets socket identity from the verified ticket rather than handshake query aliases", async () => {
    const socket = { data: {}, handshake: { auth: { ticket: ticket() }, query: { userId: "victim", appUserId: "victim" } } };
    const next = vi.fn(); await authorizeTideSocket(socket, next);
    expect(next).toHaveBeenCalledWith(); expect(socket.data.tideUser.appUserId).toMatch(/^tide:/); expect(socket.data.tideUser._id).not.toBe("victim");
  });
  it("fails closed when the replay store is unavailable", async () => {
    mocks.nonce.mockRejectedValue(new Error("Redis unavailable"));
    const next = vi.fn(); await authorizeTideSocket({ data: {}, handshake: { auth: { ticket: ticket() } } }, next);
    expect(next.mock.calls[0][0]).toBeInstanceOf(Error);
  });
});
