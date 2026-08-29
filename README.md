# Lab 27 - Human-in-the-Loop với LangGraph

Ứng dụng đánh giá churn risk, đề xuất retention action và dùng Human-in-the-Loop
để ngăn agent tự thực hiện hành động rủi ro cao. Project không cần API key vì
node reasoning được mô phỏng bằng logic deterministic.

## Luồng xử lý

```text
Customer data
     |
     v
evaluate_customer
     |
     v
route_action -- low-risk + confidence >= 0.85 --> auto execute
     |
     +-- policy override / confidence < 0.85 --> interrupt
                                                   |
                                          Approve / Reject / Edit
                                                   |
                                                   v
                                                resume
                                                   |
                                                   v
                                              audit_log.json
```

Graph dùng `MemorySaver` và được compile với:

```python
interrupt_before=["execute_high_risk_action"]
```

Vì vậy high-risk node chưa được chạy trước khi reviewer đưa ra quyết định.

## Tính năng

- `GraphState` lưu customer data, agent proposal, confidence và human decision.
- `AuditEntry` kiểm tra cấu trúc audit bằng Pydantic.
- Agent reasoning trả về action, confidence score và reasoning.
- Confidence routing kết hợp hard policy rule.
- Pending state tồn tại xuyên suốt interrupt nhờ `MemorySaver`.
- Streamlit hỗ trợ Approve, Reject và Edit.
- Audit log giữ lại cả auto-execute và quyết định của reviewer.
- Bộ kiểm thử bao phủ schema, routing, interrupt/resume, UI và audit history.

## Cấu trúc project

```text
.
|-- app.py              # Streamlit approval interface
|-- audit.py            # Đọc và append audit trail
|-- graph.py            # Nodes, routing, MemorySaver và graph compilation
|-- models.py           # GraphState và AuditEntry
|-- audit_log.json      # Audit trail cục bộ
|-- requirements.txt   # Dependency đã ghim phiên bản
|-- tests/
|   |-- test_app.py     # Streamlit component test
|   `-- test_graph.py   # Schema, routing, workflow và audit tests
`-- README.md
```

## Yêu cầu và cài đặt

- Python 3.10 trở lên.

Trên PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Project không sử dụng API key, access token hoặc credential.

## Chạy Streamlit

```powershell
streamlit run app.py
```

Mở URL Streamlit hiển thị trong terminal, thường là `http://localhost:8501`.

Quy trình sử dụng:

1. Nhập Customer ID, Total Operating Income và churn probability.
2. Bấm **Đánh giá khách hàng**.
3. Low-risk đủ confidence sẽ được auto-execute.
4. Trường hợp cần review sẽ hiển thị agent reasoning và ba lựa chọn:
   - **Approve:** đồng ý action gốc.
   - **Reject:** hủy action.
   - **Edit:** nhập action mới rồi thực thi action đã chỉnh sửa.
5. Reviewer phải nhập Reviewer ID trước khi đưa ra quyết định.

## Agent reasoning và routing rules

Confidence threshold hiện tại là `0.85`.

| Điều kiện mock | Proposed action | Confidence | Kết quả |
|---|---|---:|---|
| Churn >= 0.75 và TOI >= 500,000,000 | `increase_credit_limit` | 0.96 | Human review |
| Churn >= 0.50, không thỏa điều kiện trên | `send_email` | 0.90 | Auto-execute |
| Churn < 0.50 | `send_email` | 0.82 | Human review |

Hard policy được kiểm tra trước confidence:

```text
increase_credit_limit -> luôn human review
```

Ngay cả confidence `0.99` cũng không được bypass policy. Action không xác định
cũng được chuyển sang human review theo nguyên tắc an toàn.

Ba bộ dữ liệu có thể dùng để kiểm tra nhanh:

| Kịch bản | TOI | Churn probability | Kết quả mong đợi |
|---|---:|---:|---|
| Auto-execute | 100,000,000 | 0.65 | `send_email` tự thực thi |
| Confidence thấp | 100,000,000 | 0.40 | Pending human review |
| Policy override | 900,000,000 | 0.90 | Pending human review |

## Audit trail

Audit được lưu tại `audit_log.json`. Mỗi quyết định mới được append vào danh
sách hiện có bằng thao tác ghi file tạm rồi thay thế, tránh làm mất lịch sử nếu
quá trình ghi bị gián đoạn.

Mỗi entry chứa:

```json
{
  "timestamp": "2026-08-29T09:00:00+00:00",
  "agent_id": "churn-risk-agent",
  "action": "increase_credit_limit",
  "confidence": 0.96,
  "reviewer_id": "operator_01",
  "decision": "approve"
}
```

Low-risk tự thực thi được ghi với `reviewer_id="system"` và
`decision="auto_execute"`. Approve, Reject và Edit đều ghi reviewer thật.

## Chạy kiểm thử

Không cần cài thêm testing framework:

```powershell
python -m unittest discover -s tests -v
```

Bộ test không ghi vào `audit_log.json` thật; mỗi test sử dụng file tạm riêng.

## Reflection Questions

### 1. Rewrite email trước routing: interrupt before hay interrupt after?

Dùng `interrupt_after` đối với node generate email. Node phải chạy xong để email
tồn tại trong state, sau đó graph dừng để con người rewrite trước khi routing
node được chạy. Cách diễn đạt tương đương là interrupt trước routing node, nhưng
nếu lựa chọn theo node generate email thì `interrupt_after=["generate_email"]`
là đúng với thời điểm cần dừng.

### 2. Giảm alert fatigue khi 500 email có confidence 0.82

Thay đổi cụ thể là tạo review queue theo batch, gom các email tương tự thành một
nhóm và cho reviewer duyệt mẫu đại diện hoặc bulk approve. Architecture nên thêm
một vùng uncertainty và calibration: chỉ các trường hợp có rủi ro hoặc dữ liệu
bất thường mới cần review từng item; email low-risk có thể được sampling để kiểm
tra chất lượng. UI cần sắp xếp theo risk, giải thích lý do bị flag và hỗ trợ phím
tắt/bulk action để giảm thời gian xử lý.

Không nên chỉ hạ threshold để làm biến mất cảnh báo, vì việc đó che giấu vấn đề
confidence chưa được hiệu chỉnh.

### 3. Vì sao không thể tin hoàn toàn self-reported confidence của LLM?

Confidence do LLM tự báo không phải xác suất đã được hiệu chỉnh. Model có thể
rất tự tin dù dùng sai thu nhập, thiếu dữ liệu hoặc gặp input ngoài phân phối.
Hard policy vì thế phải độc lập với confidence.

Trước routing, có thể calibrate bằng tập dữ liệu validation có nhãn: so sánh
prediction với kết quả thật, đo reliability/Brier score rồi dùng Platt scaling
hoặc isotonic regression để ánh xạ raw score sang xác suất thực nghiệm. Score
cuối cũng nên kết hợp data-quality checks, rule-based evidence và cơ chế đưa
trường hợp ngoài phân phối sang human review.

## Giới hạn của bản lab

- `MemorySaver` chỉ lưu state trong bộ nhớ của process hiện tại.
- `audit_log.json` phù hợp demo cục bộ, chưa phù hợp nhiều process đồng thời.
- Production nên dùng persistent checkpointer và append-only database có phân
  quyền reviewer, transaction và cơ chế chống sửa lịch sử.
