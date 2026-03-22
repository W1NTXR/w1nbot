from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from textwrap import dedent

from repo_context import RepoContextBuilder


def call_codex(messages):
    print("\n--- CONTEXT SENT TO CODEX ---\n")
    for message in messages:
        print(f"{message['role'].upper()}: {message['content']}\n")
    response = input("Paste Codex response:\n")
    return response


class CodexClient:
    def __init__(
        self,
        target_repo_path: Path,
        discussion_command: str | None = None,
        report_command: str | None = None,
        execution_command: str | None = None,
    ) -> None:
        self.default_target_repo_path = target_repo_path
        self.target_repo_path = target_repo_path
        self.discussion_command = discussion_command
        self.report_command = report_command
        self.execution_command = execution_command
        self.repo_context_builder = RepoContextBuilder(target_repo_path)

    def discuss(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        self._set_active_repo_path(project_memory)
        messages = [
            {"role": "system", "content": DISCUSSION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(task, project_memory, task_memory),
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.discussion_command)

    def generate_plan_report(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        self._set_active_repo_path(project_memory)
        messages = [
            {"role": "system", "content": PLAN_REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(task, project_memory, task_memory),
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.report_command)

    def execute(self, task: dict, project_memory: dict, task_memory: dict) -> str:
        self._set_active_repo_path(project_memory)
        messages = [
            {"role": "system", "content": EXECUTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(task, project_memory, task_memory),
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
        self._set_active_repo_path(project_memory)
        messages = [
            {"role": "system", "content": FINAL_REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(
                        task,
                        project_memory,
                        task_memory,
                        execution_output=execution_output,
                    ),
                    indent=2,
                ),
            },
        ]
        return self._run(messages, self.report_command)

    def assess_report_readiness(
        self,
        task: dict,
        project_memory: dict,
        task_memory: dict,
    ) -> dict:
        self._set_active_repo_path(project_memory)
        messages = [
            {"role": "system", "content": REPORT_READINESS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(task, project_memory, task_memory),
                    indent=2,
                ),
            },
        ]
        response = self._run(messages, self.report_command)
        return json.loads(response)

    def _build_payload(
        self,
        task: dict,
        project_memory: dict,
        task_memory: dict,
        *,
        execution_output: str | None = None,
    ) -> dict:
        payload = {
            "target_repository": self.repo_context_builder.build(),
            "task": task,
            "project_memory": project_memory,
            "task_memory": task_memory,
        }
        if execution_output is not None:
            payload["execution_output"] = execution_output
        return payload

    def _set_active_repo_path(self, project_memory: dict) -> None:
        repo_value = (project_memory.get("target_repo_path") or "").strip()
        repo_path = Path(repo_value).expanduser() if repo_value else self.default_target_repo_path
        self.target_repo_path = repo_path
        self.repo_context_builder = RepoContextBuilder(repo_path)

    def _run(self, messages: list[dict], command: str | None) -> str:
        if command:
            payload = json.dumps(messages)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as output_file:
                output_path = Path(output_file.name)
            try:
                command = self._with_target_repo(command)
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

    def _with_target_repo(self, command: str) -> str:
        target = str(self.target_repo_path)
        c_arg = f'-C "{target}"'
        if re.search(r"(?<!\S)-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)", command):
            return re.sub(
                r"(?<!\S)-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)",
                c_arg,
                command,
                count=1,
            )
        exec_match = re.search(r"(?<!\S)exec(?!\S)", command)
        if exec_match:
            return f"{command[:exec_match.end()]} {c_arg}{command[exec_match.end():]}"
        return f"{command} {c_arg}"


DISCUSSION_SYSTEM_PROMPT = dedent(
    """
    You are a senior software engineer in discussion mode.
    Understand the task deeply before implementation.
    Ask focused clarifying questions.
    Use the target_repository snapshot first, then project memory and task memory,
    to avoid repeating prior discussion and to stay grounded in the actual repo.
    Treat project_memory.project_goal as the core product intent and avoid steering
    the work away from it unless the task explicitly requires that change.
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
    with the target repository context and project memory. Summarize what was
    changed, what was validated, and any blockers or remaining risks.
    Do not drift from project_memory.project_goal unless the task explicitly
    overrides it.
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

REPORT_READINESS_SYSTEM_PROMPT = dedent(
    """
    Review the task discussion and decide whether any critical implementation or
    planning questions remain unresolved.

    Return strict JSON only.
    If there is an unresolved question, return:
    {"status":"needs_answer","question":"...","proposed_answer":"..."}

    If the discussion is ready for report generation, return:
    {"status":"ready"}

    The proposed_answer should be the most logical answer consistent with the
    target repository and project_memory.project_goal.
    """
).strip()
