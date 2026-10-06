import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import { createHandler } from "./app.mjs";
import { parseDeployRevision, parseServerPort, validateServerConfig } from "./server-policy.mjs";
import { createZCloudExecutor } from "./connectors/zcloud.mjs";
import { createOpenRouterExecutor } from "./providers/openrouter.mjs";

const host = process.env.RAISE_HOST ?? "127.0.0.1";
const port = parseServerPort(process.env.RAISE_PORT);
const token = process.env.RAISE_GATEWAY_TOKEN ?? "";
const tlsCert = process.env.RAISE_TLS_CERT ?? "";
const tlsKey = process.env.RAISE_TLS_KEY ?? "";
const revision = parseDeployRevision(process.env.RAISE_DEPLOY_REVISION);

validateServerConfig({ host, port, tlsCert, tlsKey });

const executeZCloud = createZCloudExecutor({
  baseUrl: process.env.RAISE_ZCLOUD_URL ?? "http://127.0.0.1:8765"
});

const executeOpenRouter = createOpenRouterExecutor({
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
  fastModel: process.env.RAISE_OPENROUTER_FAST_MODEL ?? "z-ai/glm-5.3-flash",
  deepModel: process.env.RAISE_OPENROUTER_DEEP_MODEL ?? "z-ai/glm-5.3-flash",
  fallbackModels:
    process.env.RAISE_OPENROUTER_FALLBACK_MODELS ?? "google/gemini-3.8-flash",
  allowWebSearch: process.env.RAISE_ENABLE_WEB_SEARCH === "1"
});

const execute = async (decision, text) =>
  (await executeZCloud(decision, text)) ??
  (await executeOpenRouter(decision, text));

const handler = createHandler({ token, execute, revision });
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
    tls: Boolean(tlsCert),
    revision
  }));
});
