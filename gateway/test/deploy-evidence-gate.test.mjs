import assert from "node:assert/strict";
import test from "node:test";
import { validateDeployEvidence, assertDeployEvidence } from "../deploy/validate-deploy-evidence.mjs";

const revision = "9fdf2c7d73766ef02692d5d62708a113686de210";

function goodEvidence({ degraded = false } = {}) {
  return {
    schema_version: 1,
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
      initial_smoke: { outcome: "success", ok: true, degraded, checks: [] },
      idempotent_redeploy: { outcome: "success" },
      repeat_smoke: { outcome: "success", ok: true, degraded, checks: [] }
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
