import {
  groupsRepo,
  messagesRepo,
  populateGroup,
  populateMessageSender,
  populateUser,
} from "../repositories/chatRepository.js";
import {
  buildStoredMessagePayload,
  messagePayloadErrorResponse,
} from "../lib/messagePayload.js";
import { io, userSocketMap } from "../server.js";

function includesId(list, id) {
  return Array.isArray(list) && list.map(String).includes(String(id));
}

function emitToMembers(memberIds, event, payload) {
  memberIds.forEach((memberId) => {
    const socketId = userSocketMap[String(memberId)];
    if (socketId) io.to(socketId).emit(event, payload);
  });
}

export const createGroup = async (req, res) => {
  try {
    const { name, description, avatar, memberIds } = req.body;
    const creator = req.user._id;

    if (!name || !memberIds || memberIds.length === 0) {
      return res.status(400).json({
        success: false,
        message: "Group name and members are required",
      });
    }

    const uniqueMembers = [...new Set([creator, ...memberIds.map(String)])];
    const newGroup = await groupsRepo.create({
      name,
      description: description || "",
      avatar: avatar || "",
      creator,
      members: uniqueMembers,
      admins: [creator],
    });
    const populatedGroup = await populateGroup(newGroup);

    emitToMembers(uniqueMembers, "newGroup", populatedGroup);

    res.status(201).json({
      success: true,
      group: populatedGroup,
      message: "Group created successfully",
    });
  } catch (error) {
    console.error("Error creating group:", error);
    res.status(500).json({
      success: false,
      message: "Server error creating group",
    });
  }
};

export const getGroups = async (req, res) => {
  try {
    const groups = await groupsRepo.listForMember(req.user._id);
    const populatedGroups = await Promise.all(groups.map(populateGroup));
    res.status(200).json({ success: true, groups: populatedGroups });
  } catch (error) {
    console.error("Error fetching groups:", error);
    res.status(500).json({
      success: false,
      message: "Server error fetching groups",
    });
  }
};

export const updateGroup = async (req, res) => {
  try {
    const { groupId } = req.params;
    const { name, description, avatar } = req.body;
    const userId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    if (!includesId(group.admins, userId)) {
      return res.status(403).json({
        success: false,
        message: "Only admins can update group information",
      });
    }

    const patch = {};
    if (name !== undefined) patch.name = name;
    if (description !== undefined) patch.description = description;
    if (avatar !== undefined) patch.avatar = avatar;

    const updatedGroup = await groupsRepo.update(groupId, patch);
    const populatedGroup = await populateGroup(updatedGroup);

    emitToMembers(group.members, "groupUpdated", populatedGroup);

    res.status(200).json({
      success: true,
      group: populatedGroup,
      message: "Group updated successfully",
    });
  } catch (error) {
    console.error("Error updating group:", error);
    res.status(500).json({
      success: false,
      message: "Server error updating group",
    });
  }
};

export const deleteGroup = async (req, res) => {
  try {
    const { groupId } = req.params;
    const userId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    if (group.creator !== userId) {
      return res.status(403).json({
        success: false,
        message: "Only the group creator can delete this group",
      });
    }

    await messagesRepo.deleteByGroup(groupId);
    await groupsRepo.delete(groupId);
    emitToMembers(group.members, "groupDeleted", { groupId });

    res.status(200).json({
      success: true,
      message: "Group deleted successfully",
    });
  } catch (error) {
    console.error("Error deleting group:", error);
    res.status(500).json({
      success: false,
      message: "Server error deleting group",
    });
  }
};

export const getGroupMessages = async (req, res) => {
  try {
    const { groupId } = req.params;
    const userId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    if (!includesId(group.members, userId)) {
      return res.status(403).json({
        success: false,
        message: "You are not a member of this group",
      });
    }

    const messages = await messagesRepo.listGroup(groupId);
    const populatedMessages = await Promise.all(
      messages.map(populateMessageSender),
    );
    await messagesRepo.markGroupSeen(groupId, userId);

    res.status(200).json({ success: true, messages: populatedMessages });
  } catch (error) {
    console.error("Error fetching group messages:", error);
    res.status(500).json({
      success: false,
      message: "Server error fetching messages",
    });
  }
};

export const sendGroupMessage = async (req, res) => {
  try {
    const { groupId } = req.params;
    const { text, image, attachments, clientMessageId } = req.body;
    const senderId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    if (!includesId(group.members, senderId)) {
      return res.status(403).json({
        success: false,
        message: "You are not a member of this group",
      });
    }

    const storedPayload = await buildStoredMessagePayload({
      text,
      image,
      attachments,
      folder: "group-messages",
      ownerId: senderId,
    });

    const newMessage = await messagesRepo.create({
      sender: senderId,
      group: groupId,
      text: storedPayload.text,
      image: storedPayload.image,
      attachments: storedPayload.attachments,
      seenBy: [senderId],
      clientMessageId,
    });
    const populatedMessage = await populateMessageSender(newMessage);

    if (!newMessage.idempotencyReplay) {
      await groupsRepo.update(groupId, { lastMessage: newMessage._id });

      group.members.forEach((memberId) => {
        const socketId = userSocketMap[String(memberId)];
        if (socketId) {
          io.to(socketId).emit("newGroupMessage", {
            groupId,
            message: populatedMessage,
          });
        }
      });
    }

    res.status(newMessage.idempotencyReplay ? 200 : 201).json({
      success: true,
      message: populatedMessage,
    });
  } catch (error) {
    const payloadError = messagePayloadErrorResponse(error);
    if (payloadError) {
      return res.status(payloadError.status).json(payloadError.body);
    }
    console.error("Error sending group message:", error);
    res.status(500).json({
      success: false,
      message: "Server error sending message",
    });
  }
};

