"""LangGraph workflow for churn-risk actions with HITL routing."""

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from models import GraphState

CONFIDENCE_THRESHOLD = 0.85
LOW_RISK_ACTION = "send_email"
HIGH_RISK_ACTION = "increase_credit_limit"

RouteName = Literal["low_risk", "high_risk"]


def create_initial_state(
    customer_id: str,
    total_operating_income: float,
    churn_probability: float,
) -> GraphState:
    """Create a complete initial state for one workflow run."""

    return {
        "customer_id": customer_id,
        "total_operating_income": total_operating_income,
        "churn_probability": churn_probability,
        "proposed_action": "",
        "confidence_score": 0.0,
        "reasoning": "",
        "human_decision": None,
        "execution_result": None,
    }


def evaluate_customer(state: GraphState) -> dict[str, object]:
    """Evaluate mock customer signals and propose a retention action.

    This deterministic implementation stands in for an LLM, so the workflow is
    reproducible and does not require an API key during the lab.
    """

    income = float(state["total_operating_income"])
    churn_probability = float(state["churn_probability"])

    if income < 0:
        raise ValueError("total_operating_income must be non-negative")
    if not 0.0 <= churn_probability <= 1.0:
        raise ValueError("churn_probability must be between 0.0 and 1.0")

    if churn_probability >= 0.75 and income >= 500_000_000:
        proposed_action = HIGH_RISK_ACTION
        confidence_score = 0.96
        reasoning = (
            "Customer has high churn probability and strong operating income; "
            "a credit-limit increase may improve retention but requires policy review."
        )
    elif churn_probability >= 0.50:
        proposed_action = LOW_RISK_ACTION
        confidence_score = 0.90
        reasoning = (
            "Customer has meaningful churn risk, while a retention email is a "
            "non-financial and low-risk intervention."
        )
    else:
        proposed_action = LOW_RISK_ACTION
        confidence_score = 0.82
        reasoning = (
            "Customer churn risk is not high enough for a confident intervention; "
            "the suggested email should be reviewed by a human."
        )

    return {
        "proposed_action": proposed_action,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "human_decision": None,
        "execution_result": None,
    }


def route_action(state: GraphState) -> RouteName:
    """Apply hard policy rules before confidence-based routing."""

    action = state["proposed_action"]
    confidence = state["confidence_score"]

    # Policy override always wins, even when the agent is highly confident.
    if action == HIGH_RISK_ACTION:
        return "high_risk"

    if action == LOW_RISK_ACTION and confidence >= CONFIDENCE_THRESHOLD:
        return "low_risk"

    # Low confidence and any unrecognized action are escalated for safety.
    return "high_risk"


def execute_low_risk_action(state: GraphState) -> dict[str, str]:
    """Auto-execute a low-risk action after routing checks pass."""

    return {
        "execution_result": (
            f"Auto-executed '{state['proposed_action']}' for "
            f"customer {state['customer_id']}."
        )
    }


def execute_high_risk_action(state: GraphState) -> dict[str, str]:
    """Execute or abort an interrupted action after a human decision."""

    decision = (state.get("human_decision") or "").strip().lower()
    if decision == "reject":
        result = (
            f"Aborted '{state['proposed_action']}' for "
            f"customer {state['customer_id']} after human rejection."
        )
    elif decision in {"approve", "edit"}:
        result = (
            f"Executed '{state['proposed_action']}' for "
            f"customer {state['customer_id']} after human {decision}."
        )
    else:
        raise ValueError(
            "A human_decision of 'approve', 'reject', or 'edit' is required "
            "before executing a reviewed action."
        )

    return {"execution_result": result}


def build_graph(checkpointer: MemorySaver | None = None):
    """Build and compile the workflow with a pre-action HITL interrupt."""

    builder = StateGraph(GraphState)
    builder.add_node("evaluate_customer", evaluate_customer)
    builder.add_node("execute_low_risk_action", execute_low_risk_action)
    builder.add_node("execute_high_risk_action", execute_high_risk_action)

    builder.add_edge(START, "evaluate_customer")
    builder.add_conditional_edges(
        "evaluate_customer",
        route_action,
        {
            "low_risk": "execute_low_risk_action",
            "high_risk": "execute_high_risk_action",
        },
    )
    builder.add_edge("execute_low_risk_action", END)
    builder.add_edge("execute_high_risk_action", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["execute_high_risk_action"],
    )


memory = MemorySaver()
graph = build_graph(memory)


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "GraphState",
    "build_graph",
    "create_initial_state",
    "evaluate_customer",
    "execute_high_risk_action",
    "execute_low_risk_action",
    "graph",
    "memory",
    "route_action",
]
