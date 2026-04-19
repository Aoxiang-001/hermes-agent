import test from "node:test";
import assert from "node:assert/strict";

import { parseBridgeConfig } from "../src/config.mjs";

test("parseBridgeConfig preserves dashes in shorthand token tail", () => {
  const config = parseBridgeConfig({
    nim_token: "app-account-token-with-dashes",
  });

  assert.deepEqual(config.credentials, {
    appKey: "app",
    account: "account",
    token: "token-with-dashes",
  });
});
