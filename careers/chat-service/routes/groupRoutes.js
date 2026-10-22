import express from "express";
import {
  createGroup,
  getGroups,
  getGroupMessages,
  sendGroupMessage,
  addMember,
  removeMember,
  deleteGroupMessage,
  editGroupMessage,
  updateGroup,
  deleteGroup,
} from "../controller/groupController.js";
import { ProtectedRoute as protectedRoute } from "../middleware/auth.js";

const groupRouter = express.Router();

groupRouter.post("/create", protectedRoute, createGroup);
groupRouter.get("/", protectedRoute, getGroups);
groupRouter.put("/:groupId", protectedRoute, updateGroup);
groupRouter.delete("/:groupId", protectedRoute, deleteGroup);
groupRouter.get("/:groupId/messages", protectedRoute, getGroupMessages);
groupRouter.post("/:groupId/send", protectedRoute, sendGroupMessage);
groupRouter.post("/:groupId/add-member", protectedRoute, addMember);
groupRouter.delete(
  "/:groupId/remove-member/:userId",
  protectedRoute,
  removeMember,
);
groupRouter.put("/message/:messageId", protectedRoute, editGroupMessage);
groupRouter.delete("/message/:messageId", protectedRoute, deleteGroupMessage);

export default groupRouter;
