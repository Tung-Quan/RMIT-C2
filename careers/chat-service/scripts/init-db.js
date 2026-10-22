import "../lib/env.js";
import { CHAT_TABLES, ensureDynamoDB } from "../lib/dynamo.js";

try {
  await ensureDynamoDB();
  console.log(
    `Chat DynamoDB init complete: ${Object.values(CHAT_TABLES).join(", ")}`,
  );
} catch (error) {
  console.error("Chat DynamoDB init failed:", error?.message || error);
  process.exitCode = 1;
}
