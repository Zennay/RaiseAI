import net from "node:net";
import path from "node:path";

const CONTROL_CHARS = /[\u0000-\u001f\u007f]/u;

function isLoopbackHost(host) {
  const normalized = host.toLowerCase();
  if (normalized === "localhost" || normalized === "::1") return true;
  return net.isIP(normalized) === 4 && normalized.startsWith("127.");
}

function isValidHost(host) {
  if (net.isIP(host)) return true;
  if (host.length > 253) return false;

  const labels = host.toLowerCase().split(".");
  return labels.every(label =>
    label.length >= 1 &&
    label.length <= 63 &&
    /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/u.test(label)
  );
}

export function parseServerPort(value, fallback = 8787) {
  if (value === undefined) return fallback;

  if (typeof value !== "string" || !/^[1-9]\d{0,4}$/.test(value)) {
    throw new Error("RAISE_PORT must be a canonical decimal integer from 1 through 65535");
  }

  const port = Number(value);
  if (port > 65535) {
    throw new Error("RAISE_PORT must be a canonical decimal integer from 1 through 65535");
  }

  return port;
}

export function validateServerConfig({ host, port, tlsCert, tlsKey }) {
  if (typeof host !== "string" || !host.trim()) {
    throw new Error("RAISE_HOST must be a non-empty host");
  }

  if (host !== host.trim()) {
    throw new Error("RAISE_HOST must not contain surrounding whitespace");
  }

  if (!isValidHost(host)) {
    throw new Error("RAISE_HOST must be an IP address or canonical hostname");
  }

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("RAISE_PORT must be an integer from 1 through 65535");
  }

  if (typeof tlsCert !== "string" || typeof tlsKey !== "string") {
    throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must be strings");
  }

  if (
    (tlsCert && tlsCert !== tlsCert.trim()) ||
    (tlsKey && tlsKey !== tlsKey.trim())
  ) {
    throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must not contain surrounding whitespace");
  }

  if (Boolean(tlsCert) !== Boolean(tlsKey)) {
    throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must be set together");
  }

  if (
    tlsCert &&
    (
      !path.isAbsolute(tlsCert) ||
      !path.isAbsolute(tlsKey) ||
      CONTROL_CHARS.test(tlsCert) ||
      CONTROL_CHARS.test(tlsKey)
    )
  ) {
    throw new Error(
      "RAISE_TLS_CERT and RAISE_TLS_KEY must be absolute paths without control characters"
    );
  }

  if (!tlsCert && !isLoopbackHost(host)) {
    throw new Error("TLS is required when Raise AI listens on a non-loopback host");
  }
}
