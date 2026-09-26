import http from "node:http";
import { createHandler } from "./app.mjs";
import { createOpenAIExecutor } from "./providers/openai.mjs";

const host = process.env.RAISE_HOST ?? "127.0.0.1";
const port = Number(process.env.RAISE_PORT ?? "8787");
const token = process.env.RAISE_GATEWAY_TOKEN ?? "";

const execute = createOpenAIExecutor({
  apiKey: process.env.OPENAI_API_KEY ?? "",
  fastModel: process.env.RAISE_OPENAI_FAST_MODEL ?? "gpt-5.4-nano",
  deepModel: process.env.RAISE_OPENAI_DEEP_MODEL ?? "gpt-5.4-mini",
  allowWebSearch: process.env.RAISE_ENABLE_WEB_SEARCH === "1"
});

const server = http.createServer(createHandler({ token, execute }));
server.requestTimeout = 10_000;
server.headersTimeout = 5_000;
server.keepAliveTimeout = 5_000;

server.listen(port, host, () => {
  console.log(JSON.stringify({ event: "raise_gateway_started", host, port }));
});