#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const SUCCESS = "success";

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function push(errors, condition, message) {
  if (!condition) errors.push(message);
}

export function validateDeployEvidence(
  evidence,
  { expectedRevision = process.env.RAISE_EXPECTED_REVISION ?? process.env.GITHUB_SHA ?? "" } = {}
) {
  const errors = [];
  const expected = text(expectedRevision);

  push(errors, evidence && typeof evidence === "object", "evidence must be an object");
  if (!evidence || typeof evidence !== "object") return errors;

  push(errors, evidence.schema_version === 1, "unsupported evidence schema_version");
  push(errors, Number.isInteger(evidence.workflow?.run_id), "workflow.run_id missing");
  push(errors, Number.isInteger(evidence.workflow?.run_attempt), "workflow.run_attempt missing");

  const commit = text(evidence.workflow?.commit);
  const liveRevision = text(evidence.attestation?.live_revision);
  push(errors, Boolean(commit), "workflow.commit missing");
  push(errors, Boolean(liveRevision), "attestation.live_revision missing");
  push(errors, evidence.attestation?.exact_revision_match === true, "exact revision match not proven");

  if (expected) {
    push(errors, commit === expected, "workflow.commit does not match expected revision");
    push(errors, liveRevision === expected, "live revision does not match expected revision");
  }

  push(errors, evidence.service?.active_state === "active", "gateway service is not active");
  push(errors, evidence.service?.sub_state === "running", "gateway service is not running");

  const verification = evidence.verification ?? {};
  push(errors, verification.deploy?.outcome === SUCCESS, "deploy step did not succeed");
  push(
    errors,
    verification.initial_smoke?.outcome === SUCCESS && verification.initial_smoke?.ok === true,
    "initial live smoke did not succeed"
  );
  push(
    errors,
    verification.idempotent_redeploy?.outcome === SUCCESS,
    "idempotent redeploy did not succeed"
  );
  push(
    errors,
    verification.repeat_smoke?.outcome === SUCCESS && verification.repeat_smoke?.ok === true,
    "repeat live smoke did not succeed"
  );

  return errors;
}

export function assertDeployEvidence(evidence, options) {
  const errors = validateDeployEvidence(evidence, options);
  if (errors.length) {
    const error = new Error(`deploy evidence gate failed:\n- ${errors.join("\n- ")}`);
    error.validationErrors = errors;
    throw error;
  }
  return true;
}

function readEvidence(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  const file = process.env.RAISE_EVIDENCE_PATH ?? process.argv[2] ?? "";
  if (!file) {
    console.error("RAISE_EVIDENCE_PATH or an evidence file argument is required");
    process.exit(2);
  }

  try {
    const evidence = readEvidence(file);
    assertDeployEvidence(evidence);
    console.log(
      `deploy evidence gate passed: run=${evidence.workflow.run_id} commit=${evidence.workflow.commit}`
    );
  } catch (error) {
    console.error(String(error.message ?? error));
    process.exit(1);
  }
}
