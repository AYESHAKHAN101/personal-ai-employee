# Personal AI Employee (Bronze Tier)

A deterministic, local-first AI assistant that operates as an autonomous employee within an Obsidian vault. The system processes tasks through a structured file-based workflow with human-in-the-loop approval for sensitive actions.

## Overview

The Personal AI Employee is designed around three core principles:

1. **Local-First Architecture** - All operations occur within the local filesystem. No cloud dependencies for core workflow execution.
2. **File-Move Workflow** - State transitions are expressed through file movement between folders, making all state changes visible and auditable.
3. **Human-in-the-Loop** - Sensitive actions (emails, payments, external communications) always require explicit human approval.

## Quick Start

### Prerequisites

- Python 3.12+
- [Watchdog](https://pypi.org/project/watchdog/) library
- Claude Code CLI (for AI processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/Personal-AI-Employee_GIAIC.git
cd Personal-AI-Employee_GIAIC

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install watchdog
```

### Running the System

#### 1. Start the Filesystem Watcher

```bash
cd watcher
python filesystem_watcher.py
```

The watcher will:
- Scan the `Drop_Zone/` folder for existing files (backlog processing)
- Monitor for new files dropped into the folder
- Generate task files in `AI_Employee_Vault/Needs_Action/`

#### 2. Process Tasks with Claude Code

```bash
cd AI_Employee_Vault
claude  # Start Claude Code CLI
```

Claude Code will automatically read `CLAUDE.md` and operate according to the Bronze Tier operational contract.

## Folder Structure

```
/Personal-AI-Employee_GIAIC/
├── Drop_Zone/                    # Drop files here for processing
│   └── processed/                # Processed files moved here
├── watcher/
│   └── filesystem_watcher.py     # File monitoring service
├── AI_Employee_Vault/            # Main Obsidian vault
│   ├── Dashboard.md              # Real-time status summary
│   ├── Needs_Action/             # Incoming tasks from watcher
│   ├── In_Progress/              # Claimed, active tasks
│   ├── Plans/                    # Execution plans
│   ├── Pending_Approval/         # Items awaiting human approval
│   ├── Approved/                 # Human-approved actions
│   │   └── archive/              # Processed approval files
│   ├── Rejected/                 # Human-rejected actions
│   │   └── archive/              # Processed rejection files
│   ├── Done/                     # Completed tasks and plans
│   ├── Logs/                     # JSON log files by date
│   ├── Quarantine/               # Malformed or suspicious files
│   └── Briefings/                # Generated reports
├── CLAUDE.md                     # AI operational contract
└── README.md                     # This file
```

## Workflow Lifecycle

### Task Flow

```
Drop_Zone → Needs_Action → In_Progress → Plans → Pending_Approval → Done
                                                        ↓
                                              Approved or Rejected
```

### State Transitions

| From | To | Trigger |
|------|-----|---------|
| `Drop_Zone` | `Needs_Action` | File detected by watcher |
| `Needs_Action` | `In_Progress` | Task claimed by AI |
| `In_Progress` | `Plans` | Plan created |
| `Plans` | `Pending_Approval` | Approval required |
| `Pending_Approval` | `Approved` | Human moves file |
| `Pending_Approval` | `Rejected` | Human moves file |
| `Approved` | `Done` | Action executed |
| `Rejected` | `Done` | Task terminated |

## Human-in-the-Loop Approval

### Actions Requiring Approval

The system will **always** request approval for:
- Sending any email
- Sending any message (WhatsApp, Slack, etc.)
- Any payment or financial transaction
- Any external API call with side effects
- File deletion
- Any action involving new/unknown recipients

### How to Approve/Reject

1. Review the approval request in `/Pending_Approval/`
2. To **approve**: Move the file to `/Approved/`
3. To **reject**: Move the file to `/Rejected/`

The system will detect the file movement and proceed accordingly.

### Approval File Format

```yaml
---
type: approval_request
action: email
task_id: FILE_example_abc123
created: 2026-03-03T10:30:00Z
expires: 2026-03-04T10:30:00Z
status: pending
priority: medium
---

## Action Details
Send invoice to client...

## Parameters
| Parameter | Value |
|-----------|-------|
| recipient | client@example.com |
| amount | $500.00 |

## Instructions
- **To Approve:** Move this file to `/Approved`
- **To Reject:** Move this file to `/Rejected`
```

## Task ID Generation

The system generates deterministic task IDs using SHA-256 content hashing:

```
FILE_{original_filename_stem}_{sha256_hash[:16]}
```

Example: `FILE_test_invoice_request_c33b36d1c134d19e`

This ensures:
- Idempotency (same file = same ID)
- No duplicate processing
- Traceable audit trail

## Logging

All actions are logged to `/Logs/YYYY-MM-DD.json`:

```json
{
  "timestamp": "2026-03-03T10:30:00Z",
  "action_type": "task_completed",
  "actor": "claude_code",
  "task_id": "FILE_example_abc123",
  "result": "success"
}
```

## Security Guardrails

The Bronze Tier enforces strict security boundaries:

| Allowed | Prohibited |
|---------|------------|
| Read files in vault | Execute external API calls autonomously |
| Create plans | Send emails without approval |
| Write approval requests | Process payments without approval |
| Move files between folders | Modify files outside vault |
| Update Dashboard | Access or store credentials |
| Write logs | Auto-approve sensitive actions |

## Configuration

### CLAUDE.md

The `CLAUDE.md` file serves as the operational contract for the AI. It defines:
- Authority boundaries
- Workflow rules
- File formats
- Error handling procedures
- Security guardrails

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DRY_RUN` | Skip actual execution (testing) | `false` |
| `WATCH_DIR` | Directory to monitor | `../Drop_Zone` |
| `VAULT_DIR` | Obsidian vault path | `../AI_Employee_Vault` |

## Testing

### Quick Workflow Test

1. Drop a text file into `Drop_Zone/`:
   ```bash
   echo "Send invoice to ACME Corp for $1000" > Drop_Zone/invoice_request.txt
   ```

2. Start the watcher:
   ```bash
   python watcher/filesystem_watcher.py
   ```

3. Check `AI_Employee_Vault/Needs_Action/` for the generated task file

4. Start Claude Code and process the task

5. Review and approve/reject in `Pending_Approval/`

### Test Scenarios

| Scenario | File Content | Expected Behavior |
|----------|--------------|-------------------|
| Invoice | "Send invoice for $500" | Creates approval request |
| Meeting | "Schedule meeting Tuesday 2pm" | Creates approval request |
| Ambiguous | "Handle that thing" | Creates clarification request |
| Internal | "Update project status" | No approval needed |

## Troubleshooting

### Common Issues

**Watcher not detecting files:**
- Ensure watchdog is installed: `pip install watchdog`
- Check file permissions on `Drop_Zone/`
- Verify the watcher is running

**Files stuck in Needs_Action:**
- Start Claude Code in the vault directory
- Check `Dashboard.md` for status

**Approval files not processing:**
- Ensure files are moved to `/Approved/` or `/Rejected/` (not copied)
- Check file permissions

### Logs

Review logs for debugging:
```bash
cat AI_Employee_Vault/Logs/$(date +%Y-%m-%d).json | jq .
```

## Tier Roadmap

| Tier | Status | Features |
|------|--------|----------|
| Bronze | Current | Local-first, file-based, single watcher |
| Silver | Planned | Multiple watchers, basic MCP integration |
| Gold | Planned | Full MCP tooling, automated approvals for trusted actions |
| Platinum | Planned | Multi-agent coordination, advanced reasoning |

## Contributing

Contributions are welcome! Please ensure:
1. All changes maintain human-in-the-loop for sensitive actions
2. File-based workflow is preserved
3. Logging is comprehensive
4. Security guardrails are not weakened

## License

MIT License - See LICENSE file for details.

---

*Built with Claude Code as part of the GIAIC Personal AI Employee project.*
