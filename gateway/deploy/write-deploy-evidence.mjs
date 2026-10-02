#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const KNOWN_OUTCOMES = new Set(["success", "failure", "cancelled", "skipped"]);

function textOrNull(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function integerOrNull(value) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function outcome(value) {
  return KNOWN_OUTCOMES.has(value) ? value : "unknown";
}

function readReport(file) {
  const target = textOrNull(file);
  if (!target || !fs.existsSync(target)) return null;
  return JSON.parse(fs.readFileSync(target, "utf8"));
}

function safeCheck(check) {
  const result = {
    name: textOrNull(check?.name) ?? "unknown",
    ok: check?.ok === true
  };

  if (Number.isInteger(check?.status)) result.status = check.status;
  if (typeof check?.revision === "string") result.revision = check.revision;
  if (typeof check?.route === "string") result.route = check.route;
  if (typeof check?.reason === "string") result.reason = check.reason;
  if (typeof check?.degraded === "boolean") result.degraded = check.degraded;
  if (typeof check?.error === "string") result.error = check.error.slice(0, 500);

  return result;
}

function summarizeSmoke(report, stepOutcome) {
  return {
    outcome: outcome(stepOutcome),
    ok: typeof report?.ok === "boolean" ? report.ok : null,
    degraded: typeof report?.degraded === "boolean" ? report.degraded : null,
    checks: Array.isArray(report?.checks) ? report.checks.map(safeCheck) : []
  };
}

function summarizePayload(report, stepOutcome) {
  return {
    outcome: outcome(stepOutcome),
    ok: typeof report?.ok === "boolean" ? report.ok : null,
    source_digest: textOrNull(report?.source_digest),
    installed_digest: textOrNull(report?.installed_digest),
    source_file_count: Number.isInteger(report?.source_file_count)
      ? report.source_file_count
      : null,
    installed_file_count: Number.isInteger(report?.installed_file_count)
      ? report.installed_file_count
      : null,
    reason: textOrNull(report?.reason)
  };
}

function liveRevision(initialSmoke, repeatSmoke) {
  for (const report of [repeatSmoke, initialSmoke]) {
    const health = report?.checks?.find(
      item => item?.name === "health_revision" && item?.ok === true
    );
    if (typeof health?.revision === "string" && health.revision) return health.revision;
  }
  return null;
}

export function buildDeployEvidence({
  env = process.env,
  initialSmoke = null,
  repeatSmoke = null,
  initialPayload = null,
  repeatPayload = null,
  now = () => new Date()
} = {}) {
  const commit = textOrNull(env.GITHUB_SHA);
  const live = liveRevision(initialSmoke, repeatSmoke);

  return {
    schema_version: 2,
    generated_at: now().toISOString(),
    workflow: {
      run_id: integerOrNull(env.GITHUB_RUN_ID),
      run_attempt: integerOrNull(env.GITHUB_RUN_ATTEMPT),
      repository: textOrNull(env.GITHUB_REPOSITORY),
      ref: textOrNull(env.GITHUB_REF),
      commit
    },
    service: {
      unit: "raise-gateway.service",
      active_state: textOrNull(env.RAISE_SYSTEMD_ACTIVE_STATE),
      sub_state: textOrNull(env.RAISE_SYSTEMD_SUB_STATE)
    },
    attestation: {
      expected_revision: commit,
      live_revision: live,
      exact_revision_match: commit && live ? commit === live : null
    },
    verification: {
      deploy: {
        outcome: outcome(env.RAISE_DEPLOY_OUTCOME)
      },
      initial_payload: summarizePayload(
        initialPayload,
        env.RAISE_INITIAL_PAYLOAD_OUTCOME
      ),
      initial_smoke: summarizeSmoke(initialSmoke, env.RAISE_INITIAL_SMOKE_OUTCOME),
      idempotent_redeploy: {
        outcome: outcome(env.RAISE_IDEMPOTENCY_OUTCOME)
      },
      repeat_payload: summarizePayload(
        repeatPayload,
        env.RAISE_REPEAT_PAYLOAD_OUTCOME
      ),
      repeat_smoke: summarizeSmoke(repeatSmoke, env.RAISE_REPEAT_SMOKE_OUTCOME)
    }
  };
}

export function writeDeployEvidence({
  env = process.env,
  initialSmoke = readReport(env.RAISE_INITIAL_SMOKE_REPORT),
  repeatSmoke = readReport(env.RAISE_REPEAT_SMOKE_REPORT),
  initialPayload = readReport(env.RAISE_INITIAL_PAYLOAD_REPORT),
  repeatPayload = readReport(env.RAISE_REPEAT_PAYLOAD_REPORT),
  now
} = {}) {
  const output = textOrNull(env.RAISE_EVIDENCE_PATH);
  if (!output) throw new Error("RAISE_EVIDENCE_PATH is required");

  const evidence = buildDeployEvidence({
    env,
    initialSmoke,
    repeatSmoke,
    initialPayload,
    repeatPayload,
    now
  });
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(evidence, null, 2) + "\n", {
    encoding: "utf8",
    mode: 0o600
  });
  fs.chmodSync(output, 0o600);
  return evidence;
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  const evidence = writeDeployEvidence();
  console.log(
    `deploy evidence written: run=${evidence.workflow.run_id ?? "unknown"} commit=${evidence.workflow.commit ?? "unknown"} live=${evidence.attestation.live_revision ?? "unknown"}`
  );
}
