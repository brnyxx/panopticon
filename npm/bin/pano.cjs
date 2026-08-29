#!/usr/bin/env node
"use strict";

const childProcess = require("node:child_process");
const path = require("node:path");

const PAYLOADS = Object.freeze({
  "linux:x64": "@brnyxx/panopticon-linux-x64-gnu",
  "linux:arm64": "@brnyxx/panopticon-linux-arm64-gnu",
  "darwin:x64": "@brnyxx/panopticon-darwin-x64",
  "darwin:arm64": "@brnyxx/panopticon-darwin-arm64",
});

const key = `${process.platform}:${process.arch}`;
const packageName = PAYLOADS[key];
if (!packageName) {
  process.stderr.write(
    `panopticon does not provide a native package for ${process.platform}/${process.arch}.\n`,
  );
  process.exitCode = 1;
} else {
  let binary;
  try {
    binary = path.join(path.dirname(require.resolve(`${packageName}/package.json`)), "bin", "pano");
  } catch (error) {
    process.stderr.write(`panopticon native package ${packageName} is not installed.\n`);
    process.exitCode = 1;
  }

  if (binary) {
    const child = childProcess.spawn(binary, process.argv.slice(2), {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      stdio: "inherit",
    });
    child.on("error", (error) => {
      process.stderr.write(`panopticon could not start ${packageName}: ${error.message}\n`);
      process.exitCode = 1;
    });
    child.on("exit", (code, signal) => {
      if (signal) {
        process.kill(process.pid, signal);
      } else {
        process.exitCode = code === null ? 1 : code;
      }
    });
  }
}
