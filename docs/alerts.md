# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighAnswerLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: request có `response_sent` trong 3000 ms.
- Điều kiện và thời gian duy trì: P95 latency của `response_sent` > 3000 ms trong 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời đến chậm, tiêu hao error budget nếu vượt 3000 ms.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** mở panel Latency, xem P95/P99 và TTFT P95 trong 60 phút; xác định phút bắt đầu vượt ngưỡng.
  2. **Logs:** lọc `response_sent` trong phút đó, sắp theo `latency_ms`, lấy `correlation_id` của request chậm.
  3. **Traces:** tìm trace có cùng `correlation_id`, so thời lượng `retrieval` và `generation` để khoanh vùng.
- Mitigation tạm thời: nếu retrieval chậm, tắt practice scenario hoặc khôi phục backend truy xuất; nếu generation chậm sau đổi prompt, rollback label `production` về version ổn định và restart API.
- Owner: `student-2A202602765`

## Alert 2

- Tên: `ElevatedRequestErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: request thành công trong SLO; guardrail error rate ≤ 2%.
- Điều kiện và thời gian duy trì: `request_failed / request_received × 100 > 2%` trong 5 phút, tối thiểu 20 request để tránh nhiễu mẫu nhỏ.
- Ảnh hưởng tới người dùng: một phần request không nhận được câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** mở panel Errors, xác nhận error rate, số request và retrieval success; xem lỗi tăng ở phút nào.
  2. **Logs:** lọc `request_failed`, xem `error_type`, `tool_success` và `correlation_id` đại diện; so với `request_received` cùng khoảng.
  3. **Traces:** mở trace theo `correlation_id`, kiểm tra `retrieval` lỗi hay lỗi ở bước khác.
- Mitigation tạm thời: khôi phục dịch vụ truy xuất hoặc tắt practice `tool_fail`; nếu lỗi xuất hiện ngay sau thay đổi cấu hình, rollback cấu hình vừa đổi rồi gửi request kiểm tra.
- Owner: `student-2A202602765`

## Alert 3

- Tên: `AnswerQualityDegraded`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail quality proxy trung bình ≥ 0.75.
- Điều kiện và thời gian duy trì: trung bình `quality_score` của `response_sent` < 0.75 trong 10 phút, tối thiểu 20 response.
- Ảnh hưởng tới người dùng: câu trả lời có nguy cơ thiếu ngữ cảnh hoặc không phù hợp; đây là proxy nên cần xem mẫu thủ công.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** mở panel Quality, xác nhận mức giảm và đối chiếu Traffic để loại trừ mẫu quá nhỏ.
  2. **Logs:** lọc `response_sent` có `quality_score` thấp, xem `feature`, `tokens_in/out` và lấy `correlation_id` mà không đọc PII thô.
  3. **Traces:** tìm trace tương ứng, kiểm tra `retrieval` và `prompt_version` của `lab-agent-run` trước khi kết luận.
- Mitigation tạm thời: rollback `production` về prompt baseline nếu giảm chất lượng bắt đầu sau promote; kiểm tra corpus/retrieval và tắt practice scenario nếu đang bật.
- Owner: `student-2A202602765`
