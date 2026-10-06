import net from "node:net";

function isLoopbackHost(host) {
  const normalized = host.trim().toLowerCase();
  if (normalized === "localhost" || normalized === "::1") return true;
  return net.isIP(normalized) === 4 && normalized.startsWith("127.");
}

export function validateServerConfig({ host, port, tlsCert, tlsKey }) {
  if (typeof host !== "string" || !host.trim()) {
    throw new Error("RAISE_HOST must be a non-empty host");
  }

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("RAISE_PORT must be an integer from 1 through 65535");
  }

  if (typeof tlsCert !== "string" || typeof tlsKey !== "string") {
    throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must be strings");
  }

  if (Boolean(tlsCert) !== Boolean(tlsKey)) {
    throw new Error("RAISE_TLS_CERT and RAISE_TLS_KEY must be set together");
  }

  if (!tlsCert && !isLoopbackHost(host)) {
    throw new Error("TLS is required when Raise AI listens on a non-loopback host");
  }
}
