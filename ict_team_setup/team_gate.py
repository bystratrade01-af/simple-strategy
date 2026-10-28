#!/usr/bin/env python3
"""Validate five archived research reviews; never authorize trade execution.

This is a deterministic report aggregator, not an LLM or semantic audit.
Only the Python standard library is needed. See README_FA.md for the contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SCHEMA_VERSION = "1.0"
STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "NOT_RUN"})
SEVERITIES = frozenset({"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"})
REQUIRED_CHECKS = {
    "architect": ("role_contracts", "baseline_binding", "fail_closed_gate", "gate_failure_tests", "rerun_workflow"),
    "logic_auditor": ("causality", "terminal_states", "independent_witnesses"),
    "data_auditor": ("input_integrity", "manifest_hashes", "provenance"),
    "trade_evaluator": ("ledger", "execution_assumptions", "sample_limits"),
    "supervisor": ("independent_review", "risk_vetoes", "acceptance_integrity"),
}
REPORT_FIELDS = {"schema_version", "role_id", "run_id", "baseline_manifest_sha256", "status", "scope", "checks", "findings", "summary_fa"}
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ContractError(ValueError):
    """Input cannot be accepted as a research review report."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_number(value):
    raise ContractError(f"non-finite JSON number: {value}")


def parse_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_bad_number)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid UTF-8 JSON") from exc


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ContractError(f"{label}: fields must be exactly {', '.join(sorted(fields))}")


def _evidence_valid(value) -> bool:
    return _nonempty(value) or (isinstance(value, list) and bool(value) and all(_nonempty(item) for item in value))


