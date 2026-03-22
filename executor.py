from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from utils import utc_now_iso


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

    def run_task(self, task: dict) -> dict:
        project_memory = self.project_memory_store.load()
        task_memory = self.task_memory_store.load(task["id"], task)
        session = self._start_session(task)
        awaiting_abort_confirmation = False

        if not task_memory["discussion"]:
            self.telegram.send_message(self._task_intro(task, task_memory))

        task_memory["workflow_state"] = "discussing"
        self.task_memory_store.save(task["id"], task_memory)

        while True:
            message_text = self.telegram.wait_for_command_or_message()
            command = message_text.strip().lower()

            if awaiting_abort_confirmation:
                if command in {"/confirm abort", "confirm abort", "yes", "y"}:
                    return self._abort_session(task, session)
                awaiting_abort_confirmation = False
                self.telegram.send_message("Kill switch cancelled. Session is still active.")
                continue

            if command in {"/abort", "/kill", "/killswitch"}:
                awaiting_abort_confirmation = True
                self.telegram.send_message(
                    "Kill switch is armed. Reply with `/confirm abort` to erase this session and exit, or send any other message to cancel."
                )
                continue

            if command in {"end discussion", "/done"}:
                self._snapshot_report(task, "plan", session)
                plan_report = self.codex.generate_plan_report(task, project_memory, task_memory)
                plan_path = self.reporter.save_report(task, plan_report, "plan")
                task_memory["planning_summary"] = plan_report
                self.telegram.send_message(plan_report)
                try:
                    drive_meta = self.drive_store.upload_report(plan_path)
                    task_memory["workflow_state"] = "planned_waiting_approval"
                    task_memory["reports"].append(
                        {
                            "stage": "plan",
                            "path": str(plan_path),
                            "drive": drive_meta,
                        }
                    )
                    task_memory["drive_file"] = drive_meta
                    self._track_drive_file(drive_meta, session)
                    self.task_memory_store.save(task["id"], task_memory)
                    self.telegram.send_message(
                        self.reporter.telegram_summary(
                            task,
                            "planned_waiting_approval",
                            drive_meta.get("webViewLink"),
                        )
                    )
                except Exception as exc:
                    task_memory["workflow_state"] = "delivery_failed"
                    task_memory["reports"].append(
                        {
                            "stage": "plan",
                            "path": str(plan_path),
                            "drive": None,
                        }
                    )
                    self.task_memory_store.save(task["id"], task_memory)
                    self.telegram.send_message(
                        f"Plan report was saved locally but Google Drive upload failed: {exc}"
                    )
                continue

            if command in {"/status"}:
                self.telegram.send_message(
                    self.reporter.telegram_summary(task, task_memory["workflow_state"])
                )
                continue

            if command in {"/skip"}:
                task_memory["workflow_state"] = "skipped"
                self.task_memory_store.save(task["id"], task_memory)
                self.telegram.send_message(f'Skipped "{task["title"]}".')
                return task_memory

            if command in {"/implement", "/approve"}:
                if task_memory["workflow_state"] != "planned_waiting_approval":
                    self.telegram.send_message(
                        "Implementation is blocked until discussion is ended and the plan is generated."
                    )
                    continue
                return self._execute(task, project_memory, task_memory, session)

            if task_memory["workflow_state"] == "planned_waiting_approval":
                task_memory["workflow_state"] = "discussing"

            task_memory = self.task_memory_store.append_message(
                task["id"],
                task_memory,
                "user",
                message_text,
            )
            reply = self.codex.discuss(task, project_memory, task_memory)
            task_memory = self.task_memory_store.append_message(
                task["id"],
                task_memory,
                "assistant",
                reply,
            )
            self.telegram.send_message(reply)

    def _execute(
        self,
        task: dict,
        project_memory: dict,
        task_memory: dict,
        session: dict,
    ) -> dict:
        task_memory["workflow_state"] = "executing"
        task_memory["execution"] = {"started_at": utc_now_iso()}
        self.task_memory_store.save(task["id"], task_memory)

        execution_output = self.codex.execute(task, project_memory, task_memory)
        task_memory["execution"]["finished_at"] = utc_now_iso()
        task_memory["execution"]["output"] = execution_output

        final_report = self.codex.generate_final_report(
            task,
            project_memory,
            task_memory,
            execution_output,
        )
        self._snapshot_report(task, "final", session)
        final_path = self.reporter.save_report(task, final_report, "final")

        try:
            drive_meta = task_memory.get("drive_file")
            if drive_meta and drive_meta.get("id"):
                drive_meta = self.drive_store.upload_report(
                    final_path,
                    existing_file_id=drive_meta["id"],
                )
            else:
                drive_meta = self.drive_store.upload_report(final_path)
                self._track_drive_file(drive_meta, session)
        except Exception as exc:
            task_memory["workflow_state"] = "delivery_failed"
            task_memory["execution"]["delivery_error"] = str(exc)
            self.task_memory_store.save(task["id"], task_memory)
            self.telegram.send_message(
                f"Execution finished, but final report upload to Google Drive failed: {exc}"
            )
            return task_memory

        task_memory["reports"].append(
            {
                "stage": "final",
                "path": str(final_path),
                "drive": drive_meta,
            }
        )
        task_memory["drive_file"] = drive_meta
        task_memory["workflow_state"] = "reported"
        self.task_memory_store.save(task["id"], task_memory)

        self.telegram.send_message(
            self.reporter.telegram_summary(task, "reported", drive_meta.get("webViewLink"))
        )

        self.notion.update_task_status(task["id"], self.notion.review_status)
        task_memory["workflow_state"] = "reviewed"
        self.task_memory_store.save(task["id"], task_memory)
        self.telegram.send_message(
            dedent(
                f"""
                Task moved to Review in Notion.
                Report: {drive_meta.get('webViewLink')}
                """
            ).strip()
        )
        return task_memory

    def _start_session(self, task: dict) -> dict:
        return {
            "task_id": task["id"],
            "memory_snapshot": self.task_memory_store.snapshot(task["id"]),
            "report_snapshots": {},
            "created_drive_file_ids": set(),
        }

    def _snapshot_report(self, task: dict, stage: str, session: dict) -> Path:
        path = self.reporter.get_report_path(task, stage)
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

    def _track_drive_file(self, drive_meta: dict | None, session: dict) -> None:
        if not drive_meta:
            return
        file_id = drive_meta.get("id")
        if file_id:
            session["created_drive_file_ids"].add(file_id)

    def _abort_session(self, task: dict, session: dict) -> dict:
        for file_id in session["created_drive_file_ids"]:
            try:
                self.drive_store.delete_report(file_id)
            except Exception as exc:
                self.telegram.send_message(
                    f"Kill switch removed local session state, but failed to delete Google Drive file {file_id}: {exc}"
                )

        for path_str, snapshot in session["report_snapshots"].items():
            path = Path(path_str)
            if snapshot.get("exists"):
                path.write_text(snapshot.get("content", ""), encoding="utf-8")
            else:
                path.unlink(missing_ok=True)

        self.task_memory_store.restore_snapshot(task["id"], session["memory_snapshot"])
        self.telegram.send_message(
            "Session aborted. Current-session memory and report artifacts were removed, and no new state was kept."
        )
        return {"workflow_state": "aborted"}

    def _task_intro(self, task: dict, task_memory: dict) -> str:
        previous_summary = task_memory.get("planning_summary") or "None"
        return dedent(
            f"""
            Task selected for discussion:
            Title: {task['title']}
            Status: {task.get('status') or 'Unspecified'}
            Due: {task.get('due_date') or 'Unspecified'}
            Priority: {task.get('priority') or 'Unspecified'}

            Notes:
            {task.get('notes') or 'No notes available.'}

            Previous summary:
            {previous_summary}

            Reply with clarifications.
            Use `end discussion` or `/done` to close planning.
            Use `/implement` or `/approve` after planning to start execution.
            Use `/skip` to defer this task.
            Use `/abort` to erase this active session after confirmation.
            """
        ).strip()
