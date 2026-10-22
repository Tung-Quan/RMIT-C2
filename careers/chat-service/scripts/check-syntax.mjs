import { readdir } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";

const serviceRoot = path.resolve(import.meta.dirname, "..");
const ignoredDirectories = new Set([
  "coverage",
  "dist",
  "logs",
  "node_modules",
]);
const checkedExtensions = new Set([".js", ".mjs"]);

async function collectJavaScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        files.push(...(await collectJavaScriptFiles(absolutePath)));
      }
      continue;
    }

    if (entry.isFile() && checkedExtensions.has(path.extname(entry.name))) {
      files.push(absolutePath);
    }
  }

  return files.sort();
}

function checkSyntax(file) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--check", file], {
      cwd: serviceRoot,
      stdio: "inherit",
    });

    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(
        new Error(
          `node --check failed for ${path.relative(serviceRoot, file)}`,
        ),
      );
    });
  });
}

const files = await collectJavaScriptFiles(serviceRoot);

for (const file of files) {
  await checkSyntax(file);
}

console.log(`Syntax check passed for ${files.length} JavaScript files.`);
