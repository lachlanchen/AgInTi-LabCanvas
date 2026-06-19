#!/usr/bin/env node
"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const env = {
  ...process.env,
  PYTHONPATH: [path.join(root, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};
const python = process.env.LABCANVAS_PYTHON || process.env.PYTHON || (process.platform === "win32" ? "python.exe" : "python3");
const result = spawnSync(python, ["-m", "unittest", "discover", "-s", "tests"], {
  cwd: root,
  env,
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 0);
