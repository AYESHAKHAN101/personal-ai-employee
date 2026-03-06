---
type: approval_request
action: calendar_invite
task_id: FILE_test_multi_1_7815cb9ee0bb58f1
plan_id: PLAN_FILE_test_multi_1_7815cb9ee0bb58f1
created: 2026-03-03T13:45:00+00:00
expires: 2026-03-04T13:45:00+00:00
status: approved
approved_at: 2026-03-03T13:50:00+00:00
priority: medium
risk_level: low
---

# Approval Request: Schedule Client Meeting

## Action Details

Send a calendar invitation to schedule a meeting with client.

## Parameters

| Parameter | Value |
|-----------|-------|
| Action Type | Calendar Invite |
| Recipient | Client (unspecified) |
| Date | Next Tuesday |
| Time | 2:00 PM |
| Duration | 1 hour (assumed) |
| Location | TBD |

## Calendar Invite Preview

```
Meeting: Client Meeting
Date: Tuesday, March 11, 2026
Time: 2:00 PM - 3:00 PM
Location: [To be determined]

Attendees:
- [Your Name]
- [Client Contact]

Agenda:
- [Meeting agenda to be added]
```

## Risk Assessment

**Risk Level: LOW**

- External calendar invite
- No financial impact
- Meeting can be rescheduled if needed

## Instructions

- **To Approve:** Move this file to `/Approved`
- **To Reject:** Move this file to `/Rejected`

## Auto-Expiry

This request expires at **2026-03-04T13:45:00+00:00**.
If not actioned, it will be moved to `/Expired` automatically.
