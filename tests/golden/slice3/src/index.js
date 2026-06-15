const express = require("express");

const app = express();
const port = 3000;

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.get("/", (req, res) => {
  res.json({ service: "myapp" });
});

if (require.main === module) {
  app.listen(port, () => console.log("listening on port " + port));
}

module.exports = app;
