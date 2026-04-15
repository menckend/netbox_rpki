from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "netbox_rpki" / "compatibility.py"
MODULE_SPEC = spec_from_file_location("netbox_rpki_compatibility_contract", MODULE_PATH)
compatibility = module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(compatibility)


class CompatibilityClassificationTestCase(TestCase):
    def test_ga_runtime_is_reported_for_release_gated_combo(self):
        assessment = compatibility.classify_runtime(netbox_version="4.5.7", python_version=(3, 12))

        self.assertEqual(assessment.status, "ga")
        self.assertIn("verified release-gating combination", assessment.message)

    def test_supported_python_on_untested_patch_is_beta(self):
        assessment = compatibility.classify_runtime(netbox_version="4.5.3", python_version=(3, 12))

        self.assertEqual(assessment.status, "beta")
        self.assertIn("not release-gated", assessment.message)

    def test_newer_python_inside_documented_range_is_best_effort(self):
        assessment = compatibility.classify_runtime(netbox_version="4.5.7", python_version=(3, 13))

        self.assertEqual(assessment.status, "best_effort")
        self.assertIn("not release-gated", assessment.message)

    def test_out_of_line_netbox_is_unsupported(self):
        assessment = compatibility.classify_runtime(netbox_version="4.6.0", python_version=(3, 12))

        self.assertEqual(assessment.status, "unsupported")
        self.assertIn("outside the supported 4.5.x release line", assessment.message)

    def test_runtime_warning_is_emitted_for_non_ga_combinations(self):
        with patch("warnings.warn") as warn:
            assessment = compatibility.emit_runtime_compatibility_warning(
                netbox_version="4.5.7",
                python_version=(3, 13),
            )

        self.assertEqual(assessment.status, "best_effort")
        warn.assert_called_once()
