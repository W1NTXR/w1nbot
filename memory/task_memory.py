from __future__ import annotations

from pathlib import Path

from utils import read_json, utc_now_iso, write_json


class TaskMemoryStore:
    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def get_memory_path(self, task_id: str) -> Path:
        return self.memory_dir / f"{task_id}.json"

    def load(self, task_id: str, task_snapshot: dict | None = None) -> dict:
        payload = read_json(
            self.get_memory_path(task_id),
            {
                "task": task_snapshot or {},
                "workflow_state": "discussing",
                "discussion": [],
                "planning_summary": "",
                "reports": [],
                "drive_file": None,
                "execution": None,
                "updated_at": utc_now_iso(),
            },
        )
        if task_snapshot:
            payload["task"] = task_snapshot
        return payload

    def save(self, task_id: str, payload: dict) -> dict:
        payload["updated_at"] = utc_now_iso()
        write_json(self.get_memory_path(task_id), payload)
        return payload

    def append_message(self, task_id: str, payload: dict, role: str, content: str) -> dict:
        payload["discussion"].append({"role": role, "content": content, "at": utc_now_iso()})
        return self.save(task_id, payload)
