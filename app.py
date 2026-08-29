"""Streamlit approval interface for the churn-risk HITL workflow."""

from uuid import uuid4

import streamlit as st
from langgraph.checkpoint.memory import MemorySaver

from audit import load_audit_entries
from graph import CONFIDENCE_THRESHOLD, build_graph, create_initial_state


def _get_workflow():
    """Keep one in-memory checkpointed graph for the Streamlit session."""

    if "workflow_graph" not in st.session_state:
        st.session_state.workflow_graph = build_graph(MemorySaver())
    return st.session_state.workflow_graph


def _current_config() -> dict[str, dict[str, str]] | None:
    """Return the config for the active workflow thread, if one exists."""

    thread_id = st.session_state.get("thread_id")
    if not thread_id:
        return None
    return {"configurable": {"thread_id": thread_id}}


def _show_flash_message() -> None:
    """Show a one-time result after Streamlit reruns."""

    message = st.session_state.pop("flash_message", None)
    message_type = st.session_state.pop("flash_type", "success")
    if message:
        getattr(st, message_type)(message)


def _start_workflow(
    customer_id: str,
    total_operating_income: float,
    churn_probability: float,
) -> None:
    """Start a new checkpointed workflow thread."""

    workflow = _get_workflow()
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = create_initial_state(
        customer_id=customer_id,
        total_operating_income=total_operating_income,
        churn_probability=churn_probability,
    )
    workflow.invoke(initial_state, config)
    st.session_state.thread_id = thread_id


def _resume_workflow(decision: str, reviewer_id: str, edited_action: str) -> None:
    """Apply a human decision to pending state and resume execution."""

    workflow = _get_workflow()
    config = _current_config()
    if config is None:
        raise RuntimeError("No active workflow thread")

    update: dict[str, str] = {
        "human_decision": decision,
        "reviewer_id": reviewer_id,
    }
    if decision == "edit":
        update["edited_action"] = edited_action

    workflow.update_state(config, update)
    workflow.invoke(None, config)


def _render_customer_form() -> None:
    """Render customer inputs and start a new evaluation."""

    with st.form("customer-evaluation-form"):
        st.subheader("Thông tin khách hàng")
        customer_id = st.text_input("Customer ID", value="CUST001")
        total_operating_income = st.number_input(
            "Total Operating Income (VND)",
            min_value=0.0,
            value=600_000_000.0,
            step=10_000_000.0,
            format="%.0f",
        )
        churn_probability = st.slider(
            "Churn probability",
            min_value=0.0,
            max_value=1.0,
            value=0.80,
            step=0.01,
        )
        submitted = st.form_submit_button(
            "Đánh giá khách hàng",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not customer_id.strip():
            st.error("Customer ID không được để trống.")
            return
        try:
            _start_workflow(
                customer_id.strip(),
                total_operating_income,
                churn_probability,
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Không thể chạy workflow: {exc}")


def _render_action_card(values: dict[str, object]) -> None:
    """Display the agent proposal and reasoning."""

    with st.container(border=True):
        customer_col, action_col, confidence_col = st.columns(3)
        customer_col.metric("Customer ID", str(values["customer_id"]))
        action_col.metric("Proposed action", str(values["proposed_action"]))
        confidence_col.metric(
            "Confidence",
            f"{float(values['confidence_score']):.0%}",
        )
        st.markdown("**Agent reasoning**")
        st.write(values["reasoning"])


def _render_human_review(values: dict[str, object]) -> None:
    """Render Approve, Reject, and Edit controls for pending state."""

    st.warning("Workflow đang tạm dừng trước hành động và chờ human review.")
    reviewer_id = st.text_input(
        "Reviewer ID",
        placeholder="Ví dụ: operator_01",
    ).strip()
    edited_action = st.text_input(
        "Action sau khi chỉnh sửa",
        value=str(values["proposed_action"]),
        help="Giá trị này chỉ được dùng khi bấm Edit.",
    ).strip()

    approve_col, reject_col, edit_col = st.columns(3)
    approve_clicked = approve_col.button(
        "Approve",
        type="primary",
        width="stretch",
    )
    reject_clicked = reject_col.button("Reject", width="stretch")
    edit_clicked = edit_col.button("Edit", width="stretch")

    decision = None
    if approve_clicked:
        decision = "approve"
    elif reject_clicked:
        decision = "reject"
    elif edit_clicked:
        decision = "edit"

    if decision is None:
        return
    if not reviewer_id:
        st.error("Bạn phải nhập Reviewer ID trước khi đưa ra quyết định.")
        return
    if decision == "edit" and not edited_action:
        st.error("Action sau khi chỉnh sửa không được để trống.")
        return

    try:
        _resume_workflow(decision, reviewer_id, edited_action)
        st.session_state.flash_message = (
            f"Đã ghi nhận quyết định '{decision}' và tiếp tục workflow."
        )
        st.session_state.flash_type = "success"
        st.rerun()
    except Exception as exc:
        st.error(f"Không thể tiếp tục workflow: {exc}")


def _render_active_workflow() -> None:
    """Render pending review state or the completed execution result."""

    config = _current_config()
    if config is None:
        st.info("Chưa có workflow nào được chạy trong phiên này.")
        return

    snapshot = _get_workflow().get_state(config)
    values = dict(snapshot.values)
    if not values:
        st.info("Không tìm thấy state cho workflow hiện tại.")
        return

    st.subheader("Kết quả đánh giá")
    _render_action_card(values)

    if "execute_high_risk_action" in snapshot.next:
        _render_human_review(values)
    elif values.get("execution_result"):
        st.success(str(values["execution_result"]))


def _render_audit_trail() -> None:
    """Show newest audit decisions first."""

    st.divider()
    heading_col, refresh_col = st.columns([4, 1])
    heading_col.subheader("Audit trail")
    refresh_col.button("Làm mới", width="stretch")

    try:
        entries = load_audit_entries()
    except (OSError, ValueError) as exc:
        st.error(f"Không thể đọc audit log: {exc}")
        return

    if not entries:
        st.info("Audit log chưa có quyết định nào.")
        return

    st.dataframe(entries[::-1], width="stretch", hide_index=True)


def main() -> None:
    """Run the Streamlit application."""

    st.set_page_config(
        page_title="Churn Risk HITL",
        page_icon="🧑‍⚖️",
        layout="wide",
    )
    st.title("Churn Risk Human-in-the-Loop")
    st.caption(
        f"Confidence threshold: {CONFIDENCE_THRESHOLD:.0%} · "
        "increase_credit_limit luôn yêu cầu human review"
    )
    _show_flash_message()

    input_column, workflow_column = st.columns([1, 1.4], gap="large")
    with input_column:
        _render_customer_form()
    with workflow_column:
        _render_active_workflow()

    _render_audit_trail()


if __name__ == "__main__":
    main()
