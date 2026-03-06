---
type: approval_request
action: email
task_id: FILE_test_invoice_request_c33b36d1c134d19e
plan_id: PLAN_FILE_test_invoice_request_c33b36d1c134d19e
created: 2026-03-03T13:45:00+00:00
expires: 2026-03-04T13:45:00+00:00
status: approved
approved_at: 2026-03-03T13:50:00+00:00
priority: medium
risk_level: medium
---

# Approval Request: Send Invoice to ACME Corp

## Action Details

Send an invoice via email to client ACME Corp for March services.

## Parameters

| Parameter | Value |
|-----------|-------|
| Action Type | Email with Attachment |
| Recipient | ACME Corp (client) |
| Subject | Invoice for March Services |
| Amount | $4,500.00 |
| Payment Terms | Net 7 days |
| Due Date | 2026-03-10 |

## Email Preview

```
To: [ACME Corp contact email]
Subject: Invoice #2026-0301 - March Services

Dear ACME Corp,

Please find attached the invoice for March services.

Invoice Details:
- Invoice Number: 2026-0301
- Amount Due: $4,500.00
- Due Date: March 10, 2026
- Payment Terms: Net 7 days

Thank you for your business.

Best regards,
[Company Name]
```

## Risk Assessment

**Risk Level: MEDIUM**

- Sending email to external party
- Financial document attached
- Cannot be unsent once delivered

## Instructions

- **To Approve:** Move this file to `/Approved`
- **To Reject:** Move this file to `/Rejected`

## Auto-Expiry

This request expires at **2026-03-04T13:45:00+00:00**.
If not actioned, it will be moved to `/Expired` automatically.
