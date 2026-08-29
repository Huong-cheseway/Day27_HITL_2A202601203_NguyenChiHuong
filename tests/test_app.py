"""End-to-end component tests for the Streamlit approval interface."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from streamlit.testing.v1 import AppTest

import audit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StreamlitAppTests(unittest.TestCase):
    """Exercise the UI without starting an external browser or server."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_audit_path = audit.AUDIT_LOG_PATH
        audit.AUDIT_LOG_PATH = (
            Path(self.temporary_directory.name) / "audit_log.json"
        )

    def tearDown(self) -> None:
        audit.AUDIT_LOG_PATH = self.original_audit_path
        self.temporary_directory.cleanup()

    def _new_app(self) -> AppTest:
        app = AppTest.from_file(PROJECT_ROOT / "app.py").run(timeout=15)
        self.assertFalse(app.exception)
        return app

    def _start_high_risk_workflow(self) -> AppTest:
        app = self._new_app()
        app.button[0].click().run(timeout=15)
        self.assertFalse(app.exception)
        labels = {button.label for button in app.button}
        self.assertTrue({"Approve", "Reject", "Edit"}.issubset(labels))
        self.assertTrue(app.warning)
        return app

    def _click_decision(self, app: AppTest, decision: str) -> None:
        button = next(item for item in app.button if item.label == decision)
        button.click().run(timeout=15)
        self.assertFalse(app.exception)

    def test_auto_approve_reject_and_edit_flows(self) -> None:
        auto_app = self._new_app()
        auto_app.slider[0].set_value(0.65)
        auto_app.button[0].click().run(timeout=15)
        self.assertFalse(auto_app.exception)
        self.assertTrue(
            any("Auto-executed" in item.value for item in auto_app.success)
        )

        approve_app = self._start_high_risk_workflow()
        approve_app.text_input[1].set_value("operator_approve")
        self._click_decision(approve_app, "Approve")
        self.assertTrue(
            any("after human approve" in item.value for item in approve_app.success)
        )

        reject_app = self._start_high_risk_workflow()
        reject_app.text_input[1].set_value("operator_reject")
        self._click_decision(reject_app, "Reject")
        self.assertTrue(any("Aborted" in item.value for item in reject_app.success))

        edit_app = self._start_high_risk_workflow()
        edit_app.text_input[1].set_value("operator_edit")
        edit_app.text_input[2].set_value("send_email")
        self._click_decision(edit_app, "Edit")
        self.assertTrue(
            any("after human edit" in item.value for item in edit_app.success)
        )

        entries = audit.load_audit_entries()
        self.assertEqual(
            [entry["decision"] for entry in entries],
            ["auto_execute", "approve", "reject", "edit"],
        )
        self.assertEqual(entries[-1]["action"], "send_email")


if __name__ == "__main__":
    unittest.main()
