from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from textwrap import dedent


def call_codex(messages):
    print("\n--- CONTEXT SENT TO CODEX ---\n")
    for message in messages:
        print(f"{message['role'].upper()}: {message['content']}\n")
    response = input("Paste Codex response:\n")
    return response


class CodexClient:
    def __init__(
        self,
        discussion_command: str | None = None,
        report_command: str | None = None,
        execution_command: str | None = None,
    ) -> None:
        self.discussion_command = discussion_command
        self.report_command = report_command
        self.execution_command = execution_command

    def discuss(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        messages = [
            {"role": "system", "content": DISCUSSION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "project_memory": project_memory,
                        "task_memory": task_memory,
                    },
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.discussion_command)

    def generate_plan_report(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        messages = [
            {"role": "system", "content": PLAN_REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "project_memory": project_memory,
                        "task_memory": task_memory,
                    },
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.report_command)

    def execute(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        messages = [
            {"role": "system", "content": EXECUTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "project_memory": project_memory,
                        "task_memory": task_memory,
                    },
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.execution_command)

    def generate_final_report(
        self,
        task: dict,
        project_memory: dict,
        task_memory: dict,
        execution_output: str,
    ) -> str:
        messages = [
            {"role": "system", "content": FINAL_REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "project_memory": project_memory,
                        "task_memory": task_memory,
                        "execution_output": execution_output,
                    },
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.report_command)

    def _run(self, messages: list[dict], command: str | None) -> str:
        if command:
            payload = json.dumps(messages)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as output_file:
                output_path = Path(output_file.name)
            try:
                result = subprocess.run(
                    f'{command} -o "{output_path}"',
                    input=payload,
                    text=True,
                    capture_output=True,
                    shell=True,
                    check=False,
                )
                if result.returncode != 0:
                    stderr = result.stderr.strip() or "Unknown Codex command error."
                    raise RuntimeError(stderr)

                response = output_path.read_text(encoding="utf-8").strip()
                if response:
                    return response

                stdout = result.stdout.strip()
                if stdout:
                    return stdout
                raise RuntimeError("Codex command returned no response.")
            finally:
                output_path.unlink(missing_ok=True)
        return call_codex(messages)


DISCUSSION_SYSTEM_PROMPT = dedent(
    """
    You are a senior software engineer in discussion mode.
    Understand the task deeply before implementation.
    Ask focused clarifying questions.
    Use project memory and task memory to avoid repeating prior discussion.
    Keep the reply concise and useful for Telegram.
    """
).strip()

PLAN_REPORT_SYSTEM_PROMPT = dedent(
    """
    The discussion has ended. Produce a structured planning summary with:
    1. Final agreed approach
    2. Key decisions made
    3. Implementation plan
    4. Risks / edge cases
    5. Next steps
    Keep it concise and execution-oriented.
    """
).strip()

EXECUTION_SYSTEM_PROMPT = dedent(
    """
    Implementation mode is active.
    Follow the agreed plan and keep changes minimal, production-ready, and aligned
    with project memory. Summarize what was changed, what was validated, and any
    blockers or remaining risks.
    """
).strip()

FINAL_REPORT_SYSTEM_PROMPT = dedent(
    """
    Generate the final task report with sections:
    1. Final agreed approach
    2. Key decisions
    3. Implementation plan followed
    4. Risks / edge cases
    5. Execution notes
    6. Review notes
    Keep it structured and concise.
    """
).strip()
