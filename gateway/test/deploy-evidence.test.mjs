import assert from "node:assert/strict";
import test from "node:test";
import { buildDeployEvidence } from "../deploy/write-deploy-evidence.mjs";

const revision = "cacbd3dae9001acee86cc3a675ea50bc7a9cfe96";

function passingPayload() {
  return {
    ok: true,
    source_digest: "a".repeat(64),
    installed_digest: "a".repeat(64),
    source_file_count: 5,
    installed_file_count: 5,
    reason: "payload_match"
  };
}

function passingRuntime() {
  return {
    ok: true,
    reason: "runtime_wiring_match",
    active_state: "active",
    sub_state: "running",
    checks: {
      fragment_path: true,
      working_directory: true,
      exec_start: true,
      environment_file: true
    }
  };
}

function passingWatchProfile() {
  return {
    ok: true,
    reason: "watch_profile_match",
    checks: {
      https_url: true,
      port_match: true,
      token_match: true,
      spki_match: true,
      certificate_host_match: true,
      certificate_currently_valid: true,
      profile_mode_600: true
    }
  };
}

function passingSmoke({ degraded = false } = {}) {
  return {
    ok: true,
    degraded,
    checks: [
      {
        name: "health_revision",
        ok: true,
        status: 200,
        revision
      },
      {
        name: "unauthenticated_rejected",
        ok: true,
        status: 401
      },
      {
        name: "zcloud_dependency_probe",
        ok: true,
        status: 200,
        route: "zcloud_task",
        reason: degraded ? "zcloud_unavailable" : "connector_reachable",
        degraded
      }
    ]
  };
}

test("deploy evidence captures run, live revision, service and verification state", () => {
  const evidence = buildDeployEvidence({
    env: {
      GITHUB_RUN_ID: "36939040577",
      GITHUB_RUN_ATTEMPT: "2",
      GITHUB_REPOSITORY: "Zennay/RaiseAI",
      GITHUB_REF: "refs/heads/main",
      GITHUB_SHA: revision,
      RAISE_SYSTEMD_ACTIVE_STATE: "active",
      RAISE_SYSTEMD_SUB_STATE: "running",
      RAISE_DEPLOY_OUTCOME: "success",
      RAISE_INITIAL_PAYLOAD_OUTCOME: "success",
      RAISE_INITIAL_RUNTIME_OUTCOME: "success",
      RAISE_INITIAL_WATCH_PROFILE_OUTCOME: "success",
      RAISE_INITIAL_SMOKE_OUTCOME: "success",
      RAISE_IDEMPOTENCY_OUTCOME: "success",
      RAISE_REPEAT_PAYLOAD_OUTCOME: "success",
      RAISE_REPEAT_RUNTIME_OUTCOME: "success",
      RAISE_REPEAT_WATCH_PROFILE_OUTCOME: "success",
      RAISE_REPEAT_SMOKE_OUTCOME: "success"
    },
    initialSmoke: passingSmoke(),
    repeatSmoke: passingSmoke(),
    initialPayload: passingPayload(),
    repeatPayload: passingPayload(),
    initialRuntime: passingRuntime(),
    repeatRuntime: passingRuntime(),
    initialWatchProfile: passingWatchProfile(),
    repeatWatchProfile: passingWatchProfile(),
    now: () => new Date("2026-10-01T23:18:00.000Z")
  });

  assert.equal(evidence.schema_version, 3);
  assert.equal(evidence.workflow.run_id, 36939040577);
  assert.equal(evidence.workflow.run_attempt, 2);
  assert.equal(evidence.workflow.commit, revision);
  assert.equal(evidence.service.active_state, "active");
  assert.equal(evidence.service.sub_state, "running");
  assert.equal(evidence.attestation.live_revision, revision);
  assert.equal(evidence.attestation.exact_revision_match, true);
  assert.equal(evidence.verification.deploy.outcome, "success");
  assert.equal(evidence.verification.initial_payload.ok, true);
  assert.equal(evidence.verification.initial_payload.source_digest, "a".repeat(64));
  assert.equal(evidence.verification.initial_runtime.ok, true);
  assert.equal(evidence.verification.initial_runtime.checks.exec_start, true);
  assert.equal(evidence.verification.initial_watch_profile.ok, true);
  assert.equal(evidence.verification.initial_watch_profile.checks.token_match, true);
  assert.equal(evidence.verification.idempotent_redeploy.outcome, "success");
  assert.equal(evidence.verification.repeat_payload.ok, true);
  assert.equal(evidence.verification.repeat_runtime.ok, true);
  assert.equal(evidence.verification.repeat_smoke.ok, true);
});

