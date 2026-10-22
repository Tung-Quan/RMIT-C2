import express from "express";
import {
  getAllUsers,
  getUserById,
  markMessagesAsSeen,
  sendMessage,
  deleteMessage,
  editMessage,
} from "../controller/messageController.js";
import { ProtectedRoute as protectedRoute } from "../middleware/auth.js";

const messageRouter = express.Router();

messageRouter.get("/", (req, res) => {
  res.json({ message: "Message route is working" });
});

messageRouter.get("/users", protectedRoute, getAllUsers);
messageRouter.get("/:id", protectedRoute, getUserById);
messageRouter.put("/mark-seen/:id", protectedRoute, markMessagesAsSeen);
messageRouter.post("/send/:id", protectedRoute, sendMessage);
messageRouter.put("/edit/:id", protectedRoute, editMessage);
messageRouter.delete("/:id", protectedRoute, deleteMessage);

export default messageRouter;
