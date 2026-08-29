"""Tests for schemas, routing, checkpointing, decisions, and audit logging."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

import audit
from graph import (
    build_graph,
    create_initial_state,
    evaluate_customer,
    route_action,
)
from models import AuditEntry, GraphState


def make_config() -> dict[str, dict[str, str]]:
    """Return an isolated LangGraph thread configuration."""

    return {"configurable": {"thread_id": str(uuid4())}}


class SchemaAndRoutingTests(unittest.TestCase):
    """Verify the state contract and all routing rules."""

    def test_graph_state_contains_required_lab_fields(self) -> None:
        required_fields = {
            "customer_id",
            "proposed_action",
            "confidence_score",
            "reasoning",
            "human_decision",
        }
        self.assertTrue(required_fields.issubset(GraphState.__required_keys__))

    def test_audit_entry_validates_confidence_range(self) -> None:
        with self.assertRaises(ValidationError):
            AuditEntry(
                timestamp="2026-08-29T09:00:00+00:00",
                agent_id="churn-risk-agent",
                action="send_email",
                confidence=1.1,
                reviewer_id="system",
                decision="auto_execute",
            )

    def test_evaluate_customer_produces_expected_scenarios(self) -> None:
        scenarios = [
            (900_000_000, 0.90, "increase_credit_limit", 0.96),
            (100_000_000, 0.65, "send_email", 0.90),
            (100_000_000, 0.40, "send_email", 0.82),
        ]

        for income, churn, expected_action, expected_confidence in scenarios:
            with self.subTest(income=income, churn=churn):
                state = create_initial_state("CUST-TEST", income, churn)
                result = evaluate_customer(state)
                self.assertEqual(result["proposed_action"], expected_action)
                self.assertEqual(result["confidence_score"], expected_confidence)
                self.assertTrue(result["reasoning"])

    def test_hard_policy_overrides_confidence_099(self) -> None:
        state = create_initial_state("CUST-POLICY", 900_000_000, 0.90)
        state.update(
            proposed_action="increase_credit_limit",
            confidence_score=0.99,
        )
        self.assertEqual(route_action(state), "high_risk")

    def test_confidence_and_safe_fallback_routing(self) -> None:
        state = create_initial_state("CUST-ROUTE", 100_000_000, 0.65)
        state.update(proposed_action="send_email", confidence_score=0.90)
        self.assertEqual(route_action(state), "low_risk")

        state.update(confidence_score=0.82)
        self.assertEqual(route_action(state), "high_risk")

        state.update(proposed_action="unknown_action", confidence_score=0.99)
        self.assertEqual(route_action(state), "high_risk")

    def test_customer_signal_validation(self) -> None:
        invalid_churn = create_initial_state("CUST-BAD", 100_000_000, 1.2)
        with self.assertRaises(ValueError):
            evaluate_customer(invalid_churn)

        invalid_income = create_initial_state("CUST-BAD", -1, 0.50)
        with self.assertRaises(ValueError):
            evaluate_customer(invalid_income)


class WorkflowAndAuditTests(unittest.TestCase):
    """Verify interrupt/resume behavior and append-only audit history."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_audit_path = audit.AUDIT_LOG_PATH
        audit.AUDIT_LOG_PATH = (
            Path(self.temporary_directory.name) / "audit_log.json"
        )
        self.workflow = build_graph(MemorySaver())

    def tearDown(self) -> None:
        audit.AUDIT_LOG_PATH = self.original_audit_path
        self.temporary_directory.cleanup()

    def _run_reviewed_action(
        self,
        customer_id: str,
        decision: str,
        reviewer_id: str,
        edited_action: str | None = None,
    ) -> dict[str, object]:
        config = make_config()
        pending = self.workflow.invoke(
            create_initial_state(customer_id, 900_000_000, 0.90),
            config,
        )
        snapshot = self.workflow.get_state(config)

        self.assertIsNone(pending["execution_result"])
        self.assertEqual(snapshot.next, ("execute_high_risk_action",))
        self.assertEqual(snapshot.values["customer_id"], customer_id)

        update = {
            "human_decision": decision,
            "reviewer_id": reviewer_id,
        }
        if edited_action is not None:
            update["edited_action"] = edited_action

        self.workflow.update_state(config, update)
        result = self.workflow.invoke(None, config)
        self.assertEqual(self.workflow.get_state(config).next, ())
        return result

    def test_low_risk_action_auto_executes_and_is_audited(self) -> None:
        config = make_config()
        result = self.workflow.invoke(
            create_initial_state("CUST-AUTO", 100_000_000, 0.65),
            config,
        )

        self.assertIn("Auto-executed", result["execution_result"])
        self.assertEqual(self.workflow.get_state(config).next, ())

        entries = audit.load_audit_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["decision"], "auto_execute")
        self.assertEqual(entries[0]["reviewer_id"], "system")

    def test_low_confidence_action_is_interrupted(self) -> None:
        config = make_config()
        result = self.workflow.invoke(
            create_initial_state("CUST-LOW-CONFIDENCE", 100_000_000, 0.40),
            config,
        )

        self.assertEqual(result["proposed_action"], "send_email")
        self.assertEqual(result["confidence_score"], 0.82)
        self.assertIsNone(result["execution_result"])
        self.assertEqual(
            self.workflow.get_state(config).next,
            ("execute_high_risk_action",),
        )
        self.assertEqual(audit.load_audit_entries(), [])

    def test_approve_reject_and_edit_append_audit_history(self) -> None:
        approved = self._run_reviewed_action(
            "CUST-APPROVE",
            "approve",
            "operator_approve",
        )
        self.assertIn("after human approve", approved["execution_result"])

        rejected = self._run_reviewed_action(
            "CUST-REJECT",
            "reject",
            "operator_reject",
        )
        self.assertIn("Aborted", rejected["execution_result"])

        edited = self._run_reviewed_action(
            "CUST-EDIT",
            "edit",
            "operator_edit",
            edited_action="send_email",
        )
        self.assertIn("after human edit", edited["execution_result"])
        self.assertEqual(edited["proposed_action"], "send_email")

        entries = audit.load_audit_entries()
        self.assertEqual(
            [entry["decision"] for entry in entries],
            ["approve", "reject", "edit"],
        )
        self.assertEqual(entries[-1]["action"], "send_email")
        self.assertEqual(len(entries), 3)


if __name__ == "__main__":
    unittest.main()
