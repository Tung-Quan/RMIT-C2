import {
  buildStoredMessagePayload,
  messagePayloadErrorResponse,
} from "../lib/messagePayload.js";
import { messagesRepo, usersRepo } from "../repositories/chatRepository.js";
import { io, userSocketMap } from "../server.js";

function userDisplayName(user) {
  return (
    user?.displayName ||
    user?.username ||
    user?.email?.split("@")[0] ||
    "chat-user"
  );
}

function userIdentityKey(user) {
  return String(
    user?.appUserId || user?.email || userDisplayName(user) || user?._id,
  )
    .normalize("NFC")
    .toLowerCase();
}

function userQualityScore(user) {
  const name = userDisplayName(user);
  let score = 0;
  if (user?.displayName) score += 4;
  if (/[^\x00-\x7F]/.test(name)) score += 3;
  if (!/-/.test(name)) score += 1;
  if (user?.updatedAt) score += 1;
  return score;
}

function dedupeUsers(users) {
  const byKey = new Map();
  users.forEach((user) => {
    const key = userIdentityKey(user);
    const current = byKey.get(key);
    if (!current || userQualityScore(user) >= userQualityScore(current)) {
      byKey.set(key, user);
    }
  });
  return [...byKey.values()];
}

export const getAllUsers = async (req, res) => {
  try {
    const users = dedupeUsers(await usersRepo.listExcept(req.user._id));
    const unSeenMessages = {};

    await Promise.all(
      users.map(async (user) => {
        const count = await messagesRepo.countUnreadFromSender(
          user._id,
          req.user._id,
        );
        if (count > 0) unSeenMessages[user._id] = count;
      }),
    );

    res.status(200).json({ success: true, users, unSeenMessages });
  } catch (error) {
    console.error("Error fetching users:", error);
    res
      .status(500)
      .json({ success: false, message: "Server error fetching users" });
  }
};

export const getUserById = async (req, res) => {
  try {
    const { id: selectedUserId } = req.params;
    const myId = req.user._id;

    const messages = await messagesRepo.listDirectBetween(myId, selectedUserId);
    await messagesRepo.markDirectSeen(selectedUserId, myId);

    res.status(200).json({ success: true, messages });
  } catch (error) {
    console.error("Error fetching user by ID:", error);
    res
      .status(500)
      .json({ success: false, message: "Server error fetching user" });
  }
};

export const markMessagesAsSeen = async (req, res) => {
  try {
    await messagesRepo.markDirectSeen(req.params.id, req.user._id);
    res.status(200).json({ success: true, message: "Messages marked as seen" });
  } catch (error) {
    console.error("Error marking messages as seen:", error);
    res.status(500).json({
      success: false,
      message: "Server error marking messages as seen",
    });
  }
};

export const sendMessage = async (req, res) => {
  try {
    const { text, image, attachments, clientMessageId } = req.body;
    const receiverId = req.params.id;
    const senderId = req.user._id;

    const storedPayload = await buildStoredMessagePayload({
      text,
      image,
      attachments,
      folder: "messages",
      ownerId: senderId,
    });

    const newMessage = await messagesRepo.create({
      sender: senderId,
      receiver: receiverId,
      text: storedPayload.text,
      image: storedPayload.image,
      attachments: storedPayload.attachments,
      clientMessageId,
    });

    if (!newMessage.idempotencyReplay) {
      const receiver = await usersRepo.getById(receiverId);
      const receiverAliases = [receiverId, receiver?.appUserId, receiver?.email]
        .filter(Boolean)
        .map(String);
      const receiverSocketId = receiverAliases
        .map((alias) => userSocketMap[alias])
        .find(Boolean);
      if (receiverSocketId) {
        io.to(receiverSocketId).emit("newMessage", newMessage);
        console.log(
          `Direct message ${newMessage._id} emitted to ${receiverAliases.join(", ")}`,
        );
      } else {
        console.log(
          `Direct message ${newMessage._id} stored; receiver offline aliases=${receiverAliases.join(", ")}`,
        );
      }
    }

    res
      .status(newMessage.idempotencyReplay ? 200 : 201)
      .json({ success: true, message: newMessage });
  } catch (error) {
    const payloadError = messagePayloadErrorResponse(error);
    if (payloadError) {
      return res.status(payloadError.status).json(payloadError.body);
    }
    console.error("Error sending message:", error);
    res
      .status(500)
      .json({ success: false, message: "Server error sending message" });
  }
};

export const deleteMessage = async (req, res) => {
  try {
    const messageId = req.params.id;
    const userId = req.user._id;
    const message = await messagesRepo.getById(messageId);

    if (!message) {
      return res
        .status(404)
        .json({ success: false, message: "Message not found" });
    }

    if (message.sender !== userId) {
      return res.status(403).json({
        success: false,
        message: "You can only delete your own messages",
      });
    }

    await messagesRepo.delete(messageId);

    const receiverSocketId = userSocketMap[message.receiver];
    if (receiverSocketId) {
      io.to(receiverSocketId).emit("messageDeleted", messageId);
    }

    res
      .status(200)
      .json({ success: true, message: "Message deleted successfully" });
  } catch (error) {
    console.error("Error deleting message:", error);
    res
      .status(500)
      .json({ success: false, message: "Server error deleting message" });
  }
};

export const editMessage = async (req, res) => {
  try {
    const messageId = req.params.id;
    const { text } = req.body;
    const userId = req.user._id;

    if (!text || !text.trim()) {
      return res.status(400).json({
        success: false,
        message: "Message text is required",
      });
    }

    const message = await messagesRepo.getById(messageId);

    if (!message) {
      return res
        .status(404)
        .json({ success: false, message: "Message not found" });
    }

    if (message.sender !== userId) {
      return res.status(403).json({
        success: false,
        message: "You can only edit your own messages",
      });
    }

    const responseMessage = await messagesRepo.update(messageId, {
      text,
      edited: true,
      editedAt: new Date().toISOString(),
    });

    const receiverSocketId = userSocketMap[message.receiver];
    if (receiverSocketId) {
      io.to(receiverSocketId).emit("messageEdited", responseMessage);
    }

    res.status(200).json({ success: true, message: responseMessage });
  } catch (error) {
    console.error("Error editing message:", error);
    res
      .status(500)
      .json({ success: false, message: "Server error editing message" });
  }
};
