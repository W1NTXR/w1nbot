from __future__ import annotations
from datetime import date
from pathlib import Path
from textwrap import dedent

from git_workflow import GitWorkflow
from utils import parse_iso_date, utc_now_iso


class DiscussionExecutor:
    def __init__(
        self,
        telegram_client,
        notion_client,
        task_memory_store,
        project_memory_store,
        reporter,
        drive_store,
        codex_client,
    ) -> None:
        self.telegram = telegram_client
        self.notion = notion_client
        self.task_memory_store = task_memory_store
        self.project_memory_store = project_memory_store
        self.reporter = reporter
        self.drive_store = drive_store
        self.codex = codex_client

    def run(self) -> None:
        project_memory = self.project_memory_store.load()
        active_task: dict | None = None
        task_memory: dict | None = None
        session: dict | None = None
        pending_task: dict | None = None
        task_browser: dict | None = None
        init_state: dict | None = None
        report_state: dict | None = None
        awaiting_abort_confirmation = False

        self.telegram.send_message(self._idle_intro(project_memory))

        while True:
            message_text = self.telegram.wait_for_command_or_message()
            command = message_text.strip().lower()

            if init_state:
                project_memory, init_state = self._handle_init_message(
                    message_text,
                    project_memory,
                    init_state,
                )
                continue

            if report_state and active_task and task_memory:
                task_memory, report_state = self._handle_report_resolution(
                    project_memory,
                    active_task,
                    task_memory,
                    report_state,
                    session,
                    message_text,
                )
                continue

            if pending_task:
                if command in {"/confirm start", "confirm start", "yes", "y"}:
                    active_task, task_memory, session = self._begin_task(
                        project_memory,
                        pending_task,
                    )
                    pending_task = None
                    task_browser = None
                    continue
                if command in {"no", "n"} and task_browser:
                    pending_task = None
                    self.telegram.send_message(self._task_browser_message(project_memory, task_browser))
                    continue
                pending_task = None
                if task_browser:
                    self.telegram.send_message(self._task_browser_message(project_memory, task_browser))
                    continue
                self.telegram.send_message("Task start cancelled.")
                continue

            if task_browser:
                selection = self._handle_task_browser_input(
                    message_text,
                    task_browser,
                )
                if selection["action"] == "pick":
                    pending_task = selection["task"]
                    self.telegram.send_message(self._task_confirmation(project_memory, pending_task))
                    continue
                if selection["action"] == "browse":
                    self.telegram.send_message(self._task_browser_message(project_memory, task_browser))
                    continue
                task_browser = None
                self.telegram.send_message("Task selection cancelled.")
                continue

            if awaiting_abort_confirmation:
                if command in {"/confirm abort", "confirm abort", "yes", "y"}:
                    if active_task and session:
                        self._abort_session(project_memory, active_task, session)
                        active_task = None
                        task_memory = None
                        session = None
                        report_state = None
                    else:
                        self.telegram.send_message("No active task session to abort.")
                    awaiting_abort_confirmation = False
                    continue
                awaiting_abort_confirmation = False
                self.telegram.send_message("Abort cancelled. Session is still active.")
                continue

            if command == "/init":
                init_state = {"step": "project_name"}
                self.telegram.send_message("Send the project name for this bot workspace.")
                continue

            if command in {"/start", "start"}:
                if not project_memory.get("project_name"):
                    self.telegram.send_message("Run `/init` first so the bot knows which project to use.")
                    continue
                if active_task:
                    self.telegram.send_message(
                        f'Already working on "{active_task["title"]}". Use `/done` or `/abort` first.'
                    )
                    continue
                tasks = self.notion.fetch_actionable_tasks()
                if not tasks:
                    self.telegram.send_message("No actionable tasks found.")
                    continue
                task_browser = self._create_task_browser(tasks, date.today())
                if not task_browser:
                    self.telegram.send_message(
                        "No tasks are due today or earlier outside `In Review` and `Done`."
                    )
                    continue
                self.telegram.send_message(self._task_browser_message(project_memory, task_browser))
                continue

            if command in {"/abort", "/kill", "/killswitch"}:
                awaiting_abort_confirmation = True
                self.telegram.send_message(
                    "Abort is armed. Reply with `/confirm abort` to restore memory/report state for the active session."
                )
                continue

            if command in {"/status"}:
                self.telegram.send_message(
                    self._status_message(project_memory, active_task, task_memory)
                )
                continue

            if command in {"/gen_report", "gen_report"}:
                if not active_task or not task_memory:
                    self.telegram.send_message("No active task session. Use `/start` first.")
                    continue
                task_memory, report_state = self._generate_report_or_question(
                    project_memory,
                    active_task,
                    task_memory,
                    session,
                )
                continue

            if command in {"/implement", "implement"}:
                if not active_task or not task_memory or not session:
                    self.telegram.send_message("No active task session. Use `/start` first.")
                    continue
                try:
                    task_memory = self._implement(project_memory, active_task, task_memory, session)
                except Exception as exc:
                    self.telegram.send_message(f"Implementation failed: {exc}")
                continue

            if command in {"/done", "done"}:
                if not active_task or not task_memory or not session:
                    self.telegram.send_message("No active task session. Use `/start` first.")
                    continue
                try:
                    task_memory, report_state = self._done(
                        project_memory,
                        active_task,
                        task_memory,
                        session,
                    )
                    if report_state is None:
                        active_task = None
                        task_memory = None
                        session = None
                except Exception as exc:
                    self.telegram.send_message(f"Done failed: {exc}")
                continue

            if not active_task or not task_memory:
                self.telegram.send_message(
                    "Idle. Use `/init` to select a project or `/start` to pick the next task."
                )
                continue

            task_memory = self.task_memory_store.append_message(
                self._require_project_name(project_memory),
                active_task["id"],
                task_memory,
                "user",
                message_text,
            )
            reply = self.codex.discuss(active_task, project_memory, task_memory)
            task_memory = self.task_memory_store.append_message(
                self._require_project_name(project_memory),
                active_task["id"],
                task_memory,
                "assistant",
                reply,
            )
            self.telegram.send_message(reply)

    def _begin_task(
        self,
        project_memory: dict,
        task: dict,
    ) -> tuple[dict, dict, dict]:
        project_name = self._require_project_name(project_memory)
        task_memory = self.task_memory_store.load(project_name, task["id"], task)
        session = self._start_session(project_name, task)
        task_memory["workflow_state"] = "discussing"
        task_memory = self.task_memory_store.append_message(
            project_name,
            task["id"],
            task_memory,
            "user",
            self._task_start_prompt(task_memory),
        )
        try:
            reply = self.codex.discuss(task, project_memory, task_memory)
        except Exception as exc:
            task_memory["workflow_state"] = "discussion_failed"
            self.task_memory_store.save(project_name, task["id"], task_memory)
            self.telegram.send_message(
                f'Started task "{task["title"]}", but the initial discussion failed: {exc}'
            )
            return task, task_memory, session

        task_memory = self.task_memory_store.append_message(
            project_name,
            task["id"],
            task_memory,
            "assistant",
            reply,
        )
        self.telegram.send_message(reply)
        return task, task_memory, session

    def _implement(
        self,
        project_memory: dict,
        task: dict,
        task_memory: dict,
        session: dict,
    ) -> dict:
        project_name = self._require_project_name(project_memory)
        repo_path = self._require_repo_path(project_memory)
        git = GitWorkflow(repo_path)

        branch_info = task_memory.get("execution", {}).get("branch")
        if not branch_info:
            branch_info = git.prepare_branch(project_name, task)
            session["branch_name"] = branch_info["branch_name"]
            self.telegram.send_message(
                f'Created branch `{branch_info["branch_name"]}` from `{branch_info["base_ref"]}`.'
            )

        task_memory["workflow_state"] = "executing"
        task_memory["execution"] = {
            "started_at": utc_now_iso(),
            "branch": branch_info,
        }
        self.task_memory_store.save(project_name, task["id"], task_memory)

        execution_output = self.codex.execute(task, project_memory, task_memory)
        task_memory["execution"]["finished_at"] = utc_now_iso()
        task_memory["execution"]["output"] = execution_output
        task_memory["workflow_state"] = "implemented"
        self.task_memory_store.save(project_name, task["id"], task_memory)
        self.telegram.send_message(execution_output)
        return task_memory

    def _done(
        self,
        project_memory: dict,
        task: dict,
        task_memory: dict,
        session: dict,
    ) -> tuple[dict, dict | None]:
        project_name = self._require_project_name(project_memory)
        task_memory, report_state = self._ensure_report_ready(
            project_memory,
            task,
            task_memory,
            session,
        )
        if report_state is not None:
            return task_memory, report_state

        execution_output = ""
        if task_memory.get("execution"):
            execution_output = task_memory["execution"].get("output", "")

        final_report = self.codex.generate_final_report(
            task,
            project_memory,
            task_memory,
            execution_output or "No code changes were required.",
        )
        self._snapshot_report(project_name, task, "final", session)
        final_path = self.reporter.save_report(task, final_report, "final", project_name)
        drive_meta = self._upload_report(task_memory, final_path, session)
        if drive_meta:
            task_memory["drive_file"] = drive_meta

        repo_path = self._require_repo_path(project_memory)
        git = GitWorkflow(repo_path)
        pr_meta: dict | None = None
        if task_memory.get("execution", {}).get("branch"):
            branch = task_memory["execution"]["branch"]
            if git.has_uncommitted_changes():
                commit_sha = git.commit_all(f"{task['title']}")
                git.push_branch(branch["branch_name"])
                pr_meta = git.create_pr(
                    branch["base_branch"],
                    branch["branch_name"],
                    task["title"],
                    final_report,
                )
                task_memory["execution"]["commit_sha"] = commit_sha
                task_memory["execution"]["pr"] = pr_meta
                self.notion.update_task_status(task["id"], self.notion.review_status)

        task_memory["reports"].append(
            {"stage": "final", "path": str(final_path), "drive": drive_meta}
        )
        task_memory["workflow_state"] = "reviewed" if pr_meta else "reported"
        self.task_memory_store.save(project_name, task["id"], task_memory)

        message_lines = [f'Finished task "{task["title"]}".']
        if drive_meta and drive_meta.get("webViewLink"):
            message_lines.append(f'Report: {drive_meta["webViewLink"]}')
        if pr_meta:
            if pr_meta.get("pr_url"):
                message_lines.append(f'PR: {pr_meta["pr_url"]}')
            elif pr_meta.get("compare_url"):
                message_lines.append(f'Compare: {pr_meta["compare_url"]}')
            if pr_meta.get("error"):
                message_lines.append(f'PR creation note: {pr_meta["error"]}')
        self.telegram.send_message("\n".join(message_lines))
        return task_memory, None

    def _ensure_report_ready(
        self,
        project_memory: dict,
        task: dict,
        task_memory: dict,
        session: dict,
    ) -> tuple[dict, dict | None]:
        if task_memory.get("planning_summary"):
            return task_memory, None
        return self._generate_report_or_question(project_memory, task, task_memory, session)

    def _generate_report_or_question(
        self,
        project_memory: dict,
        task: dict,
        task_memory: dict,
        session: dict | None = None,
    ) -> tuple[dict, dict | None]:
        project_name = self._require_project_name(project_memory)
        readiness = self.codex.assess_report_readiness(task, project_memory, task_memory)
        if readiness.get("status") == "needs_answer":
            self.telegram.send_message(
                dedent(
                    f"""
                    Open question before report generation:
                    {readiness.get("question", "")}

                    Proposed answer:
                    {readiness.get("proposed_answer", "")}

                    Reply `yes` to accept, `no` to reject, or send a corrected answer.
                    """
                ).strip()
            )
            return task_memory, readiness

        plan_report = self.codex.generate_plan_report(task, project_memory, task_memory)
        task_memory["planning_summary"] = plan_report
        task_memory["workflow_state"] = "report_ready"
        if session is not None:
            self._snapshot_report(project_name, task, "plan", session)
        plan_path = self.reporter.save_report(task, plan_report, "plan", project_name)
        drive_meta = self._upload_report(task_memory, plan_path, session)
        task_memory["reports"].append({"stage": "plan", "path": str(plan_path), "drive": drive_meta})
        if drive_meta:
            task_memory["drive_file"] = drive_meta
        self.task_memory_store.save(project_name, task["id"], task_memory)
        self.telegram.send_message(plan_report)
        return task_memory, None

    def _handle_report_resolution(
        self,
        project_memory: dict,
        task: dict,
        task_memory: dict,
        report_state: dict,
        session: dict | None,
        message_text: str,
    ) -> tuple[dict, dict | None]:
        project_name = self._require_project_name(project_memory)
        command = message_text.strip().lower()
        if report_state.get("awaiting_manual"):
            resolution = message_text.strip()
        elif command in {"yes", "y"}:
            resolution = report_state.get("proposed_answer", "")
        elif command in {"no", "n"}:
            report_state["awaiting_manual"] = True
            self.telegram.send_message("Send the corrected answer you want kept in memory.")
            return task_memory, report_state
        else:
            resolution = message_text.strip()

        note = (
            f"Resolved open question: {report_state.get('question', '')}\n"
            f"Answer: {resolution}"
        )
        task_memory = self.task_memory_store.append_message(
            project_name,
            task["id"],
            task_memory,
            "assistant",
            note,
        )
        return self._generate_report_or_question(project_memory, task, task_memory, session)

    def _start_session(self, project_name: str, task: dict) -> dict:
        return {
            "task_id": task["id"],
            "project_name": project_name,
            "memory_snapshot": self.task_memory_store.snapshot(project_name, task["id"]),
            "report_snapshots": {},
            "created_drive_file_ids": set(),
            "branch_name": "",
        }

    def _snapshot_report(self, project_name: str, task: dict, stage: str, session: dict) -> Path:
        path = self.reporter.get_report_path(task, stage, project_name)
        key = str(path)
        if key in session["report_snapshots"]:
            return path

        if path.exists():
            session["report_snapshots"][key] = {
                "exists": True,
                "content": path.read_text(encoding="utf-8"),
            }
        else:
            session["report_snapshots"][key] = {"exists": False, "content": ""}
        return path

    def _abort_session(self, project_memory: dict, task: dict, session: dict) -> None:
        for file_id in session["created_drive_file_ids"]:
            try:
                self.drive_store.delete_report(file_id)
            except Exception as exc:
                self.telegram.send_message(
                    f"Memory was restored, but Drive file {file_id} could not be deleted: {exc}"
                )

        for path_str, snapshot in session["report_snapshots"].items():
            path = Path(path_str)
            if snapshot.get("exists"):
                path.write_text(snapshot.get("content", ""), encoding="utf-8")
            else:
                path.unlink(missing_ok=True)

        project_name = self._require_project_name(project_memory)
        self.task_memory_store.restore_snapshot(project_name, task["id"], session["memory_snapshot"])
        self.telegram.send_message(
            "Session aborted. Task memory and report artifacts were restored. Repo changes were left untouched."
        )

    def _upload_report(
        self,
        task_memory: dict,
        report_path: Path,
        session: dict | None = None,
    ) -> dict | None:
        try:
            drive_meta = task_memory.get("drive_file")
            if drive_meta and drive_meta.get("id"):
                return self.drive_store.upload_report(report_path, existing_file_id=drive_meta["id"])
            drive_meta = self.drive_store.upload_report(report_path)
            if session is not None and drive_meta.get("id"):
                session["created_drive_file_ids"].add(drive_meta["id"])
            return drive_meta
        except Exception as exc:
            self.telegram.send_message(f"Report saved locally, but Drive upload failed: {exc}")
            return None

    def _task_confirmation(self, project_memory: dict, task: dict) -> str:
        return dedent(
            f"""
            Selected task for project `{project_memory.get("project_name")}`:
            Title: {task["title"]}
            Status: {task.get("status") or "Unspecified"}
            Due: {task.get("due_date") or "Unspecified"}
            Priority: {task.get("priority") or "Unspecified"}

            Notes:
            {task.get("notes") or "No notes available."}

            Reply with `yes` or `/confirm start` to begin this task.
            Reply with `no` to return to the task list.
            """
        ).strip()

    def _task_start_prompt(self, task_memory: dict) -> str:
        if task_memory.get("discussion"):
            return dedent(
                """
                Task selected again from /start.
                Continue from the existing task memory.
                Ask only the highest-value remaining clarification if one is still unresolved.
                If no clarification is needed, give the next concrete action for this task.
                """
            ).strip()
        return dedent(
            """
            Task selected from /start.
            Begin the discussion now.
            Ask the smallest set of focused clarifying questions needed to proceed.
            If nothing important is unclear, say that directly and give the next concrete action.
            """
        ).strip()

    def _status_message(
        self,
        project_memory: dict,
        active_task: dict | None,
        task_memory: dict | None,
    ) -> str:
        lines = [
            f'Project: {project_memory.get("project_name") or "Not set"}',
            f'Repo: {project_memory.get("target_repo_path") or "Not set"}',
            f'Idea: {project_memory.get("project_goal") or "Not set"}',
        ]
        if active_task and task_memory:
            lines.extend(
                [
                    f'Active task: {active_task["title"]}',
                    f'State: {task_memory.get("workflow_state") or "idle"}',
                ]
            )
        else:
            lines.append("Active task: None")
        return "\n".join(lines)

    def _idle_intro(self, project_memory: dict) -> str:
        return dedent(
            f"""
            Bot ready.
            Active project: {project_memory.get("project_name") or "Not set"}
            Repo: {project_memory.get("target_repo_path") or "Not set"}

            Commands:
            /init
            /start
            /status
            /gen_report
            /implement
            /done
            /abort
            """
        ).strip()

    def _create_task_browser(self, tasks: list[dict], current_date: date) -> dict | None:
        eligible_tasks = []
        for task in tasks:
            due = parse_iso_date(task.get("due_date"))
            status = (task.get("status") or "").strip().lower()
            if due is None or due > current_date:
                continue
            if status in {"in review", "done"}:
                continue
            eligible_tasks.append(task)

        if not eligible_tasks:
            return None

        groups: list[dict] = []
        for task in eligible_tasks:
            due_value = task.get("due_date") or ""
            if groups and groups[-1]["due_date"] == due_value:
                groups[-1]["tasks"].append(task)
                continue
            groups.append({"due_date": due_value, "tasks": [task]})

        return {"groups": groups, "index": 0}

    def _handle_task_browser_input(self, message_text: str, task_browser: dict) -> dict:
        command = message_text.strip().lower()
        groups = task_browser["groups"]
        index = task_browser["index"]
        current_group = groups[index]

        if command in {"cancel", "/cancel"}:
            return {"action": "cancel"}
        if command in {"next", "n"}:
            if index < len(groups) - 1:
                task_browser["index"] = index + 1
            return {"action": "browse"}
        if command in {"back", "prev", "previous", "b"}:
            if index > 0:
                task_browser["index"] = index - 1
            return {"action": "browse"}
        if command.isdigit():
            choice = int(command)
            if 1 <= choice <= len(current_group["tasks"]):
                return {"action": "pick", "task": current_group["tasks"][choice - 1]}
        return {"action": "browse"}

    def _task_browser_message(self, project_memory: dict, task_browser: dict) -> str:
        groups = task_browser["groups"]
        index = task_browser["index"]
        current_group = groups[index]
        due_label = self._format_due_date(current_group["due_date"])

        lines = [
            f'Tasks for project `{project_memory.get("project_name")}`',
            f'Showing {len(current_group["tasks"])} task(s) due on {due_label}.',
            "",
        ]
        for position, task in enumerate(current_group["tasks"], start=1):
            priority = task.get("priority") or "Unspecified"
            lines.append(f'{position}. {task["title"]} [{priority}]')

        nav = []
        if index > 0:
            nav.append(f'`back` for {self._format_due_date(groups[index - 1]["due_date"])}')
        if index < len(groups) - 1:
            nav.append(f'`next` for {self._format_due_date(groups[index + 1]["due_date"])}')

        lines.extend(
            [
                "",
                "Reply with a task number to inspect it.",
            ]
        )
        if nav:
            lines.append("Navigation: " + ", ".join(nav))
        lines.append("Reply `cancel` to stop task selection.")
        return "\n".join(lines)

    def _format_due_date(self, due_value: str) -> str:
        due = parse_iso_date(due_value)
        if due is None:
            return due_value or "Unspecified"
        return due.strftime("%d/%m/%Y")

    def _handle_init_message(
        self,
        message_text: str,
        project_memory: dict,
        init_state: dict,
    ) -> tuple[dict, dict | None]:
        step = init_state["step"]
        if step == "project_name":
            project_name = message_text.strip()
            if not project_name:
                self.telegram.send_message("Project name cannot be empty. Send a valid project name.")
                return project_memory, init_state

            init_state["project_name"] = project_name
            if self.project_memory_store.project_exists(project_name):
                existing = self.project_memory_store.load_project(project_name)
                init_state["existing_project"] = existing
                self.telegram.send_message(
                    f'Project "{project_name}" already exists. No issue. Now send the repo path.'
                )
            else:
                self.telegram.send_message("Send the repo path for this project.")
            init_state["step"] = "repo_path"
            return project_memory, init_state

        if step == "repo_path":
            candidate = Path(message_text.strip()).expanduser()
            if candidate.exists():
                if not candidate.is_dir():
                    self.telegram.send_message("That path exists but is not a directory. Send another path.")
                    return project_memory, init_state
                init_state["target_repo_path"] = str(candidate.resolve())
                init_state["step"] = "project_goal"
                self.telegram.send_message(
                    "Repo confirmed. Now send the core project idea in 1 or 2 sentences."
                )
                return project_memory, init_state

            init_state["pending_repo_path"] = str(candidate)
            init_state["step"] = "create_repo_path"
            self.telegram.send_message(
                f"Path does not exist: {candidate}\nReply `yes` to create it or send another path."
            )
            return project_memory, init_state

        if step == "create_repo_path":
            command = message_text.strip().lower()
            if command in {"yes", "y"}:
                candidate = Path(init_state["pending_repo_path"]).expanduser()
                candidate.mkdir(parents=True, exist_ok=True)
                init_state["target_repo_path"] = str(candidate.resolve())
                init_state["step"] = "project_goal"
                self.telegram.send_message(
                    "Path created. Now send the core project idea in 1 or 2 sentences."
                )
                return project_memory, init_state

            init_state["step"] = "repo_path"
            self.telegram.send_message("Send another repo path.")
            return project_memory, init_state

        existing = init_state.get("existing_project") or {}
        updated_memory = dict(existing)
        updated_memory.update(
            {
                "project_name": init_state["project_name"],
                "target_repo_path": init_state["target_repo_path"],
                "project_goal": message_text.strip(),
            }
        )
        self.project_memory_store.save(updated_memory)
        self.telegram.send_message(
            dedent(
                f"""
                Project configuration updated.
                Name: {updated_memory["project_name"]}
                Repo: {updated_memory["target_repo_path"]}
                Idea: {updated_memory["project_goal"]}
                """
            ).strip()
        )
        return updated_memory, None

    def _require_project_name(self, project_memory: dict) -> str:
        project_name = (project_memory.get("project_name") or "").strip()
        if not project_name:
            raise RuntimeError("Project is not initialized. Run `/init` first.")
        return project_name

    def _require_repo_path(self, project_memory: dict) -> Path:
        repo_value = (project_memory.get("target_repo_path") or "").strip()
        if not repo_value:
            raise RuntimeError("Project repo path is not configured. Run `/init` first.")
        return Path(repo_value).expanduser()
