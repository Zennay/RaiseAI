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

function runtimeAttestationOk(report) {
  const checks = report?.checks ?? {};
  return (
    report?.outcome === SUCCESS &&
    report?.ok === true &&
    report?.active_state === "active" &&
    report?.sub_state === "running" &&
    checks.fragment_path === true &&
    checks.working_directory === true &&
    checks.exec_start === true &&
    checks.environment_file === true
  );
}

function watchProfileAttestationOk(report) {
  const checks = report?.checks ?? {};
  return (
    report?.outcome === SUCCESS &&
    report?.ok === true &&
    checks.https_url === true &&
    checks.port_match === true &&
    checks.token_match === true &&
    checks.spki_match === true &&
    checks.certificate_host_match === true &&
    checks.certificate_currently_valid === true &&
    checks.profile_mode_600 === true
  );
}

function openRouterProbeOk(report) {
  const check = report?.checks?.find(
    item => item?.name === "openrouter_quick_ai_probe"
  );
  return (
    report?.outcome === SUCCESS &&
    report?.ok === true &&
    check?.ok === true &&
    check?.status === 200 &&
    check?.route === "quick_ai" &&
    check?.configured === true &&
    check?.provider === "openrouter"
  );
}

export function validateDeployEvidence(
  evidence,
  {
    expectedRevision = process.env.RAISE_EXPECTED_REVISION ?? process.env.GITHUB_SHA ?? "",
    requireOpenRouter = process.env.RAISE_REQUIRE_OPENROUTER === "1"
  } = {}
) {
  const errors = [];
  const expected = text(expectedRevision);

  push(errors, evidence && typeof evidence === "object", "evidence must be an object");
  if (!evidence || typeof evidence !== "object") return errors;

  push(errors, evidence.schema_version === 3, "unsupported evidence schema_version");
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
    verification.initial_payload?.outcome === SUCCESS &&
      verification.initial_payload?.ok === true &&
      verification.initial_payload?.source_digest &&
      verification.initial_payload?.source_digest === verification.initial_payload?.installed_digest,
    "initial payload attestation did not succeed"
  );
  push(
    errors,
    runtimeAttestationOk(verification.initial_runtime),
    "initial runtime wiring attestation did not succeed"
  );
  push(
    errors,
    watchProfileAttestationOk(verification.initial_watch_profile),
    "initial Watch profile attestation did not succeed"
  );
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
    verification.repeat_payload?.outcome === SUCCESS &&
      verification.repeat_payload?.ok === true &&
      verification.repeat_payload?.source_digest &&
      verification.repeat_payload?.source_digest === verification.repeat_payload?.installed_digest,
    "repeat payload attestation did not succeed"
  );
  push(
    errors,
    runtimeAttestationOk(verification.repeat_runtime),
    "repeat runtime wiring attestation did not succeed"
  );
  push(
    errors,
    watchProfileAttestationOk(verification.repeat_watch_profile),
    "repeat Watch profile attestation did not succeed"
  );
  push(
    errors,
    verification.repeat_smoke?.outcome === SUCCESS && verification.repeat_smoke?.ok === true,
    "repeat live smoke did not succeed"
  );

  if (requireOpenRouter) {
    push(
      errors,
      openRouterProbeOk(verification.initial_smoke),
      "initial OpenRouter quick_ai probe not proven"
    );
    push(
      errors,
      openRouterProbeOk(verification.repeat_smoke),
      "repeat OpenRouter quick_ai probe not proven"
    );
  }

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
