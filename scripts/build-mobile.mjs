import { cp, mkdir, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const localEnvPath = resolve(root, ".env.capacitor.local");
const localEnv = existsSync(localEnvPath)
  ? dotenv.parse(await readFile(localEnvPath))
  : {};
const apiBaseUrl = process.env.VITE_API_BASE_URL || localEnv.VITE_API_BASE_URL;

if (!apiBaseUrl) {
  throw new Error(
    "Set VITE_API_BASE_URL in .env.capacitor.local before building the mobile bundle. See .env.capacitor.example.",
  );
}
const apiUrl = new URL(apiBaseUrl);
if (!["http:", "https:"].includes(apiUrl.protocol))
  throw new Error("VITE_API_BASE_URL must use http:// or https://.");

const env = { ...process.env, VITE_API_BASE_URL: apiUrl.origin };
const commands = [
  {
    cwd: root,
    executable: resolve(root, "node_modules/vite/bin/vite.js"),
    args: ["build", "--mode", "capacitor"],
  },
  {
    cwd: resolve(root, "careers/frontend"),
    executable: resolve(
      root,
      "careers/frontend/node_modules/vite/bin/vite.js",
    ),
    args: ["build", "--mode", "capacitor"],
  },
];

for (const command of commands) {
  if (!existsSync(command.executable))
    throw new Error(
      "Vite is not installed for both FairEnrol apps. Run npm.cmd run careers:install.",
    );
  const result = spawnSync(process.execPath, [command.executable, ...command.args], {
    cwd: command.cwd,
    env,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0)
    process.exit(result.status ?? 1);
}

const careersBuild = resolve(root, "careers/frontend/dist");
const mobileCareersBuild = resolve(root, "dist/careers");
await mkdir(mobileCareersBuild, { recursive: true });
await cp(careersBuild, mobileCareersBuild, { recursive: true, force: true });
console.log("FairEnrol mobile bundle staged in dist/ (including /careers/).");
