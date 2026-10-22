import crypto from "node:crypto";
import {
  CHAT_TABLES,
  deleteItem,
  getItem,
  isConditionalCheckFailed,
  putItem,
  scanAll,
  updateItem,
} from "../lib/dynamo.js";
import {
  dynamodbConditionalFailureTotal,
  idempotencyReplayTotal,
} from "../src/metrics.js";

function now() {
  return new Date().toISOString();
}

function id() {
  return crypto.randomUUID();
}

function cleanOptionalString(value) {
  if (value === undefined || value === null) return undefined;
  const cleaned = String(value).trim();
  return cleaned || undefined;
}

function messageId(data) {
  const clientMessageId = cleanOptionalString(data.clientMessageId);
  if (!clientMessageId) return data._id || id();

  const scope = data.group
    ? `group:${String(data.group)}`
    : `direct:${String(data.sender)}:${String(data.receiver)}`;
  const digest = crypto
    .createHash("sha256")
    .update(`${String(data.sender)}|${scope}|${clientMessageId}`)
    .digest("hex")
    .slice(0, 32);
  return `client-message-${digest}`;
}

function cloneWithoutPassword(user) {
  if (!user) return null;
  const { password: _password, ...safeUser } = user;
  return safeUser;
}

function userIdentityKey(user) {
  return String(user?.appUserId || user?.email || user?._id || "")
    .normalize("NFC")
    .toLowerCase();
}

function userQualityScore(user) {
  let score = 0;
  if (user?.appUserId) score += 8;
  if (user?.email) score += 4;
  if (user?.displayName) score += 2;
  if (user?.updatedAt) score += 1;
  return score;
}

function canonicalUser(users) {
  return (
    users.filter(Boolean).sort((left, right) => {
      const scoreDelta = userQualityScore(right) - userQualityScore(left);
      if (scoreDelta !== 0) return scoreDelta;
      return String(right.updatedAt || right.createdAt || "").localeCompare(
        String(left.updatedAt || left.createdAt || ""),
      );
    })[0] || null
  );
}

function canonicalUsers(users) {
  const byIdentity = new Map();
  users.forEach((user) => {
    const key = userIdentityKey(user);
    if (!key) return;
    const current = byIdentity.get(key);
    byIdentity.set(key, canonicalUser([current, user]));
  });
  return [...byIdentity.values()].filter(Boolean);
}

function normalizeList(value) {
  return Array.isArray(value) ? value.map(String) : [];
}

function normalizeAttachments(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((attachment) => attachment && attachment.url)
    .map((attachment) => ({
      name: cleanOptionalString(attachment.name) || "attachment",
      contentType: cleanOptionalString(
        attachment.contentType || attachment.type,
      ),
      size: Number(attachment.size || 0),
      url: attachment.url,
      s3Key: cleanOptionalString(attachment.s3Key),
      storage: cleanOptionalString(attachment.storage),
    }));
}

function byCreatedAtAsc(a, b) {
  return (
    new Date(a.createdAt || a.timestamp || 0) -
    new Date(b.createdAt || b.timestamp || 0)
  );
}

function byUpdatedAtDesc(a, b) {
  return (
    new Date(b.updatedAt || b.createdAt || 0) -
    new Date(a.updatedAt || a.createdAt || 0)
  );
}

function createOnlyOptions() {
  return {
    ConditionExpression: "attribute_not_exists(#id)",
    ExpressionAttributeNames: {
      "#id": "_id",
    },
  };
}

function buildPatchExpression(patch) {
  const entries = Object.entries(patch).filter(
    ([, value]) => value !== undefined,
  );
  if (entries.length === 0) return null;

  const ExpressionAttributeNames = {
    "#id": "_id",
  };
  const ExpressionAttributeValues = {};
  const setters = entries.map(([field, value], index) => {
    const nameKey = `#field${index}`;
    const valueKey = `:value${index}`;
    ExpressionAttributeNames[nameKey] = field;
    ExpressionAttributeValues[valueKey] = value;
    return `${nameKey} = ${valueKey}`;
  });

  return {
    UpdateExpression: `SET ${setters.join(", ")}`,
    ConditionExpression: "attribute_exists(#id)",
    ExpressionAttributeNames,
    ExpressionAttributeValues,
  };
}

async function patchItem(TableName, itemId, patch, operation) {
  const expression = buildPatchExpression(patch);
  if (!expression) return getItem(TableName, String(itemId));

  try {
    return await updateItem(TableName, String(itemId), expression);
  } catch (error) {
    if (isConditionalCheckFailed(error)) {
      dynamodbConditionalFailureTotal.labels(operation).inc();
      return null;
    }
    throw error;
  }
}

