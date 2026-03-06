# Personal AI Employee — Bronze Tier

A local-first autonomous AI workflow system powered by Claude Code.

This project implements the **Bronze Tier Control Plane** of a Personal AI Employee — an AI system that monitors incoming work, generates structured plans, and coordinates tasks through a transparent file-based workflow.

The system is designed around **reliability, transparency, and human-in-the-loop control.**

---

# Architecture Overview

The system follows a simple control-plane architecture:

Watcher → Perception  
Orchestrator → Control Loop  
Claude CLI → Planning Engine  
Human → Approval Authority

```
Incoming Task
     │
     ▼
Drop_Zone / Needs_Action
     │
     ▼
Filesystem Watcher
     │
     ▼
Orchestrator (control loop)
     │
     ▼
Claude CLI
     │
     ▼
Plan Generation
     │
     ▼
Human Approval
     │
     ▼
Execution / Completion
```

---

# Key Features

• Local-first architecture (no cloud dependency)  
• File-based workflow engine  
• Structured Markdown plans  
• Human-in-the-loop approvals  
• Deterministic task lifecycle  
• Crash-safe orchestrator loop  
• Structured JSON logging  
• Recoverable workflow state

---

# Project Structure

```
personal-ai-employee/

AI_Employee_Vault/
│
├── Needs_Action/        # Incoming tasks
├── In_Progress/         # Claimed tasks
├── Plans/               # Generated execution plans
├── Pending_Approval/    # Awaiting human approval
├── Approved/
├── Rejected/
├── Done/                # Completed tasks
├── Logs/                # Structured JSON logs
├── Quarantine/          # Malformed files
│
└── Dashboard.md         # System activity summary


watcher/
└── filesystem_watcher.py

orchestrator.py

CLAUDE.md                # Operational contract
requirements.md
```

---

# Task Lifecycle

Tasks move through the system using **file-based state transitions**.

```
Needs_Action
      │
      ▼
In_Progress
      │
      ▼
Plans
      │
      ▼
Pending_Approval
      │
      ▼
Approved
      │
      ▼
Done
```

Each state transition is expressed through **file movement**, ensuring transparency and auditability.

---

# Claude Operational Contract

The system behavior is defined by:

```
CLAUDE.md
```

This document defines:

• authority boundaries  
• workflow lifecycle  
• security guardrails  
• approval requirements  
• error handling rules

It acts as the **operational brain** of the Personal AI Employee.

---

# Orchestrator

The orchestrator provides the **Bronze Tier control loop**.

Responsibilities:

• Start filesystem watcher  
• Monitor incoming tasks  
• Trigger Claude CLI processing  
• Write structured logs  
• Retry failed executions  
• Recover from transient failures

Execution loop:

```
Every 60 seconds:

1. Scan Needs_Action/
2. If tasks exist
3. Execute Claude CLI
4. Generate plans
5. Log results
```

---

# Watcher

The watcher monitors the filesystem for new tasks and deposits them into:

```
Needs_Action/
```

This acts as the **perception layer** of the system.

---

# Human-in-the-Loop Design

The system never performs sensitive actions automatically.

Actions requiring approval:

• sending emails  
• sending messages  
• financial transactions  
• external API calls  
• irreversible operations

Approvals are handled through:

```
Pending_Approval/
```

Users approve actions by moving files to:

```
Approved/
```

---

# Logging

All system activity is written as structured JSON logs:

```
AI_Employee_Vault/Logs/
```

Example log entry:

```
{
  "timestamp": "...",
  "component": "orchestrator",
  "event": "task_detected",
  "details": {...},
  "result": "success"
}
```

---

# Running the System

Start the orchestrator:

```
python orchestrator.py
```

Optional DRY RUN mode:

```
export DRY_RUN=true
python orchestrator.py
```

---

# Design Principles

This system follows several core principles:

**Local First**  
All operations occur within the local vault.

**Transparency**  
All state changes occur via file movement.

**Human Authority**  
No sensitive action executes without approval.

**Determinism**  
Workflow state is always observable.

**Resilience**  
Failures do not crash the system.

---

# Roadmap

Future tiers will expand the system:

Bronze  
• Local workflow orchestration

Silver  
• Multi-source watchers (Gmail, Slack)  
• Advanced task parsing

Gold  
• Multi-agent coordination  
• Autonomous task execution

---

# License

This project is intended for educational and experimental use.
