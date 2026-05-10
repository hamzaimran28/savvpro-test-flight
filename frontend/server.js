"use strict";

const path = require("path");
const express = require("express");

const PORT = Number(process.env.PORT) || 3000;
const app = express();

const publicDir = path.join(__dirname, "public");
app.use(express.static(publicDir));

app.listen(PORT, () => {
  console.log(`FlightHub UI at http://127.0.0.1:${PORT}`);
  console.log("Ensure the FastAPI backend is running (default http://127.0.0.1:8000).");
});