async function appendUniqueListValue(
  TableName,
  itemId,
  attribute,
  value,
  operation,
) {
  try {
    return await updateItem(TableName, String(itemId), {
      UpdateExpression:
        "SET #attribute = list_append(if_not_exists(#attribute, :emptyList), :values), " +
        "#updatedAt = :updatedAt",
      ConditionExpression:
        "attribute_exists(#id) AND (attribute_not_exists(#attribute) OR " +
        "NOT contains(#attribute, :value))",
      ExpressionAttributeNames: {
        "#id": "_id",
        "#attribute": attribute,
        "#updatedAt": "updatedAt",
      },
      ExpressionAttributeValues: {
        ":emptyList": [],
        ":values": [String(value)],
        ":value": String(value),
        ":updatedAt": now(),
      },
    });
  } catch (error) {
    if (isConditionalCheckFailed(error)) {
      dynamodbConditionalFailureTotal.labels(operation).inc();
      return null;
    }
    throw error;
  }
}

export const usersRepo = {
  async create(data) {
    const timestamp = now();
    const user = {
      _id: data._id || id(),
      appUserId: data.appUserId,
      username: data.username,
      displayName: data.displayName || data.username,
      email: data.email,
      password: data.password,
      profilePicture: data.profilePicture,
      bio: data.bio || "",
      createdAt: data.createdAt || timestamp,
      updatedAt: timestamp,
    };
    return putItem(CHAT_TABLES.users, user, createOnlyOptions());
  },

  async getById(userId) {
    return getItem(CHAT_TABLES.users, String(userId));
  },

  async getSafeById(userId) {
    return cloneWithoutPassword(await this.getById(userId));
  },

  async list() {
    return canonicalUsers(await scanAll(CHAT_TABLES.users));
  },

  async listExcept(userId) {
    const users = await this.list();
    return users
      .filter((user) => user._id !== String(userId))
      .map(cloneWithoutPassword);
  },

  async findByEmail(email) {
    if (!email) return null;
    const users = await scanAll(CHAT_TABLES.users);
    return canonicalUser(users.filter((user) => user.email === email));
  },

  async findByAppUserId(appUserId) {
    if (!appUserId) return null;
    const users = await scanAll(CHAT_TABLES.users);
    return canonicalUser(users.filter((user) => user.appUserId === appUserId));
  },

  async findByEmailOrUsername(email, username) {
    const users = await scanAll(CHAT_TABLES.users);
    return canonicalUser(
      users.filter(
        (user) => user.email === email || user.username === username,
      ),
    );
  },

  async findByAppUserIdOrEmail(appUserId, email) {
    const users = await scanAll(CHAT_TABLES.users);
    return canonicalUser(
      users.filter(
        (user) =>
          (appUserId && user.appUserId === appUserId) ||
          (email && user.email === email),
      ),
    );
  },

  async existsByUsername(username) {
    const users = await this.list();
    return users.some((user) => user.username === username);
  },

  async update(userId, patch) {
    return patchItem(
      CHAT_TABLES.users,
      userId,
      {
        ...patch,
        updatedAt: now(),
      },
      "user_update",
    );
  },

  async delete(userId) {
    await deleteItem(CHAT_TABLES.users, String(userId));
  },
};

