import { shutdownTracing } from "./src/tracing.js";
import express from "express";
import "./lib/env.js";
import cors from "cors";
import http from "http";
import { connectDB } from "./lib/db.js";
import {
  closeRedisAdapter,
  connectRedisAdapter,
  getRedisStatus,
} from "./lib/redis.js";
import { parseCorsOrigins } from "./lib/cors.js";
import {
  groupsRepo,
  messagesRepo,
  populateMessageSender,
  usersRepo,
} from "./repositories/chatRepository.js";
import {
  buildStoredMessagePayload,
  messagePayloadErrorResponse,
} from "./lib/messagePayload.js";

import userRouter from "./routes/userRoutes.js";
import messageRouter from "./routes/messageRoutes.js";
import groupRouter from "./routes/groupRoutes.js";
import { authorizeTideSocket } from "./middleware/tideGateway.js";

import {
  activeSocketConnections,
  conversationJoinsTotal,
  dependencyUp,
  messageProcessingSeconds,
  messagesTotal,
  renderMetrics,
  socketConnectionsTotal,
  socketDisconnectionsTotal,
} from "./src/metrics.js";

import { Server } from "socket.io";
const app = express();
const server = http.createServer(app);

const chatCorsOrigins = parseCorsOrigins(
  process.env.CHAT_CORS_ORIGIN || "http://localhost:5173,http://127.0.0.1:5173",
);
const dependencyState = {
  dynamodb: false,
};

app.get("/health", (_req, res) => {
  res.status(200).json({
    status: "ok",
    service: "chat-service",
    timestamp: new Date().toISOString(),
  });
});

app.get("/metrics", renderMetrics);

// Socket.io setup
export const io = new Server(server, {
  path: "/careers-socket.io",
  cors: {
    origin: chatCorsOrigins,
    // methods: ["GET", "POST"],
  },
  maxHttpBufferSize: Number(
    process.env.CHAT_SOCKET_MAX_BUFFER_BYTES || 24 * 1024 * 1024,
  ),
});
io.use(authorizeTideSocket);

// Store online users by every stable alias we know about:
// chat DynamoDB _id, upstream app user id, and email.
export const userSocketMap = {}; // {userAlias: socketId}
const socketAliasMap = new Map(); // {socketId: string[]}

function getSocketAliases(socket) {
  const identity = socket.data.tideUser;
  const userId = identity?._id, chatUserId = identity?._id, appUserId = identity?.appUserId, email = identity?.email;
  return [
    ...new Set(
      [userId, chatUserId, appUserId, email]
        .flat()
        .filter(Boolean)
        .map((value) => String(value)),
    ),
  ];
}

function includesId(list, id) {
  return Array.isArray(list) && list.map(String).includes(String(id));
}

function conversationRoom(conversationId) {
  return `conversation:${conversationId}`;
}

async function getConversationForUser(conversationId, userId) {
  const group = await groupsRepo.getById(conversationId);
  if (group) {
    if (!includesId(group.members, userId)) {
      throw new Error("conversation_membership_required");
    }
    return { type: "group", group };
  }

  const receiver = await usersRepo.getById(conversationId);
  if (receiver) {
    return { type: "direct", receiver };
  }

  throw new Error("conversation_not_found");
}

async function sendTextMessage({
  conversationId,
  senderId,
  content,
  image,
  attachments,
  clientMessageId,
}) {
  const conversation = await getConversationForUser(conversationId, senderId);
  const storedPayload = await buildStoredMessagePayload({
    text: content,
    image,
    attachments,
    folder: conversation.type === "group" ? "group-messages" : "messages",
    ownerId: senderId,
  });

  if (conversation.type === "group") {
    const message = await messagesRepo.create({
      sender: senderId,
      group: conversation.group._id,
      text: storedPayload.text,
      image: storedPayload.image,
      attachments: storedPayload.attachments,
      seenBy: [senderId],
      clientMessageId,
    });
    const populatedMessage = await populateMessageSender(message);
    if (!message.idempotencyReplay) {
      await groupsRepo.update(conversation.group._id, {
        lastMessage: message._id,
      });
    }
    return {
      ...populatedMessage,
      messageId: populatedMessage._id,
      conversationId: conversation.group._id,
    };
  }

  const message = await messagesRepo.create({
    sender: senderId,
    receiver: conversation.receiver._id,
    text: storedPayload.text,
    image: storedPayload.image,
    attachments: storedPayload.attachments,
    clientMessageId,
  });

  return {
    ...message,
    messageId: message._id,
    conversationId: conversation.receiver._id,
  };
}

