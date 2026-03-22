from __future__ import annotations

from config import load_config
from codex_client import CodexClient
from executor import DiscussionExecutor
from google_drive_store import GoogleDriveReportStore
from memory import ProjectMemoryStore, TaskMemoryStore
from reporter import Reporter
from telegram_client import TelegramClient
from win_notion_client import NotionWorkflowClient


def main() -> None:
    config = load_config()
    if not config.telegram_bot_token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN.")

    notion_client = NotionWorkflowClient(config)
    task_memory_store = TaskMemoryStore(config.memory_dir)
    project_memory_store = ProjectMemoryStore(config.project_memory_path)
    reporter = Reporter(config.reports_dir)
    telegram_client = TelegramClient(
        config.telegram_bot_token,
        config.telegram_chat_id,
        config.telegram_poll_seconds,
    )
    drive_store = GoogleDriveReportStore(
        config.google_drive_access_token,
        config.google_drive_folder_id,
    )
    codex_client = CodexClient(
        target_repo_path=config.target_repo_path,
        discussion_command=config.codex_discussion_command,
        report_command=config.codex_report_command,
        execution_command=config.codex_execution_command,
    )

    executor = DiscussionExecutor(
        telegram_client=telegram_client,
        notion_client=notion_client,
        task_memory_store=task_memory_store,
        project_memory_store=project_memory_store,
        reporter=reporter,
        drive_store=drive_store,
        codex_client=codex_client,
    )
    executor.run()


if __name__ == "__main__":
    main()
