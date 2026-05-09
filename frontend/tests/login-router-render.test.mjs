// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const loginPageSource = readFileSync(
  new URL("../src/app/login/page.tsx", import.meta.url),
  "utf8"
);

test("LoginPage redirects authenticated users from an effect, not render", () => {
  assert.equal(
    /if\s*\(\s*dbUser\s*\)\s*{\s*router\.push\(/s.test(loginPageSource),
    false,
    "router.push during render triggers React's setState-in-render warning"
  );

  assert.match(
    loginPageSource,
    /useEffect\s*\(\s*\(\)\s*=>\s*{\s*if\s*\(\s*!dbUser\s*\)\s*return;\s*router\.push\(getRedirect\(dbUser\)\);/s
  );
});
