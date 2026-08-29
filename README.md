# Lab 27 - Human-in-the-Loop với LangGraph

Project xây dựng workflow đánh giá churn risk, áp dụng confidence routing,
hard policy rules, human approval và audit logging.

## Yêu cầu

- Python 3.10 trở lên

## Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Cấu trúc project

```text
.
|-- app.py             # Streamlit approval interface
|-- graph.py           # LangGraph state, nodes, routing và compilation
|-- models.py          # GraphState và AuditEntry
|-- audit_log.json     # Audit trail cục bộ
|-- requirements.txt  # Python dependencies
`-- README.md
```

## Chạy ứng dụng

```powershell
streamlit run app.py
```

Ứng dụng hiện hỗ trợ confidence routing, hard policy, checkpoint bằng
`MemorySaver`, Approve, Reject, Edit và audit logging vào `audit_log.json`.
README sẽ được hoàn thiện cùng bộ kiểm thử ở bước cuối.
