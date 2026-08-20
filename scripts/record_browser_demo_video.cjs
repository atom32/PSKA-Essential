#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

function main() {
  console.error(
    [
      "Legacy PSKA diagnostic-page browser demo recording is disabled.",
      "PSKA has no independent product frontend; use Hermes WebUI extension demo instead:",
      "  node scripts/record_hermes_pska_extension_demo.cjs",
    ].join("\n"),
  );
  process.exitCode = 1;
}

main();
