from __future__ import annotations

from pathlib import Path

from utils import slugify, utc_now_iso


class Reporter:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def get_report_path(self, task: dict, stage: str, project_name: str) -> Path:
        project_dir = self.reports_dir / slugify(project_name or "default")
        project_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{task['id']}-{stage}-{slugify(task['title'])}.md"
        return project_dir / filename

    def save_report(self, task: dict, report_body: str, stage: str, project_name: str) -> Path:
        path = self.get_report_path(task, stage, project_name)
        path.write_text(report_body, encoding="utf-8")
        return path

    def telegram_summary(self, task: dict, state: str, drive_link: str | None = None) -> str:
        lines = [
            f"Task: {task['title']}",
            f"State: {state}",
            f"Due: {task.get('due_date') or 'Unspecified'}",
            f"Priority: {task.get('priority') or 'Unspecified'}",
            f"Updated: {utc_now_iso()}",
        ]
        if drive_link:
            lines.append(f"Report: {drive_link}")
        return "\n".join(lines)
