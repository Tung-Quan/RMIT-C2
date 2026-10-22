import dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const serviceRoot = path.resolve(path.dirname(__filename), "..");
const workspaceRoot = path.resolve(serviceRoot, "..");

dotenv.config({ path: path.join(workspaceRoot, ".env"), quiet: true });
dotenv.config({
  path: path.join(serviceRoot, ".env"),
  override: true,
  quiet: true,
});
