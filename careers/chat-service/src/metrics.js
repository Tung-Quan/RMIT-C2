import client from "prom-client";

export const metricsRegistry = new client.Registry();

metricsRegistry.setDefaultLabels({
  service: "chat-service",
  environment: process.env.NODE_ENV || "development",
});

client.collectDefaultMetrics({
  register: metricsRegistry,
  prefix: "chat_",
});

export const socketConnectionsTotal = new client.Counter({
  name: "chat_socket_connections_total",

  help: "Total number of accepted Socket.IO connections.",

  registers: [metricsRegistry],
});

export const socketDisconnectionsTotal = new client.Counter({
  name: "chat_socket_disconnections_total",

  help: "Total number of disconnected Socket.IO connections.",

  registers: [metricsRegistry],
});

export const activeSocketConnections = new client.Gauge({
  name: "chat_active_socket_connections",

  help: "Current number of active Socket.IO connections.",

  registers: [metricsRegistry],
});

export const conversationJoinsTotal = new client.Counter({
  name: "chat_conversation_joins_total",

  help: "Total number of conversation join attempts.",

  labelNames: ["status"],

  registers: [metricsRegistry],
});

export const messagesTotal = new client.Counter({
  name: "chat_messages_total",

  help: "Total number of message send attempts.",

  labelNames: ["status"],

  registers: [metricsRegistry],
});

export const idempotencyReplayTotal = new client.Counter({
  name: "idempotency_replay_total",

  help: "Total number of idempotent chat requests replayed from persisted state.",

  labelNames: ["operation"],

  registers: [metricsRegistry],
});

export const dynamodbConditionalFailureTotal = new client.Counter({
  name: "dynamodb_conditional_failure_total",

  help: "Total number of expected DynamoDB conditional write failures.",

  labelNames: ["operation"],

  registers: [metricsRegistry],
});

export const messageProcessingSeconds = new client.Histogram({
  name: "chat_message_processing_seconds",

  help: "Time required to validate, store and broadcast a message.",

  labelNames: ["status"],

  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],

  registers: [metricsRegistry],
});

export const dependencyUp = new client.Gauge({
  name: "chat_dependency_up",

  help: "Whether a chat service dependency is available.",

  labelNames: ["dependency"],

  registers: [metricsRegistry],
});

export async function renderMetrics(_request, response, next) {
  try {
    response.setHeader("Content-Type", metricsRegistry.contentType);

    response.end(await metricsRegistry.metrics());
  } catch (error) {
    next(error);
  }
}
