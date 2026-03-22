from __future__ import annotations

from pathlib import Path

from utils import read_json, slugify, utc_now_iso, write_json


def _default_task_payload(task_snapshot: dict | None = None) -> dict:
    return {
        "task": task_snapshot or {},
        "workflow_state": "idle",
        "discussion": [],
        "planning_summary": "",
        "reports": [],
        "drive_file": None,
        "execution": None,
        "updated_at": utc_now_iso(),
    }


class TaskMemoryStore:
    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def get_memory_path(self, project_name: str, task_id: str) -> Path:
        project_dir = self.memory_dir / "tasks" / slugify(project_name or "default")
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / f"{task_id}.json"

    def snapshot(self, project_name: str, task_id: str) -> dict:
        path = self.get_memory_path(project_name, task_id)
        if not path.exists():
            return {"exists": False, "content": ""}
        return {"exists": True, "content": path.read_text(encoding="utf-8")}

    def load(self, project_name: str, task_id: str, task_snapshot: dict | None = None) -> dict:
        payload = read_json(
            self.get_memory_path(project_name, task_id),
            _default_task_payload(task_snapshot),
        )
        if task_snapshot:
            payload["task"] = task_snapshot
        return payload

    def save(self, project_name: str, task_id: str, payload: dict) -> dict:
        payload["updated_at"] = utc_now_iso()
        write_json(self.get_memory_path(project_name, task_id), payload)
        return payload

    def restore_snapshot(self, project_name: str, task_id: str, snapshot: dict) -> None:
        path = self.get_memory_path(project_name, task_id)
        if snapshot.get("exists"):
            path.write_text(snapshot.get("content", ""), encoding="utf-8")
            return
        path.unlink(missing_ok=True)

    def append_message(
        self,
        project_name: str,
        task_id: str,
        payload: dict,
        role: str,
        content: str,
    ) -> dict:
        payload["discussion"].append({"role": role, "content": content, "at": utc_now_iso()})
        return self.save(project_name, task_id, payload)
