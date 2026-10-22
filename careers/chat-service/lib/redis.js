import { createAdapter } from "@socket.io/redis-adapter";
import { createClient } from "redis";
import "./env.js";
import { dependencyUp } from "../src/metrics.js";

let pubClient;
let subClient;

export async function connectRedisAdapter(io) {
  const enabled = process.env.REDIS_ENABLED !== "false";
  if (!enabled) {
    console.log("Redis adapter disabled by REDIS_ENABLED=false");
    return false;
  }

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  pubClient = createClient({ url: redisUrl });
  subClient = pubClient.duplicate();

  pubClient.on("error", (error) => {
    dependencyUp.labels("redis").set(0);
    console.error("Redis pub client error:", error.message);
  });
  subClient.on("error", (error) => {
    dependencyUp.labels("redis").set(0);
    console.error("Redis sub client error:", error.message);
  });
  pubClient.on("reconnecting", () => dependencyUp.labels("redis").set(0));
  subClient.on("reconnecting", () => dependencyUp.labels("redis").set(0));
  pubClient.on("ready", () => dependencyUp.labels("redis").set(1));
  subClient.on("ready", () => dependencyUp.labels("redis").set(1));

  try {
    await Promise.all([pubClient.connect(), subClient.connect()]);
    await pubClient.ping();
    dependencyUp.labels("redis").set(1);
    io.adapter(createAdapter(pubClient, subClient));
    console.log(`Socket.IO Redis adapter connected at ${redisUrl}`);
    return true;
  } catch (error) {
    const required = process.env.REDIS_ADAPTER_REQUIRED === "true";
    dependencyUp.labels("redis").set(0);
    console.error("Redis adapter connection failed:", error.message);
    if (required) throw error;
    console.warn(
      "Continuing with in-memory Socket.IO adapter. Set REDIS_ADAPTER_REQUIRED=true to fail fast.",
    );
    return false;
  }
}

export async function closeRedisAdapter() {
  await Promise.allSettled([subClient?.destroy?.(), pubClient?.destroy?.()]);
}

export function getRedisStatus() {
  return {
    publisherReady: Boolean(pubClient?.isReady),
    subscriberReady: Boolean(subClient?.isReady),
  };
}

export async function consumeGatewayNonce(id) {
  if (!pubClient?.isReady) throw new Error("Chat replay store is unavailable");
  return (await pubClient.set(`fairenrol:gateway:${id}`, "1", { NX: true, EX: 40 })) === "OK";
}
