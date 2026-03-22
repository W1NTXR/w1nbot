from __future__ import annotations

from pathlib import Path

from utils import read_json, slugify, write_json


def _default_project_payload(project_name: str = "") -> dict:
    return {
        "project_name": project_name,
        "target_repo_path": "",
        "project_goal": "",
        "key_decisions": [],
        "constraints": [],
    }


class ProjectMemoryStore:
    def __init__(self, path: Path) -> None:
        self.active_project_path = path
        self.projects_dir = path.parent / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def project_exists(self, project_name: str) -> bool:
        return self._get_project_path(project_name).exists()

    def load(self) -> dict:
        active = read_json(self.active_project_path, {})
        project_name = active.get("active_project")
        if project_name:
            return self.load_project(project_name)

        legacy = read_json(self.active_project_path, _default_project_payload())
        if legacy.get("project_name"):
            return legacy
        return _default_project_payload()

    def load_project(self, project_name: str) -> dict:
        path = self._get_project_path(project_name)
        return read_json(path, _default_project_payload(project_name))

    def save(self, payload: dict) -> None:
        project_name = (payload.get("project_name") or "").strip()
        if not project_name:
            raise ValueError("project_name is required to save project memory.")

        normalized = dict(_default_project_payload(project_name))
        normalized.update(payload)
        write_json(self._get_project_path(project_name), normalized)
        write_json(self.active_project_path, {"active_project": project_name})

    def activate(self, project_name: str) -> dict:
        payload = self.load_project(project_name)
        self.save(payload)
        return payload

    def _get_project_path(self, project_name: str) -> Path:
        return self.projects_dir / f"{slugify(project_name)}.json"
