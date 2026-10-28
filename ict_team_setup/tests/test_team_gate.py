"""Adversarial acceptance-boundary tests, using synthetic reports only."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "team_gate.py"
SPEC = importlib.util.spec_from_file_location("team_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reports = self.root / "reports"
        self.reports.mkdir()
        self.baseline = self.root / "baseline"
        (self.baseline / "results").mkdir(parents=True)
        (self.baseline / "source").mkdir()
        (self.baseline / "data").mkdir()
        (self.baseline / "SPEC.md").write_text("frozen synthetic specification")
        (self.baseline / "source" / "engine.py").write_text("frozen synthetic source")
        (self.baseline / "data" / "bars.csv").write_text("frozen synthetic data")
        self.manifest = self.baseline / "results" / "run_manifest.json"
        self.manifest.write_text('{"fixture":"synthetic manifest"}\n')
        self.digest = gate.sha256_bytes(self.manifest.read_bytes())
        self.out = self.root / "evidence" / "gate.json"
        self.run_id = "fixture-run"
        self.fixture = {}
        for role_id, checks in gate.REQUIRED_CHECKS.items():
            self.fixture[role_id] = {
                "schema_version": "1.0", "role_id": role_id, "run_id": self.run_id,
                "baseline_manifest_sha256": self.digest, "status": "PASS",
                "scope": "synthetic contract test, no audit performed",
                "checks": [{"name": name, "status": "PASS", "evidence": ["synthetic test witness"]} for name in checks],
                "findings": [], "summary_fa": "دادهٔ مصنوعی آزمون قرارداد",
            }
        self.write_reports()

    def write_reports(self):
        for role_id, report in self.fixture.items():
            (self.reports / f"{role_id}.json").write_text(json.dumps(report))

    def run_gate(self):
        state, code = gate.run_gate(self.reports, self.manifest, self.run_id, self.out)
        self.assertIs(state["execution_eligible"], False)
        self.assertEqual(json.loads(self.out.read_text()), state)
        return state, code

    def assert_rejected(self):
        state, code = self.run_gate()
        self.assertEqual(code, 2)
        self.assertEqual(state["status"], "FAIL")
        self.assertFalse(state["acceptance_pass"])
        self.assertTrue(state["errors"])

    def test_all_five_pass_only_research_readiness_passes(self):
        state, code = self.run_gate()
        self.assertEqual((code, state["status"]), (0, "PASS"))
        self.assertEqual(len(state["report_sha256"]), 5)

    def test_missing_role_rejects_old_pass(self):
        self.out.parent.mkdir()
        self.out.write_text('{"acceptance_pass":true,"execution_eligible":true}')
        (self.reports / "supervisor.json").unlink()
        self.assert_rejected()

    def test_sixth_report_rejected(self):
        (self.reports / "duplicate.json").write_text('{}')
        self.assert_rejected()

    def test_report_role_must_match_filename(self):
        self.fixture["architect"]["role_id"] = "supervisor"
        self.write_reports()
        self.assert_rejected()

    def test_stale_run_id_rejected(self):
        self.fixture["architect"]["run_id"] = "previous-run"
        self.write_reports()
        self.assert_rejected()

    def test_stale_manifest_hash_rejected(self):
        self.manifest.write_text('{"changed":"baseline"}')
        self.assert_rejected()

    def test_missing_required_check_rejected(self):
        self.fixture["logic_auditor"]["checks"].pop()
        self.write_reports()
        self.assert_rejected()

    def test_duplicate_check_rejected(self):
        checks = self.fixture["architect"]["checks"]
        checks.append(copy.deepcopy(checks[0]))
        self.write_reports()
        self.assert_rejected()

    def test_missing_fields_rejected(self):
        del self.fixture["architect"]["scope"]
        self.write_reports()
        self.assert_rejected()

    def test_unknown_field_cannot_authorize_execution(self):
        self.fixture["architect"]["execution_eligible"] = True
        self.write_reports()
        self.assert_rejected()

    def test_malformed_evidence_types_and_empty_values_rejected(self):
        for evidence in (None, [], " ", [""], [True], {"path": "x"}):
            with self.subTest(evidence=evidence):
                self.fixture["architect"]["checks"][0]["evidence"] = evidence
                self.write_reports()
                self.assert_rejected()

    def test_string_evidence_supported(self):
        self.fixture["architect"]["checks"][0]["evidence"] = "precise source locator"
        self.write_reports()
        self.assertEqual(self.run_gate()[1], 0)

    def test_invalid_statuses_rejected(self):
        for status in ("RUNNING", "PASSED", True, None, []):
            with self.subTest(status=status):
                self.fixture["architect"]["status"] = status
                self.write_reports()
                self.assert_rejected()

    def test_invalid_check_status_rejected(self):
        self.fixture["architect"]["checks"][0]["status"] = "SKIPPED"
        self.write_reports()
        self.assert_rejected()

    def test_non_pass_check_under_pass_role_is_rejected(self):
        self.fixture["architect"]["checks"][0]["status"] = "BLOCKED"
        self.write_reports()
        self.assert_rejected()

    def test_valid_blocked_and_not_run_reports_stop_readiness(self):
        for status in ("BLOCKED", "NOT_RUN", "FAIL"):
            with self.subTest(status=status):
                self.fixture["architect"]["status"] = status
                self.fixture["architect"]["checks"][0]["status"] = status
                self.write_reports()
                state, code = self.run_gate()
                self.assertEqual((code, state["status"]), (1, status))
                self.assertFalse(state["acceptance_pass"])

    def test_high_or_critical_finding_vetoes_otherwise_green_reports(self):
        for severity in ("HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                self.fixture["trade_evaluator"]["findings"] = [{"severity": severity, "category": "risk", "detail": "unresolved witness"}]
                self.write_reports()
                state, code = self.run_gate()
                self.assertEqual((code, state["status"]), (1, "BLOCKED"))
                self.assertEqual(len(state["risk_vetoes"]), 1)

    def test_invalid_finding_rejected(self):
        self.fixture["architect"]["findings"] = [{"severity": "high", "category": "risk", "detail": "witness"}]
        self.write_reports()
        self.assert_rejected()

    def test_malformed_json_rejected(self):
        (self.reports / "architect.json").write_text('{')
        self.assert_rejected()

    def test_duplicate_json_key_rejected(self):
        raw = json.dumps(self.fixture["architect"])
        (self.reports / "architect.json").write_text(raw[:-1] + ',"status":"PASS"}')
        self.assert_rejected()

    def test_nonfinite_json_rejected(self):
        (self.reports / "architect.json").write_text('{"status": NaN}')
        self.assert_rejected()

    def test_unknown_schema_rejected(self):
        self.fixture["architect"]["schema_version"] = "2.0"
        self.write_reports()
        self.assert_rejected()

    def test_reset_only_does_not_read_missing_reports_or_manifest(self):
        self.out.parent.mkdir()
        self.out.write_text('{"acceptance_pass":true}')
        state, code = gate.run_gate(self.root / "missing", self.root / "missing" / "results" / "run_manifest.json", self.run_id, self.out, True)
        self.assertEqual((code, state["status"]), (0, "NOT_RUN"))
        self.assertFalse(json.loads(self.out.read_text())["acceptance_pass"])

    def test_reset_occurs_before_report_review(self):
        original = gate.validate_report
        def observe(*args):
            saved = json.loads(self.out.read_text())
            self.assertEqual(saved["status"], "NOT_RUN")
            self.assertFalse(saved["acceptance_pass"])
            return original(*args)
        with patch.object(gate, "validate_report", side_effect=observe):
            self.assertEqual(self.run_gate()[1], 0)

    def test_manifest_mutation_during_gate_rejected(self):
        original = gate.validate_report
        def mutate(*args):
            self.manifest.write_text('{"mutated":true}')
            return original(*args)
        with patch.object(gate, "validate_report", side_effect=mutate):
            self.assert_rejected()

    def test_report_mutation_during_gate_rejected(self):
        original = gate.validate_report
        def mutate(*args):
            result = original(*args)
            if args[1] == "supervisor":
                (self.reports / "architect.json").write_text('{}')
            return result
        with patch.object(gate, "validate_report", side_effect=mutate):
            self.assert_rejected()

    def test_symlink_report_rejected(self):
        path = self.reports / "architect.json"
        target = self.root / "architect-copy.json"
        path.rename(target)
        path.symlink_to(target)
        self.assert_rejected()

    def test_output_cannot_overwrite_report_or_baseline(self):
        for unsafe in (self.reports / "architect.json", self.manifest):
            with self.subTest(unsafe=unsafe):
                before = unsafe.read_bytes()
                with self.assertRaises(gate.ContractError):
                    gate.run_gate(self.reports, self.manifest, self.run_id, unsafe)
                self.assertEqual(unsafe.read_bytes(), before)

    def test_output_cannot_modify_any_baseline_subtree(self):
        for relative in ("SPEC.md", "source/engine.py", "data/bars.csv", "results/new-gate.json"):
            with self.subTest(relative=relative):
                unsafe = self.baseline / relative
                before = {path.relative_to(self.baseline): path.read_bytes() for path in self.baseline.rglob("*") if path.is_file()}
                with self.assertRaises(gate.ContractError):
                    gate.run_gate(self.reports, self.manifest, self.run_id, unsafe)
                after = {path.relative_to(self.baseline): path.read_bytes() for path in self.baseline.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_output_alias_into_baseline_rejected(self):
        alias = self.root / "baseline-alias"
        alias.symlink_to(self.baseline, target_is_directory=True)
        with self.assertRaises(gate.ContractError):
            gate.run_gate(self.reports, self.manifest, self.run_id, alias / "source" / "engine.py")
        self.assertEqual((self.baseline / "source" / "engine.py").read_text(), "frozen synthetic source")

    def test_manifest_symlink_cannot_hide_actual_baseline_root(self):
        alias = self.root / "manifest-alias"
        (alias / "results").mkdir(parents=True)
        alias_manifest = alias / "results" / "run_manifest.json"
        alias_manifest.symlink_to(self.manifest)
        original = (self.baseline / "source" / "engine.py").read_bytes()
        with self.assertRaises(gate.ContractError):
            gate.run_gate(self.reports, alias_manifest, self.run_id, self.baseline / "source" / "engine.py")
        self.assertEqual((self.baseline / "source" / "engine.py").read_bytes(), original)

    def test_results_directory_symlink_cannot_hide_actual_baseline_root(self):
        alias = self.root / "results-alias"
        alias.mkdir()
        (alias / "results").symlink_to(self.baseline / "results", target_is_directory=True)
        original = (self.baseline / "SPEC.md").read_bytes()
        with self.assertRaises(gate.ContractError):
            gate.run_gate(self.reports, alias / "results" / "run_manifest.json", self.run_id, self.baseline / "SPEC.md")
        self.assertEqual((self.baseline / "SPEC.md").read_bytes(), original)

    def test_output_symlink_inside_baseline_rejected_even_if_target_outside(self):
        external = self.root / "outside.json"
        external.write_text("untouched outside")
        inside = self.baseline / "results" / "output-link.json"
        inside.symlink_to(external)
        with self.assertRaises(gate.ContractError):
            gate.run_gate(self.reports, self.manifest, self.run_id, inside)
        self.assertTrue(inside.is_symlink())
        self.assertEqual(external.read_text(), "untouched outside")

    def test_ambiguous_baseline_root_fails_closed_before_mutation(self):
        ambiguous = self.root / "some_manifest.json"
        ambiguous.write_bytes(self.manifest.read_bytes())
        with self.assertRaises(gate.ContractError):
            gate.run_gate(self.reports, ambiguous, self.run_id, self.out)
        self.assertFalse(self.out.exists())

    def test_decision_and_output_are_deterministic(self):
        self.run_gate()
        before = self.out.read_bytes()
        self.run_gate()
        self.assertEqual(self.out.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
