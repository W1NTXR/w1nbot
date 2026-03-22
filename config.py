from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _csv_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass(slots=True)
class AppConfig:
    target_repo_path: Path
    notion_api_key: str
    notion_database_id: str | None
    notion_data_source_id: str | None
    notion_title_property: str
    notion_notes_property: str
    notion_priority_property: str
    notion_due_date_property: str
    notion_status_property: str
    notion_review_status: str
    actionable_statuses: list[str] = field(default_factory=list)
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_poll_seconds: int = 20
    google_drive_folder_id: str | None = None
    google_drive_access_token: str | None = None
    codex_discussion_command: str | None = None
    codex_report_command: str | None = None
    codex_execution_command: str | None = None
    reports_dir: Path = Path("reports")
    memory_dir: Path = Path("memory")
    project_memory_path: Path = Path("memory") / "project_memory.json"


def load_config() -> AppConfig:
    load_dotenv()

    target_repo_path = Path(os.getenv("TARGET_REPO_PATH", os.getcwd())).expanduser()
    memory_dir = Path(os.getenv("MEMORY_DIR", "memory"))
    config = AppConfig(
        target_repo_path=target_repo_path,
        notion_api_key=os.getenv("NOTION_API_KEY", ""),
        notion_database_id=os.getenv("NOTION_DATABASE_ID"),
        notion_data_source_id=os.getenv("NOTION_DATA_SOURCE_ID"),
        notion_title_property=os.getenv("NOTION_TITLE_PROPERTY", "Task"),
        notion_notes_property=os.getenv("NOTION_NOTES_PROPERTY", "Notes"),
        notion_priority_property=os.getenv("NOTION_PRIORITY_PROPERTY", "Priority"),
        notion_due_date_property=os.getenv("NOTION_DUE_DATE_PROPERTY", "Due Date"),
        notion_status_property=os.getenv("NOTION_STATUS_PROPERTY", "Status"),
        notion_review_status=os.getenv("NOTION_REVIEW_STATUS", "Review"),
        actionable_statuses=_csv_list(
            os.getenv("NOTION_ACTIONABLE_STATUSES"),
            ["Current", "Pending", "In Progress", "Todo"],
        ),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        telegram_poll_seconds=int(os.getenv("TELEGRAM_POLL_SECONDS", "20")),
        google_drive_folder_id=os.getenv("GOOGLE_DRIVE_FOLDER_ID"),
        google_drive_access_token=os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN"),
        codex_discussion_command=os.getenv("CODEX_DISCUSSION_COMMAND"),
        codex_report_command=os.getenv("CODEX_REPORT_COMMAND"),
        codex_execution_command=os.getenv("CODEX_EXECUTION_COMMAND"),
        reports_dir=Path(os.getenv("REPORTS_DIR", "reports")),
        memory_dir=memory_dir,
        project_memory_path=Path(
            os.getenv("PROJECT_MEMORY_PATH", str(memory_dir / "project_memory.json"))
        ),
    )

    if not config.notion_api_key:
        raise ValueError("Missing NOTION_API_KEY in environment.")
    if not (config.notion_data_source_id or config.notion_database_id):
        raise ValueError("Missing NOTION_DATA_SOURCE_ID or NOTION_DATABASE_ID.")
    if not config.target_repo_path.exists():
        raise ValueError(
            f"Configured TARGET_REPO_PATH does not exist: {config.target_repo_path}"
        )
    if not config.target_repo_path.is_dir():
        raise ValueError(
            f"Configured TARGET_REPO_PATH is not a directory: {config.target_repo_path}"
        )

    config.memory_dir.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    config.project_memory_path.parent.mkdir(parents=True, exist_ok=True)
    return config
