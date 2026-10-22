import { ensureDynamoDB } from "./dynamo.js";
import { dependencyUp } from "../src/metrics.js";

export const connectDB = async () => {
  try {
    await ensureDynamoDB();
    dependencyUp.labels("dynamodb").set(1);
  } catch (error) {
    dependencyUp.labels("dynamodb").set(0);
    console.error("Error connecting to DynamoDB:", error?.message || error);
    throw error;
  }
};