export const messagesRepo = {
  async create(data) {
    if ((data.receiver && data.group) || (!data.receiver && !data.group)) {
      throw new Error(
        "Message must have either receiver or group, not both or neither",
      );
    }
    const timestamp = now();
    const message = {
      _id: messageId(data),
      sender: String(data.sender),
      receiver: data.receiver ? String(data.receiver) : undefined,
      group: data.group ? String(data.group) : undefined,
      clientMessageId: cleanOptionalString(data.clientMessageId),
      text: data.text || "",
      image: data.image,
      attachments: normalizeAttachments(data.attachments),
      seen: data.seen ?? false,
      seenBy: normalizeList(data.seenBy),
      edited: data.edited ?? false,
      editedAt: data.editedAt,
      timestamp: data.timestamp || timestamp,
      createdAt: data.createdAt || timestamp,
      updatedAt: timestamp,
    };
    try {
      return await putItem(CHAT_TABLES.messages, message, createOnlyOptions());
    } catch (error) {
      if (isConditionalCheckFailed(error)) {
        dynamodbConditionalFailureTotal.labels("message_create").inc();
        const existing = await this.getById(message._id);
        if (message.clientMessageId && existing) {
          idempotencyReplayTotal.labels("message_create").inc();
          return { ...existing, idempotencyReplay: true };
        }
      }
      throw error;
    }
  },

  async getById(messageId) {
    return getItem(CHAT_TABLES.messages, String(messageId));
  },

  async list() {
    return scanAll(CHAT_TABLES.messages);
  },

  async listDirectBetween(userA, userB) {
    const first = String(userA);
    const second = String(userB);
    const messages = await this.list();
    return messages
      .filter(
        (message) =>
          (message.sender === first && message.receiver === second) ||
          (message.sender === second && message.receiver === first),
      )
      .sort(byCreatedAtAsc);
  },

  async listGroup(groupId) {
    const messages = await this.list();
    return messages
      .filter((message) => message.group === String(groupId))
      .sort(byCreatedAtAsc);
  },

  async countUnreadFromSender(senderId, receiverId) {
    const messages = await this.list();
    return messages.filter(
      (message) =>
        message.sender === String(senderId) &&
        message.receiver === String(receiverId) &&
        !message.seen,
    ).length;
  },

  async markDirectSeen(senderId, receiverId) {
    const messages = await this.list();
    const targets = messages.filter(
      (message) =>
        message.sender === String(senderId) &&
        message.receiver === String(receiverId) &&
        !message.seen,
    );
    await Promise.all(
      targets.map((message) =>
        patchItem(
          CHAT_TABLES.messages,
          message._id,
          {
            seen: true,
            updatedAt: now(),
          },
          "direct_seen",
        ),
      ),
    );
  },

  async markGroupSeen(groupId, userId) {
    const messages = await this.listGroup(groupId);
    const targets = messages.filter(
      (message) =>
        message.sender !== String(userId) &&
        !normalizeList(message.seenBy).includes(String(userId)),
    );
    await Promise.all(
      targets.map((message) =>
        appendUniqueListValue(
          CHAT_TABLES.messages,
          message._id,
          "seenBy",
          userId,
          "group_seen",
        ),
      ),
    );
  },

  async update(messageId, patch) {
    return patchItem(
      CHAT_TABLES.messages,
      messageId,
      {
        ...patch,
        updatedAt: now(),
      },
      "message_update",
    );
  },

  async delete(messageId) {
    await deleteItem(CHAT_TABLES.messages, String(messageId));
  },

  async deleteByGroup(groupId) {
    const messages = await this.listGroup(groupId);
    await Promise.all(messages.map((message) => this.delete(message._id)));
  },
};

export const groupsRepo = {
  async create(data) {
    const timestamp = now();
    const group = {
      _id: data._id || id(),
      name: data.name,
      description: data.description || "",
      avatar: data.avatar || "",
      creator: String(data.creator),
      members: normalizeList(data.members),
      admins: normalizeList(data.admins),
      lastMessage: data.lastMessage,
      createdAt: data.createdAt || timestamp,
      updatedAt: timestamp,
    };
    return putItem(CHAT_TABLES.groups, group, createOnlyOptions());
  },

  async getById(groupId) {
    return getItem(CHAT_TABLES.groups, String(groupId));
  },

  async list() {
    return scanAll(CHAT_TABLES.groups);
  },

  async listForMember(userId) {
    const groups = await this.list();
    return groups
      .filter((group) => normalizeList(group.members).includes(String(userId)))
      .sort(byUpdatedAtDesc);
  },

  async update(groupId, patch) {
    return patchItem(
      CHAT_TABLES.groups,
      groupId,
      {
        ...patch,
        updatedAt: now(),
      },
      "group_update",
    );
  },

  async addMember(groupId, userId) {
    return appendUniqueListValue(
      CHAT_TABLES.groups,
      groupId,
      "members",
      userId,
      "group_add_member",
    );
  },

  async delete(groupId) {
    await deleteItem(CHAT_TABLES.groups, String(groupId));
  },
};

export async function populateUser(userId) {
  return usersRepo.getSafeById(userId);
}

export async function populateMembers(memberIds) {
  const users = await Promise.all(
    normalizeList(memberIds).map((memberId) => usersRepo.getSafeById(memberId)),
  );
  return users.filter(Boolean);
}

export async function populateGroup(group) {
  if (!group) return null;
  const [members, creator, lastMessage] = await Promise.all([
    populateMembers(group.members),
    usersRepo.getSafeById(group.creator),
    group.lastMessage
      ? messagesRepo.getById(group.lastMessage)
      : Promise.resolve(null),
  ]);
  return { ...group, members, creator, lastMessage };
}

export async function populateMessageSender(message) {
  if (!message) return null;
  const sender = await usersRepo.getSafeById(message.sender);
  return { ...message, sender: sender || message.sender };
}

export function safeUser(user) {
  return cloneWithoutPassword(user);
}
