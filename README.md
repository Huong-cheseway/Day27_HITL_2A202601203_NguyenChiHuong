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

Các bước tiếp theo sẽ bổ sung LangGraph workflow, giao diện Human-in-the-Loop,
audit logging và hướng dẫn chạy đầy đủ.
