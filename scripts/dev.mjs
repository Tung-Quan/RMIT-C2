import { spawn } from "node:child_process";
import { resolve } from "node:path";

const root = process.cwd();
const services = [
  {
    name: "FairEnrol API",
    cwd: root,
    entry: resolve(root, "server/index.js"),
    args: ["--watch"],
  },
  {
    name: "FairEnrol Web",
    cwd: root,
    entry: resolve(root, "node_modules/vite/bin/vite.js"),
    args: [],
  },
  {
    name: "Careers Web",
    cwd: resolve(root, "careers/frontend"),
    entry: resolve(root, "careers/frontend/node_modules/vite/bin/vite.js"),
    args: [],
  },
];
const children = services.map(({ name, cwd, entry, args }) => {
  const child = spawn(process.execPath, [entry, ...args], {
    cwd,
    stdio: "inherit",
    env: process.env,
  });
  child.on("error", (error) => {
    console.error(`${name} could not start: ${error.message}`);
    process.exitCode = 1;
    close();
  });
  child.on("exit", (code) => {
    if (!closing) {
      process.exitCode = code || 0;
      close();
    }
  });
  return child;
});

let closing = false;
function close() {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill();
}
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, close);
