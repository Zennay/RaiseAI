import assert from "node:assert/strict";
import test from "node:test";
import { validateDeployEvidence, assertDeployEvidence } from "../deploy/validate-deploy-evidence.mjs";

const revision = "9fdf2c7d73766ef02692d5d62708a113686de210";

function openRouterProbe() {
  return {
    name: "openrouter_quick_ai_probe",
    ok: true,
    status: 200,
    route: "quick_ai",
    configured: true,
    provider: "openrouter",
    model: "z-ai/glm-5.3-flash"
  };
}

function goodEvidence({ degraded = false } = {}) {
  return {
    schema_version: 3,
    workflow: {
      run_id: 36941194825,
      run_attempt: 1,
      repository: "Zennay/RaiseAI",
      ref: "refs/heads/main",
      commit: revision
    },
    service: {
      unit: "raise-gateway.service",
      active_state: "active",
      sub_state: "running"
    },
    attestation: {
      expected_revision: revision,
      live_revision: revision,
      exact_revision_match: true
    },
    verification: {
      deploy: { outcome: "success" },
      initial_payload: {
        outcome: "success",
        ok: true,
        source_digest: "a".repeat(64),
        installed_digest: "a".repeat(64),
        source_file_count: 4,
        installed_file_count: 4
      },
      initial_runtime: {
        outcome: "success",
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
      },
      initial_watch_profile: {
        outcome: "success",
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
      },
      initial_smoke: { outcome: "success", ok: true, degraded, checks: [openRouterProbe()] },
      idempotent_redeploy: { outcome: "success" },
      repeat_payload: {
        outcome: "success",
        ok: true,
        source_digest: "a".repeat(64),
        installed_digest: "a".repeat(64),
        source_file_count: 4,
        installed_file_count: 4
      },
      repeat_runtime: {
        outcome: "success",
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
      },
      repeat_watch_profile: {
        outcome: "success",
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
      },
      repeat_smoke: { outcome: "success", ok: true, degraded, checks: [openRouterProbe()] }
    }
  };
}

test("accepts complete exact-revision deployment evidence", () => {
  assert.deepEqual(
    validateDeployEvidence(goodEvidence(), { expectedRevision: revision }),
    []
  );
  assert.equal(
    assertDeployEvidence(goodEvidence(), { expectedRevision: revision }),
    true
  );
});

test("allows a degraded dependency when core deployment proof is green", () => {
  assert.deepEqual(
    validateDeployEvidence(goodEvidence({ degraded: true }), {
      expectedRevision: revision
    }),
    []
  );
});

test("accepts production evidence only when both OpenRouter probes are proven", () => {
  assert.deepEqual(
    validateDeployEvidence(goodEvidence(), {
      expectedRevision: revision,
      requireOpenRouter: true
    }),
    []
  );
});

test("rejects production evidence when an OpenRouter probe is missing or degraded", () => {
  const evidence = goodEvidence();
  evidence.verification.initial_smoke.checks = [];
  evidence.verification.repeat_smoke.checks[0] = {
    name: "openrouter_quick_ai_probe",
    ok: true,
    route: "quick_ai",
    configured: false,
    reason: "openrouter_not_configured",
    degraded: true
  };

  const errors = validateDeployEvidence(evidence, {
    expectedRevision: revision,
    requireOpenRouter: true
  });
  assert.equal(errors.includes("initial OpenRouter quick_ai probe not proven"), true);
  assert.equal(errors.includes("repeat OpenRouter quick_ai probe not proven"), true);
});

test("rejects stale live revision and an inactive service", () => {
  const evidence = goodEvidence();
  evidence.attestation.live_revision = "stale";
  evidence.attestation.exact_revision_match = false;
  evidence.service.active_state = "failed";
  evidence.service.sub_state = "dead";

  const errors = validateDeployEvidence(evidence, { expectedRevision: revision });
  assert.equal(errors.includes("exact revision match not proven"), true);
  assert.equal(errors.includes("live revision does not match expected revision"), true);
  assert.equal(errors.includes("gateway service is not active"), true);
  assert.equal(errors.includes("gateway service is not running"), true);
});

test("rejects mismatched payload attestation", () => {
  const evidence = goodEvidence();
  evidence.verification.initial_payload.installed_digest = "b".repeat(64);
  evidence.verification.repeat_payload.ok = false;

  const errors = validateDeployEvidence(evidence, { expectedRevision: revision });
  assert.equal(errors.includes("initial payload attestation did not succeed"), true);
  assert.equal(errors.includes("repeat payload attestation did not succeed"), true);
});

