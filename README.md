# Cliffy

AI-enhanced shell with fast suggestions, safer execution, and task-oriented modes.

## Quick Start

1. Create and activate a virtual environment (example):
   `python -m venv env`
   `source env/bin/activate`
2. Install dependencies:
   `pip install -r requirements.txt`
3. Run:
   `./cliffy`

## Usage Overview

- `%`  Single command suggestion with inline edit
  - Prompts for a task, shows a suggested command inline, and lets you edit before running.
- `%%` Multi-step task execution with explanations
  - Breaks complex tasks into steps, shows a one-sentence explanation for each step, and asks before running.
- `%%%` Interactive coding mode
  - Generates code into files, auto-saves, and keeps output clean (no code printed to the terminal).
  - Supports new directory creation when requested in the task.
- `edit <path>` Agentic file edit
  - Paste a snippet, describe changes, and it updates the file in place.

## Notes

- Commands are echoed in a distinct color before execution.
- Destructive actions require confirmation and may trigger safety checks.