export const addMember = async (req, res) => {
  try {
    const { groupId } = req.params;
    const { userId: newMemberId } = req.body;
    const currentUserId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    if (!includesId(group.admins, currentUserId)) {
      return res.status(403).json({
        success: false,
        message: "Only admins can add members",
      });
    }

    if (includesId(group.members, newMemberId)) {
      return res.status(409).json({
        success: false,
        message: "User is already a member",
      });
    }

    const updatedGroup = await groupsRepo.addMember(groupId, newMemberId);
    if (!updatedGroup) {
      return res.status(409).json({
        success: false,
        message: "User is already a member",
      });
    }
    const populatedGroup = await populateGroup(updatedGroup);
    const newMember = await populateUser(newMemberId);

    const socketId = userSocketMap[String(newMemberId)];
    if (socketId) io.to(socketId).emit("addedToGroup", populatedGroup);

    emitToMembers(group.members, "memberAdded", { groupId, newMember });

    res.status(200).json({
      success: true,
      group: populatedGroup,
      message: "Member added successfully",
    });
  } catch (error) {
    console.error("Error adding member:", error);
    res.status(500).json({
      success: false,
      message: "Server error adding member",
    });
  }
};

export const removeMember = async (req, res) => {
  try {
    const { groupId, userId: memberToRemove } = req.params;
    const currentUserId = req.user._id;

    const group = await groupsRepo.getById(groupId);
    if (!group) {
      return res.status(404).json({
        success: false,
        message: "Group not found",
      });
    }

    const isAdmin = includesId(group.admins, currentUserId);
    const isSelf = currentUserId === memberToRemove;

    if (!isAdmin && !isSelf) {
      return res.status(403).json({
        success: false,
        message: "Only admins can remove members",
      });
    }

    if (memberToRemove === group.creator) {
      return res.status(400).json({
        success: false,
        message: "Cannot remove group creator",
      });
    }

    const updatedMembers = group.members.filter(
      (id) => String(id) !== String(memberToRemove),
    );
    const updatedAdmins = group.admins.filter(
      (id) => String(id) !== String(memberToRemove),
    );
    await groupsRepo.update(groupId, {
      members: updatedMembers,
      admins: updatedAdmins,
    });

    const socketId = userSocketMap[String(memberToRemove)];
    if (socketId) io.to(socketId).emit("removedFromGroup", { groupId });

    emitToMembers(updatedMembers, "memberRemoved", {
      groupId,
      removedMemberId: memberToRemove,
    });

    res.status(200).json({
      success: true,
      message: isSelf
        ? "Left group successfully"
        : "Member removed successfully",
    });
  } catch (error) {
    console.error("Error removing member:", error);
    res.status(500).json({
      success: false,
      message: "Server error removing member",
    });
  }
};

export const deleteGroupMessage = async (req, res) => {
  try {
    const { messageId } = req.params;
    const userId = req.user._id;

    const message = await messagesRepo.getById(messageId);
    if (!message || !message.group) {
      return res.status(404).json({
        success: false,
        message: "Message not found",
      });
    }

    const group = await groupsRepo.getById(message.group);
    const isAdmin = includesId(group?.admins, userId);
    const isSender = message.sender === userId;

    if (!isAdmin && !isSender) {
      return res.status(403).json({
        success: false,
        message: "You can only delete your own messages or be an admin",
      });
    }

    await messagesRepo.delete(messageId);
    emitToMembers(group.members, "groupMessageDeleted", {
      groupId: group._id,
      messageId,
    });

    res.status(200).json({
      success: true,
      message: "Message deleted successfully",
    });
  } catch (error) {
    console.error("Error deleting group message:", error);
    res.status(500).json({
      success: false,
      message: "Server error deleting message",
    });
  }
};

export const editGroupMessage = async (req, res) => {
  try {
    const { messageId } = req.params;
    const { text } = req.body;
    const userId = req.user._id;

    if (!text || !text.trim()) {
      return res.status(400).json({
        success: false,
        message: "Message text is required",
      });
    }

    const message = await messagesRepo.getById(messageId);
    if (!message || !message.group) {
      return res.status(404).json({
        success: false,
        message: "Message not found",
      });
    }

    if (message.sender !== userId) {
      return res.status(403).json({
        success: false,
        message: "You can only edit your own messages",
      });
    }

    const updatedMessage = await messagesRepo.update(messageId, {
      text,
      edited: true,
      editedAt: new Date().toISOString(),
    });
    const populatedMessage = await populateMessageSender(updatedMessage);
    const group = await groupsRepo.getById(message.group);

    emitToMembers(group.members, "groupMessageEdited", {
      groupId: group._id,
      message: populatedMessage,
    });

    res.status(200).json({
      success: true,
      message: populatedMessage,
    });
  } catch (error) {
    console.error("Error editing group message:", error);
    res.status(500).json({
      success: false,
      message: "Server error editing message",
    });
  }
};
