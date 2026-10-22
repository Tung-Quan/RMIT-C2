import { spawn } from "node:child_process";
const children = [
  spawn(process.execPath, ["--watch", "server/index.js"], { stdio: "inherit" }),
  spawn(process.execPath, ["node_modules/vite/bin/vite.js"], {
    stdio: "inherit",
  }),
];
let closing = false;
const close = () => {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill();
};
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, close);
for (const child of children)
  child.on("exit", (code) => {
    if (!closing) {
      process.exitCode = code || 0;
      close();
    }
  });
