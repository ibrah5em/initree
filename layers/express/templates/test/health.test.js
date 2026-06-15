const test = require("node:test");
const assert = require("node:assert");

const app = require("../src/index.js");

test("health endpoint reports ok", async () => {
  const server = app.listen(0);
  const { port } = server.address();
  try {
    const response = await fetch("http://127.0.0.1:" + port + "${app.healthcheck_path}");
    assert.strictEqual(response.status, 200);
    assert.deepStrictEqual(await response.json(), { status: "ok" });
  } finally {
    server.close();
  }
});
