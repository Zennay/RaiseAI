import http from "node:http";
import { createHandler } from "./app.mjs";

const host = process.env.RAISE_HOST ?? "127.0.0.1";
const port = Number(process.env.RAISE_PORT ?? "8787");
const token = process.env.RAISE_GATEWAY_TOKEN ?? "";

const server = http.createServer(createHandler({ token }));
server.requestTimeout = 10_000;
server.headersTimeout = 5_000;
server.keepAliveTimeout = 5_000;

server.listen(port, host, () => {
  console.log(JSON.stringify({ event: "raise_gateway_started", host, port }));
});
