import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import { createHandler } from "./app.mjs";
import { createOpenAIExecutor } from "./providers/openai.mjs";

const host = process.env.RAISE_HOST ?? "127.0.0.1";
const port = Number(process.env.RAISE_PORT ?? "8787");
const token = process.env.RAISE_GATEWAY_TOKEN ?? "";
const tlsCert = process.env.RAISE_TLS_CERT ?? "";
const tlsKey = process.env.RAISE_TLS_KEY ?? "";

if (Boolean(tlsCert) !== Boolean(tlsKey)) {
  throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must be set together");
}

const execute = createOpenAIExecutor({
  apiKey: process.env.OPENAI_API_KEY ?? "",
  fastModel: process.env.RAISE_OPENAI_FAST_MODEL ?? "gpt-5.4-nano",
  deepModel: process.env.RAISE_OPENAI_DEEP_MODEL ?? "gpt-5.4-mini",
  allowWebSearch: process.env.RAISE_ENABLE_WEB_SEARCH === "1"
});

const handler = createHandler({ token, execute });
const server = tlsCert
  ? https.createServer({
      cert: fs.readFileSync(tlsCert),
      key: fs.readFileSync(tlsKey),
      minVersion: "TLSv1.2"
    }, handler)
  : http.createServer(handler);

server.requestTimeout = 10_000;
server.headersTimeout = 5_000;
server.keepAliveTimeout = 5_000;

server.listen(port, host, () => {
  console.log(JSON.stringify({
    event: "raise_gateway_started",
    host,
    port,
    tls: Boolean(tlsCert)
  }));
});