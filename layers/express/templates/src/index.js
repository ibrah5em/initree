const express = require("express");

const app = express();
const port = ${app.port};

app.get("${app.healthcheck_path}", (req, res) => {
  res.json({ status: "ok" });
});

app.get("/", (req, res) => {
  res.json({ service: "${project.slug}" });
});

if (require.main === module) {
  app.listen(port, () => console.log("listening on port " + port));
}

module.exports = app;