test("rejects missing or partial runtime wiring proof", () => {
  const evidence = goodEvidence();
  evidence.verification.initial_runtime.checks.exec_start = false;
  evidence.verification.repeat_runtime.checks = {};

  const errors = validateDeployEvidence(evidence, { expectedRevision: revision });
  assert.equal(errors.includes("initial runtime wiring attestation did not succeed"), true);
  assert.equal(errors.includes("repeat runtime wiring attestation did not succeed"), true);
});

test("rejects mismatched Watch provisioning proof", () => {
  const evidence = goodEvidence();
  evidence.verification.initial_watch_profile.checks.token_match = false;
  evidence.verification.repeat_watch_profile.checks.spki_match = false;

  const errors = validateDeployEvidence(evidence, { expectedRevision: revision });
  assert.equal(errors.includes("initial Watch profile attestation did not succeed"), true);
  assert.equal(errors.includes("repeat Watch profile attestation did not succeed"), true);
});

test("rejects incomplete deploy, smoke and idempotency outcomes", () => {
  const evidence = goodEvidence();
  evidence.verification.deploy.outcome = "failure";
  evidence.verification.initial_smoke.ok = false;
  evidence.verification.idempotent_redeploy.outcome = "skipped";
  evidence.verification.repeat_smoke.outcome = "cancelled";

  const errors = validateDeployEvidence(evidence, { expectedRevision: revision });
  assert.equal(errors.includes("deploy step did not succeed"), true);
  assert.equal(errors.includes("initial live smoke did not succeed"), true);
  assert.equal(errors.includes("idempotent redeploy did not succeed"), true);
  assert.equal(errors.includes("repeat live smoke did not succeed"), true);
});


test("rejects self-asserted revision match when commit and live revision differ", () => {
  const evidence = goodEvidence();
  evidence.attestation.live_revision = "b".repeat(40);
  evidence.attestation.exact_revision_match = true;

  const errors = validateDeployEvidence(evidence, { expectedRevision: "" });
  assert.equal(errors.includes("live revision does not match workflow commit"), true);
});

test("rejects incoherent attested expected revision without relying on CI environment", () => {
  const evidence = goodEvidence();
  evidence.attestation.expected_revision = "b".repeat(40);

  const errors = validateDeployEvidence(evidence, { expectedRevision: "" });
  assert.equal(
    errors.includes("attestation.expected_revision does not match workflow.commit"),
    true
  );
});

test("rejects malformed revision identities and non-positive workflow identifiers", () => {
  const evidence = goodEvidence();
  evidence.workflow.run_id = 0;
  evidence.workflow.run_attempt = 0;
  evidence.workflow.commit = "not-a-sha";
  evidence.attestation.expected_revision = "not-a-sha";
  evidence.attestation.live_revision = "not-a-sha";
  evidence.attestation.exact_revision_match = true;

  const errors = validateDeployEvidence(evidence, { expectedRevision: "" });
  assert.equal(errors.includes("workflow.run_id must be a positive integer"), true);
  assert.equal(errors.includes("workflow.run_attempt must be a positive integer"), true);
  assert.equal(
    errors.includes("workflow.commit must be a 40-character hexadecimal revision"),
    true
  );
  assert.equal(
    errors.includes("attestation.expected_revision must be a 40-character hexadecimal revision"),
    true
  );
  assert.equal(
    errors.includes("attestation.live_revision must be a 40-character hexadecimal revision"),
    true
  );
});

test("rejects payload proof with fake equal digests or mismatched file counts", () => {
  const fakeDigest = goodEvidence();
  fakeDigest.verification.initial_payload.source_digest = "same";
  fakeDigest.verification.initial_payload.installed_digest = "same";

  const fakeDigestErrors = validateDeployEvidence(fakeDigest, {
    expectedRevision: revision
  });
  assert.equal(
    fakeDigestErrors.includes("initial payload attestation did not succeed"),
    true
  );

  const mismatchedCounts = goodEvidence();
  mismatchedCounts.verification.repeat_payload.installed_file_count = 5;

  const countErrors = validateDeployEvidence(mismatchedCounts, {
    expectedRevision: revision
  });
  assert.equal(
    countErrors.includes("repeat payload attestation did not succeed"),
    true
  );
});
