from __future__ import annotations

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

        if not task_memory["discussion"]:
            self.telegram.send_message(self._task_intro(task, task_memory))

        task_memory["workflow_state"] = "discussing"
        self.task_memory_store.save(task["id"], task_memory)

        while True:
            message_text = self.telegram.wait_for_command_or_message()
            command = message_text.strip().lower()

            if command in {"end discussion", "/done"}:
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
                return self._execute(task, project_memory, task_memory)

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

    def _execute(self, task: dict, project_memory: dict, task_memory: dict) -> dict:
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
            """
        ).strip()