test("deploy evidence never serializes unrelated server secrets", () => {
  const secret = "do-not-leak-this-gateway-token";
  const evidence = buildDeployEvidence({
    env: {
      GITHUB_RUN_ID: "1",
      GITHUB_SHA: revision,
      RAISE_GATEWAY_TOKEN: secret,
      OPENROUTER_API_KEY: "also-secret",
      RAISE_DEPLOY_OUTCOME: "success",
      RAISE_INITIAL_PAYLOAD_OUTCOME: "success",
      RAISE_INITIAL_RUNTIME_OUTCOME: "success",
      RAISE_INITIAL_WATCH_PROFILE_OUTCOME: "success",
      RAISE_INITIAL_SMOKE_OUTCOME: "success"
      RAISE_IDEMPOTENCY_OUTCOME: "success",
      RAISE_REPEAT_PAYLOAD_OUTCOME: "success",
      RAISE_REPEAT_RUNTIME_OUTCOME: "success",
      RAISE_REPEAT_WATCH_PROFILE_OUTCOME: "success",
      RAISE_REPEAT_SMOKE_OUTCOME: "success"
    },
    initialPayload: passingPayload(),
    repeatPayload: passingPayload(),
    initialRuntime: passingRuntime(),
    repeatRuntime: passingRuntime(),
    initialWatchProfile: passingWatchProfile(),
    repeatWatchProfile: passingWatchProfile(),
    repeatSmoke: passingSmoke()
  });

  const serialized = JSON.stringify(evidence);
  assert.equal(serialized.includes(secret), false);
  assert.equal(serialized.includes("also-secret"), false);
  assert.equal(serialized.includes("RAISE_GATEWAY_TOKEN"), false);
  assert.equal(serialized.includes("OPENROUTER_API_KEY"), false);
});

test("failed or skipped stages still yield machine-readable evidence", () => {
  const evidence = buildDeployEvidence({
    env: {
      GITHUB_RUN_ID: "2",
      GITHUB_SHA: revision,
      RAISE_DEPLOY_OUTCOME: "failure",
      RAISE_INITIAL_PAYLOAD_OUTCOME: "skipped",
      RAISE_INITIAL_RUNTIME_OUTCOME: "skipped",
      RAISE_INITIAL_WATCH_PROFILE_OUTCOME: "skipped",
      RAISE_INITIAL_SMOKE_OUTCOME: "skipped",
      RAISE_IDEMPOTENCY_OUTCOME: "skipped",
      RAISE_REPEAT_PAYLOAD_OUTCOME: "skipped",
      RAISE_REPEAT_RUNTIME_OUTCOME: "skipped",
      RAISE_REPEAT_WATCH_PROFILE_OUTCOME: "skipped",
      RAISE_REPEAT_SMOKE_OUTCOME: "skipped"
    }
  });

  assert.equal(evidence.verification.deploy.outcome, "failure");
  assert.equal(evidence.verification.initial_payload.outcome, "skipped");
  assert.equal(evidence.verification.initial_runtime.outcome, "skipped");
  assert.equal(evidence.verification.initial_watch_profile.outcome, "skipped");
  assert.equal(evidence.verification.initial_smoke.outcome, "skipped");
  assert.equal(evidence.verification.repeat_payload.outcome, "skipped");
  assert.equal(evidence.verification.repeat_runtime.outcome, "skipped");
  assert.equal(evidence.verification.repeat_watch_profile.outcome, "skipped");
  assert.equal(evidence.attestation.live_revision, null);
  assert.equal(evidence.attestation.exact_revision_match, null);
});
