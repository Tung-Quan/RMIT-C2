import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const sourceRoot = join(process.cwd(), "src");
const scriptRoot = join(process.cwd(), "scripts");
const deprecatedRouteFragments = [
  [["/hr/", "jobs/"].join(""), ["/st", "atus"].join("")],
  [["/hr/", "applications/"].join(""), ["/st", "atus"].join("")],
  ["api.patch(", "/candidate/job-applications/", "/withdraw"],
  ["api.delete(`", "/hr/jobs/"],
  [["update", "HrJob", "Status"].join("")],
  [["update", "HrApplication", "Status"].join("")],
  [["withdraw", "Candidate", "JobApplication"].join("")]
];

const files = [...walk(sourceRoot), ...walk(scriptRoot)];
const failures = [];

for (const file of files) {
  if (file.endsWith(".js") || file.endsWith(".mjs")) {
    try {
      execFileSync(process.execPath, ["--check", file], { stdio: "pipe" });
    } catch (error) {
      failures.push(`${file}: JavaScript syntax check failed\n${error.stderr || error.message}`);
    }
  }

  if (file.includes("workflowCommands.test.mjs") || file.includes("lint-source.mjs")) continue;
  const text = readFileSync(file, "utf8");
  for (const fragments of deprecatedRouteFragments) {
    if (fragments.every((fragment) => text.includes(fragment))) {
      failures.push(`${file}: deprecated workflow route usage`);
    }
  }
}

if (failures.length > 0) {
  console.error(failures.join("\n\n"));
  process.exit(1);
}

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}
