# notion_client.py

import os
from datetime import date

from dotenv import load_dotenv
from notion_client import Client
import json

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID") or NOTION_DATABASE_ID
notion = Client(auth=NOTION_API_KEY)


def _read_plain_text(property_value):
    if not property_value:
        return ""
    return "".join(item.get("plain_text", "") for item in property_value)


def _priority_sort_value(priority_name):
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    return priority_order.get(priority_name, 99)


def get_today_tasks():
    if not NOTION_API_KEY:
        raise ValueError("Missing NOTION_API_KEY in environment.")
    if not NOTION_DATA_SOURCE_ID:
        raise ValueError(
            "Missing NOTION_DATA_SOURCE_ID in environment."
            " If you only have a database ID, fetch the data source ID from Notion first."
        )

    today = date.today().isoformat()

    response = notion.data_sources.query(
        data_source_id=NOTION_DATA_SOURCE_ID,
        filter={
            "and": [
                {"property": "Due Date", "date": {"before": today}},
            ]
        }
    )
    tasks_dict = response["results"]
    tasks = []
    for task in tasks_dict:
        properties = task.get("properties", {})
        t_title = _read_plain_text(properties.get("Task", {}).get("title", []))
        t_notes = _read_plain_text(properties.get("Notes", {}).get("rich_text", []))
        t_priority = properties.get("Priority", {}).get("select", {}).get("name", "")
        t_date = properties.get("Due Date", {}).get("date", {}).get("start", "")
        tasks.append({
            "title": t_title,
            "notes": t_notes,
            "priority": t_priority,
            "due_date": t_date,
        })

    tasks.sort(key=lambda task: (task["due_date"] or "9999-12-31", _priority_sort_value(task["priority"])))
    return tasks


def main():
    tasks = get_today_tasks()
    print(json.dumps(tasks, indent = 2))


if __name__ == "__main__":
    main()
