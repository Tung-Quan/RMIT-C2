import {
  CreateTableCommand,
  DescribeTableCommand,
  DynamoDBClient,
  ListTablesCommand,
  ResourceInUseException,
  ResourceNotFoundException,
} from "@aws-sdk/client-dynamodb";
import {
  DeleteCommand,
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  ScanCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import "./env.js";

export const CHAT_TABLES = {
  users: process.env.DYNAMODB_USERS_TABLE || "ChatUsers",
  groups: process.env.DYNAMODB_GROUPS_TABLE || "ChatGroups",
  messages: process.env.DYNAMODB_MESSAGES_TABLE || "ChatMessages",
};

const endpoint = process.env.DYNAMODB_ENDPOINT || "";
const region =
  process.env.AWS_REGION || process.env.DYNAMODB_REGION || "us-east-1";
const hasStaticCredentials =
  Boolean(process.env.AWS_ACCESS_KEY_ID) &&
  Boolean(process.env.AWS_SECRET_ACCESS_KEY);

const clientConfig = {
  region,
};

if (endpoint) {
  clientConfig.endpoint = endpoint;
}

if (hasStaticCredentials) {
  clientConfig.credentials = {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  };
} else if (endpoint) {
  clientConfig.credentials = {
    accessKeyId: "local",
    secretAccessKey: "local",
  };
}

export const dynamoClient = new DynamoDBClient(clientConfig);

export const dynamo = DynamoDBDocumentClient.from(dynamoClient, {
  marshallOptions: {
    convertClassInstanceToMap: true,
    removeUndefinedValues: true,
  },
});

function keySchema() {
  return {
    KeySchema: [{ AttributeName: "_id", KeyType: "HASH" }],
    AttributeDefinitions: [{ AttributeName: "_id", AttributeType: "S" }],
    BillingMode: "PAY_PER_REQUEST",
  };
}

async function tableExists(TableName) {
  try {
    await dynamoClient.send(new DescribeTableCommand({ TableName }));
    return true;
  } catch (error) {
    if (
      error instanceof ResourceNotFoundException ||
      error?.name === "ResourceNotFoundException"
    )
      return false;
    throw error;
  }
}

async function ensureTable(TableName) {
  if (await tableExists(TableName)) {
    await waitForActiveTable(TableName);
    return;
  }

  try {
    await dynamoClient.send(
      new CreateTableCommand({ TableName, ...keySchema() }),
    );
  } catch (error) {
    if (
      !(error instanceof ResourceInUseException) &&
      error?.name !== "ResourceInUseException"
    ) {
      throw error;
    }
  }
  await waitForActiveTable(TableName);
}

async function waitForActiveTable(TableName) {
  const maxAttempts = Number(process.env.DYNAMODB_TABLE_READY_ATTEMPTS || 20);
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const result = await dynamoClient.send(
      new DescribeTableCommand({ TableName }),
    );
    if (result.Table?.TableStatus === "ACTIVE") return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`DynamoDB table ${TableName} was not ACTIVE in time`);
}

export async function ensureDynamoDB() {
  await Promise.all(
    Object.values(CHAT_TABLES).map((tableName) => ensureTable(tableName)),
  );
  const result = await dynamoClient.send(new ListTablesCommand({}));
  console.log(`DynamoDB connected at ${endpoint || `AWS region ${region}`}`);
  console.log(
    `DynamoDB chat tables ready: ${Object.values(CHAT_TABLES).join(", ")}`,
  );
  return result.TableNames || [];
}

export async function getItem(TableName, _id) {
  const result = await dynamo.send(new GetCommand({ TableName, Key: { _id } }));
  return result.Item || null;
}

export function isConditionalCheckFailed(error) {
  return error?.name === "ConditionalCheckFailedException";
}

export async function putItem(TableName, Item, options = {}) {
  await dynamo.send(new PutCommand({ TableName, Item, ...options }));
  return Item;
}

export async function updateItem(TableName, _id, update, options = {}) {
  const result = await dynamo.send(
    new UpdateCommand({
      TableName,
      Key: { _id: String(_id) },
      ReturnValues: "ALL_NEW",
      ...update,
      ...options,
    }),
  );
  return result.Attributes || null;
}

export async function deleteItem(TableName, _id) {
  await dynamo.send(new DeleteCommand({ TableName, Key: { _id } }));
}

export async function scanAll(TableName) {
  const items = [];
  let ExclusiveStartKey;

  do {
    const result = await dynamo.send(
      new ScanCommand({ TableName, ExclusiveStartKey }),
    );
    items.push(...(result.Items || []));
    ExclusiveStartKey = result.LastEvaluatedKey;
  } while (ExclusiveStartKey);

  return items;
}
