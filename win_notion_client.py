from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from notion_client import Client

from config import AppConfig, load_config
from utils import parse_iso_date


def _read_plain_text(items):
    if not items:
        return ""
    x = "".join(item.get("plain_text", "") for item in items)
    return x


def _read_select_name(property_value):
    if not property_value:
        return ""
    x = property_value.get("name", "")
    return x


def _read_status_name(property_value):
    if not property_value:
        return ""
    x = property_value.get("status", {}).get("name", "")
    return x


def _priority_rank(priority_name: str) -> int:
    order = {"P0": 0, "P1": 1, "P2": 2, "High": 3, "Medium": 4, "Low": 5}
    return order.get(priority_name, 99)


@dataclass(slots=True)
class NotionTask:
    id: str
    title: str
    notes: str
    priority: str
    due_date: str
    status: str
    url: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "notes": self.notes,
            "priority": self.priority,
            "due_date": self.due_date,
            "status": self.status,
            "url": self.url,
        }


class NotionWorkflowClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = Client(auth=config.notion_api_key)
        self.review_status = config.notion_review_status

    def fetch_actionable_tasks(self, today: date | None = None) -> list[dict]:
        current_date = today or date.today()
        results = self._query_results()
        print(len(results))
        tasks: list[NotionTask] = []
        for item in results:
            task = self._parse_task(item)
            if not task.title:
                continue
            if not self._is_actionable(task, current_date):
                continue
            tasks.append(task)

        tasks.sort(
            key=lambda task: (
                task.due_date or "9999-12-31",
                _priority_rank(task.priority),
                task.title.lower(),
            )
        )
        print(len(tasks))
        return [task.to_dict() for task in tasks]

    def update_task_status(self, page_id: str, status: str) -> None:
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.config.notion_status_property: {
                        "status": {"name": status}
                    }
                },
            )
        except Exception:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.config.notion_status_property: {
                        "select": {"name": status}
                    }
                },
            )

    def _query_results(self) -> list[dict]:
        results: list[dict] = []
        query_kwargs = {"page_size": 100}
        cursor = None


        if self.config.notion_data_source_id:
            response = self.client.data_sources.query(
                data_source_id=self.config.notion_data_source_id
            )
        
        else:
            response = self.client.databases.query(
                database_id=self.config.notion_database_id
            )
        
        results.extend(response.get("results", []))
        print(len(results))
        return  results

    def _parse_task(self, page: dict) -> NotionTask:
        
        properties = page.get("properties", {})
        title_prop = properties.get(self.config.notion_title_property, {})
        notes_prop = properties.get(self.config.notion_notes_property, {})
        priority_prop = properties.get(self.config.notion_priority_property, {})
        due_date_prop = properties.get(self.config.notion_due_date_property, {})
        status_prop = properties.get(self.config.notion_status_property, {})

        return NotionTask(
            id=page["id"],
            title=_read_plain_text(title_prop.get("title", [])),
            notes=_read_plain_text(notes_prop.get("rich_text", [])),
            priority=_read_select_name(priority_prop.get("select", {})),
            due_date=due_date_prop.get("date", {}).get("start", "") or "",
            status=_read_status_name(status_prop) or _read_select_name(status_prop.get("select", {})),
            url=page.get("url", ""),
        )

    def _is_actionable(self, task: NotionTask, current_date: date) -> bool:
        if task.status and task.status.lower() not in {
            status.lower() for status in self.config.actionable_statuses
        }:
            return False
        due = parse_iso_date(task.due_date)
        return due is None or due <= current_date


def get_today_tasks():
    client = NotionWorkflowClient(load_config())
    return client.fetch_actionable_tasks()


def main():
    print(type(get_today_tasks()))
    json.dumps(get_today_tasks(), indent=2)


if __name__ == "__main__":
    main()
