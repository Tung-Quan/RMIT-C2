import { beforeEach, describe, expect, it, vi } from "vitest";

const dynamoMock = vi.hoisted(() => {
  const tables = new Map();
  const CHAT_TABLES = {
    users: "ChatUsers",
    groups: "ChatGroups",
    messages: "ChatMessages",
  };

  function table(name) {
    if (!tables.has(name)) tables.set(name, new Map());
    return tables.get(name);
  }

  function clone(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  function conditionalError() {
    const error = new Error("conditional failed");
    error.name = "ConditionalCheckFailedException";
    return error;
  }

  function applySetExpression(item, update) {
    const names = update.ExpressionAttributeNames || {};
    const values = update.ExpressionAttributeValues || {};

    if (update.UpdateExpression.includes("list_append")) {
      const attribute = names["#attribute"];
      const value = values[":value"];
      const current = Array.isArray(item[attribute]) ? item[attribute] : [];
      if (current.map(String).includes(String(value))) {
        throw conditionalError();
      }
      item[attribute] = [...current, ...values[":values"]];
      item.updatedAt = values[":updatedAt"];
      return item;
    }

    for (const assignment of update.UpdateExpression.replace(
      /^SET\s+/,
      "",
    ).split(",")) {
      const [nameKey, valueKey] = assignment.trim().split(/\s*=\s*/);
      item[names[nameKey]] = values[valueKey];
    }
    return item;
  }

  return {
    CHAT_TABLES,
    __resetDynamoMock() {
      tables.clear();
    },
    async getItem(TableName, _id) {
      return clone(table(TableName).get(String(_id))) || null;
    },
    async putItem(TableName, Item, options = {}) {
      const currentTable = table(TableName);
      if (
        options.ConditionExpression?.includes("attribute_not_exists") &&
        currentTable.has(String(Item._id))
      ) {
        throw conditionalError();
      }
      currentTable.set(String(Item._id), clone(Item));
      return clone(Item);
    },
    async updateItem(TableName, _id, update) {
      const currentTable = table(TableName);
      const item = clone(currentTable.get(String(_id)));
      if (!item) throw conditionalError();
      const updated = applySetExpression(item, update);
      currentTable.set(String(_id), clone(updated));
      return clone(updated);
    },
    async deleteItem(TableName, _id) {
      table(TableName).delete(String(_id));
    },
    async scanAll(TableName) {
      return [...table(TableName).values()].map(clone);
    },
    isConditionalCheckFailed(error) {
      return error?.name === "ConditionalCheckFailedException";
    },
  };
});

const metricMock = vi.hoisted(() => ({
  inc: vi.fn(),
}));

vi.mock("../lib/dynamo.js", () => dynamoMock);
vi.mock("../src/metrics.js", () => ({
  dynamodbConditionalFailureTotal: {
    labels: () => metricMock,
  },
  idempotencyReplayTotal: {
    labels: () => metricMock,
  },
}));

const { __resetDynamoMock, scanAll, CHAT_TABLES } =
  await import("../lib/dynamo.js");
const { groupsRepo, messagesRepo } =
  await import("../repositories/chatRepository.js");

describe("chat repository concurrency policy", () => {
  beforeEach(() => {
    __resetDynamoMock();
    metricMock.inc.mockClear();
  });

  it("replays duplicate clientMessageId creates without storing a second message", async () => {
    const first = await messagesRepo.create({
      sender: "candidate-1",
      receiver: "hr-1",
      text: "Hello",
      clientMessageId: "local-123",
    });

    const replay = await messagesRepo.create({
      sender: "candidate-1",
      receiver: "hr-1",
      text: "Hello",
      clientMessageId: "local-123",
    });

    const messages = await scanAll(CHAT_TABLES.messages);
    expect(replay._id).toBe(first._id);
    expect(replay.idempotencyReplay).toBe(true);
    expect(messages).toHaveLength(1);
  });

  it("atomically appends different group members without overwriting prior members", async () => {
    const group = await groupsRepo.create({
      name: "Backend Review",
      creator: "hr-1",
      members: ["hr-1"],
      admins: ["hr-1"],
    });

    await Promise.all([
      groupsRepo.addMember(group._id, "candidate-1"),
      groupsRepo.addMember(group._id, "candidate-2"),
    ]);

    const [updated] = await scanAll(CHAT_TABLES.groups);
    expect(updated.members).toEqual(["hr-1", "candidate-1", "candidate-2"]);
  });

  it("does not duplicate group read markers when the same user is marked twice", async () => {
    await messagesRepo.create({
      sender: "candidate-1",
      group: "group-1",
      text: "Status update",
      seenBy: [],
    });

    await Promise.all([
      messagesRepo.markGroupSeen("group-1", "hr-1"),
      messagesRepo.markGroupSeen("group-1", "hr-1"),
    ]);

    const [message] = await scanAll(CHAT_TABLES.messages);
    expect(message.seenBy).toEqual(["hr-1"]);
  });

  it("stores attachment metadata with a message without affecting idempotency", async () => {
    await messagesRepo.create({
      sender: "candidate-1",
      receiver: "hr-1",
      text: "",
      attachments: [
        {
          name: "portfolio.pdf",
          contentType: "application/pdf",
          size: 1024,
          url: "https://cdn.example.test/chat/portfolio.pdf",
          s3Key: "chat/messages/candidate-1/portfolio.pdf",
        },
      ],
      clientMessageId: "attachment-123",
    });

    const [message] = await scanAll(CHAT_TABLES.messages);
    expect(message.attachments).toEqual([
      {
        name: "portfolio.pdf",
        contentType: "application/pdf",
        size: 1024,
        url: "https://cdn.example.test/chat/portfolio.pdf",
        s3Key: "chat/messages/candidate-1/portfolio.pdf",
      },
    ]);
  });
});