// socket.io connection handler
io.on("connection", (socket) => {
  const aliases = getSocketAliases(socket);
  const currentUserId = aliases[0];
  const isAuthenticatedSocket = aliases.length > 0;

  if (isAuthenticatedSocket) {
    socketConnectionsTotal.inc();
    activeSocketConnections.inc();
  }

  console.log(
    `User connected: ${aliases.join(", ") || "anonymous"}, Socket ID: ${socket.id}`,
  );
  if (aliases.length) {
    socketAliasMap.set(socket.id, aliases);
    aliases.forEach((alias) => {
      userSocketMap[alias] = socket.id;
    });
  }
  // Emit event to all connected clients
  io.emit("getOnlineUsers", Object.keys(userSocketMap));

  // Reauthenticate against the active FairEnrol account at most every five minutes.
  const expiry = setTimeout(() => socket.disconnect(true), 300000);
  socket.once("disconnect", () => clearTimeout(expiry));

  socket.on("conversation:join", async (payload = {}, acknowledge) => {
    const conversationId = payload.conversationId;

    try {
      await getConversationForUser(conversationId, currentUserId);
      socket.join(conversationRoom(conversationId));

      conversationJoinsTotal.labels("success").inc();

      acknowledge?.({
        ok: true,
        conversationId,
      });
    } catch (error) {
      conversationJoinsTotal.labels("failed").inc();

      console.warn({
        event: "conversation_join_failed",
        conversationId,
        userId: currentUserId,
        error: error.message,
      });

      acknowledge?.({
        ok: false,
        error: {
          code: error.message,
          message: "Unable to join conversation",
        },
      });
    }
  });

  socket.on("message:send", async (payload = {}, acknowledge) => {
    const stopTimer = messageProcessingSeconds.startTimer();

    try {
      const message = await sendTextMessage({
        conversationId: payload.conversationId,

        senderId: currentUserId,

        content: payload.content,

        image: payload.image,

        attachments: payload.attachments,

        clientMessageId: payload.clientMessageId,
      });

      if (!message.idempotencyReplay) {
        io.to(conversationRoom(message.conversationId)).emit(
          "message:new",
          message,
        );
      }

      messagesTotal.labels("success").inc();

      stopTimer({
        status: "success",
      });

      console.info({
        event: "message_sent",
        messageId: message.messageId,
        conversationId: message.conversationId,
        senderId: currentUserId,
      });

      acknowledge?.({
        ok: true,
        message,
      });
    } catch (error) {
      const payloadError = messagePayloadErrorResponse(error);
      messagesTotal.labels("failed").inc();

      stopTimer({
        status: "failed",
      });

      console.warn({
        event: "message_send_failed",
        conversationId: payload.conversationId,
        userId: currentUserId,
        error: error.message,
      });

      acknowledge?.({
        ok: false,
        error: {
          code: error.message,
          message: payloadError?.body?.message || "Unable to send message",
        },
      });
    }
  });

  socket.on("disconnect", (reason) => {
    if (isAuthenticatedSocket) {
      socketDisconnectionsTotal.inc();
      activeSocketConnections.dec();
    }

    const registeredAliases = socketAliasMap.get(socket.id) || aliases;
    console.log({
      event: "socket_disconnected",
      socketId: socket.id,
      userId: currentUserId,
      reason,
    });
    registeredAliases.forEach((alias) => {
      if (userSocketMap[alias] === socket.id) {
        delete userSocketMap[alias];
      }
    });
    socketAliasMap.delete(socket.id);
    io.emit("getOnlineUsers", Object.keys(userSocketMap));
  });
});
// Middleware
app.use(
  express.json({
    limit: process.env.CHAT_JSON_LIMIT || "24mb",
    verify: (req, res, body) => { req.rawBody = Buffer.from(body); },
  }),
);
app.use(cors({ origin: chatCorsOrigins }));

app.use("/api/status", (req, res) => {
  res.json({ status: "Server is running" });
});
app.use("/api/auth", userRouter);
app.use("/api/users", userRouter);
app.use("/api/messages", messageRouter);
app.use("/api/groups", groupRouter);
app.get("/health/live", (_req, res) => {
  res.status(200).json({
    status: "alive",
    service: "chat-service",
  });
});

app.get("/health/ready", (_req, res) => {
  const redisStatus = getRedisStatus();

  const ready =
    redisStatus.publisherReady &&
    redisStatus.subscriberReady &&
    dependencyState.dynamodb;

  res.status(ready ? 200 : 503).json({
    status: ready ? "ready" : "not_ready",

    dependencies: {
      redis: redisStatus.publisherReady && redisStatus.subscriberReady,

      dynamodb: dependencyState.dynamodb,
    },
  });
});

const PORT = process.env.PORT || 5000;

async function startServer() {
  try {
    await connectDB();
    dependencyState.dynamodb = true;
    dependencyUp.labels("dynamodb").set(1);

    const redisConnected = await connectRedisAdapter(io);
    dependencyUp.labels("redis").set(redisConnected ? 1 : 0);

    server.listen(PORT, () => {
      console.log(`Server is running on port ${PORT}`);
    });
  } catch (error) {
    dependencyUp.labels("redis").set(0);

    dependencyUp.labels("dynamodb").set(0);

    console.error("Chat service startup failed:", error?.message || error);
    process.exit(1);
  }
}

startServer();

async function shutdown() {
  await closeRedisAdapter();
  await shutdownTracing();
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
