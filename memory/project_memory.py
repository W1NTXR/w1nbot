from __future__ import annotations

from pathlib import Path

from utils import read_json, write_json


class ProjectMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        return read_json(
            self.path,
            {
                "project_goal": "",
                "key_decisions": [],
                "constraints": [],
            },
        )

    def save(self, payload: dict) -> None:
        write_json(self.path, payload)