def validate_report(report, role_id: str, run_id: str, manifest_digest: str):
    """Validate shape and consistency, without pretending to verify evidence truth."""
    _require_fields(report, REPORT_FIELDS, role_id)
    if report["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"{role_id}: unsupported schema_version")
    if report["role_id"] != role_id:
        raise ContractError(f"{role_id}: role_id does not match filename")
    if report["run_id"] != run_id:
        raise ContractError(f"{role_id}: stale or different run_id")
    if report["baseline_manifest_sha256"] != manifest_digest:
        raise ContractError(f"{role_id}: baseline manifest SHA256 mismatch")
    if not isinstance(report["status"], str) or report["status"] not in STATUSES:
        raise ContractError(f"{role_id}: invalid status")
    for field in ("scope", "summary_fa"):
        if not _nonempty(report[field]):
            raise ContractError(f"{role_id}: {field} must be a nonempty string")
    checks = report["checks"]
    if not isinstance(checks, list) or not checks:
        raise ContractError(f"{role_id}: checks must be a nonempty list")
    names = set()
    for check in checks:
        _require_fields(check, {"name", "status", "evidence"}, f"{role_id} check")
        if not _nonempty(check["name"]) or check["name"] in names:
            raise ContractError(f"{role_id}: empty or duplicate check name")
        names.add(check["name"])
        if not isinstance(check["status"], str) or check["status"] not in STATUSES:
            raise ContractError(f"{role_id}: invalid check status")
        if not _evidence_valid(check["evidence"]):
            raise ContractError(f"{role_id}: check evidence must be a nonempty string or string list")
    missing = set(REQUIRED_CHECKS[role_id]) - names
    if missing:
        raise ContractError(f"{role_id}: missing required checks: {', '.join(sorted(missing))}")
    findings = report["findings"]
    if not isinstance(findings, list):
        raise ContractError(f"{role_id}: findings must be a list")
    vetoes = []
    for finding in findings:
        _require_fields(finding, {"severity", "category", "detail"}, f"{role_id} finding")
        if not isinstance(finding["severity"], str) or finding["severity"] not in SEVERITIES:
            raise ContractError(f"{role_id}: invalid finding severity")
        if not _nonempty(finding["category"]) or not _nonempty(finding["detail"]):
            raise ContractError(f"{role_id}: findings need category and detail")
        if finding["severity"] in {"HIGH", "CRITICAL"}:
            vetoes.append({"role_id": role_id, **finding})
    if report["status"] == "PASS" and any(check["status"] != "PASS" for check in checks):
        raise ContractError(f"{role_id}: PASS contradicts a non-PASS check")
    # A PASS plus a high finding remains a well-formed report, but the finding vetoes readiness.
    return vetoes


def _state(run_id: str, digest=None, status="NOT_RUN", errors=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "baseline_manifest_sha256": digest,
        "status": status,
        "research_review_readiness": status,
        "acceptance_pass": status == "PASS",
        "execution_eligible": False,
        "scope": "five-role archived research review; no financial validation or execution authorization",
        "role_statuses": {},
        "report_sha256": {},
        "risk_vetoes": [],
        "errors": list(errors or []),
    }


def write_state(path: Path, value):
    """Atomic replacement prevents an interrupted write from leaving a partial PASS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".gate-", delete=False) as stream:
            name = stream.name
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        Path(name).replace(path)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def _safe_output(output: Path, reports_dir: Path, baseline_manifest: Path):
    # The immutable Stage9 root is unambiguous only for its documented layout.
    # Check both lexical paths and symlink-resolved paths: replacing a symlink
    # inside the baseline is still a mutation even when its target is elsewhere.
    manifest_lexical = Path(os.path.abspath(baseline_manifest))
    manifest_resolved = baseline_manifest.resolve()
    if any(path.name != "run_manifest.json" or path.parent.name != "results" for path in (manifest_lexical, manifest_resolved)):
        raise ContractError("ambiguous baseline root: require BASELINE/results/run_manifest.json")
    baseline_roots = {manifest_lexical.parent.parent, manifest_lexical.parent.parent.resolve(), manifest_resolved.parent.parent}
    output_paths = {Path(os.path.abspath(output)), output.resolve()}
    report_roots = {Path(os.path.abspath(reports_dir)), reports_dir.resolve()}
    if any(path.is_relative_to(root) for path in output_paths for root in baseline_roots):
        raise ContractError("output must be outside the entire read-only baseline tree")
    if any(path.is_relative_to(root) for path in output_paths for root in report_roots):
        raise ContractError("output must be outside reports")


def _report_files(reports_dir: Path):
    if not reports_dir.is_dir():
        raise ContractError("reports directory is missing")
    files = {path.name: path for path in reports_dir.iterdir() if path.suffix.lower() == ".json"}
    expected = {f"{role}.json" for role in REQUIRED_CHECKS}
    if set(files) != expected:
        missing = sorted(expected - set(files))
        extra = sorted(set(files) - expected)
        raise ContractError(f"exactly five role JSON reports required; missing={missing}, extra={extra}")
    if any(not path.is_file() or path.is_symlink() for path in files.values()):
        raise ContractError("role reports must be regular files, not symlinks")
    return files


def run_gate(reports_dir: Path, baseline_manifest: Path, run_id: str, output: Path, reset_only=False):
    """Reset prior acceptance before reading input; return (state, exit_code)."""
    _safe_output(output, reports_dir, baseline_manifest)
    state = _state(run_id)
    write_state(output, state)  # First mutation: stale acceptance cannot survive work starting.
    try:
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise ContractError("run_id must be 1-128 safe identifier characters")
        if reset_only:
            return state, 0
        baseline_raw = baseline_manifest.read_bytes()
        if not isinstance(parse_json(baseline_raw), dict):
            raise ContractError("baseline manifest must be a JSON object")
        digest = sha256_bytes(baseline_raw)
        state["baseline_manifest_sha256"] = digest
        reports = _report_files(reports_dir)
        report_bytes = {}
        all_statuses = []
        for role_id in REQUIRED_CHECKS:
            raw = reports[f"{role_id}.json"].read_bytes()
            report_bytes[role_id] = raw
            report = parse_json(raw)
            state["risk_vetoes"].extend(validate_report(report, role_id, run_id, digest))
            state["role_statuses"][role_id] = report["status"]
            state["report_sha256"][role_id] = sha256_bytes(raw)
            all_statuses.extend([report["status"], *(check["status"] for check in report["checks"])])
        # Reject mutations while the gate reads; report truth still needs independent review.
        if baseline_manifest.read_bytes() != baseline_raw:
            raise ContractError("baseline manifest changed during aggregation")
        if set(_report_files(reports_dir)) != set(reports):
            raise ContractError("report set changed during aggregation")
        for role_id, raw in report_bytes.items():
            if reports[f"{role_id}.json"].read_bytes() != raw:
                raise ContractError(f"{role_id}: report changed during aggregation")
        if "FAIL" in all_statuses:
            status = "FAIL"
        elif state["risk_vetoes"] or "BLOCKED" in all_statuses:
            status = "BLOCKED"
        elif "NOT_RUN" in all_statuses:
            status = "NOT_RUN"
        else:
            status = "PASS"
        state.update(status=status, research_review_readiness=status, acceptance_pass=status == "PASS")
        write_state(output, state)
        return state, 0 if status == "PASS" else 1
    except (ContractError, OSError, TypeError, ValueError) as exc:
        state.update(status="FAIL", research_review_readiness="FAIL", acceptance_pass=False)
        state["errors"].append(str(exc))
        write_state(output, state)
        return state, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reset-only", action="store_true", help="invalidate prior readiness before any review/revalidation work")
    args = parser.parse_args(argv)
    try:
        state, code = run_gate(args.reports, args.baseline_manifest, args.run_id, args.out, args.reset_only)
    except (ContractError, OSError) as exc:
        state, code = _state(args.run_id, status="FAIL", errors=[str(exc)]), 2
    print(json.dumps(state, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
