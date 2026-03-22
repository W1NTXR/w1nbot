from __future__ import annotations

from pathlib import Path


TEXT_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PRIORITY_FILENAMES = {
    "readme",
    "readme.md",
    "checklist.md",
    "notion_import.md",
    "notion_tasks.csv",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "cargo.toml",
    "go.mod",
}
IGNORED_DIRS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "venv",
}


class RepoContextBuilder:
    def __init__(
        self,
        repo_path: Path,
        *,
        max_files: int = 12,
        max_chars_per_file: int = 4000,
    ) -> None:
        self.repo_path = repo_path
        self.max_files = max_files
        self.max_chars_per_file = max_chars_per_file

    def build(self) -> dict:
        files = self._select_files()
        return {
            "path": str(self.repo_path.resolve()),
            "is_git_repo": (self.repo_path / ".git").exists(),
            "selected_files": [self._read_file(path) for path in files],
        }

    def _select_files(self) -> list[Path]:
        candidates: list[tuple[int, str, Path]] = []
        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not self._is_text_candidate(path):
                continue
            rel_path = path.relative_to(self.repo_path).as_posix()
            candidates.append((self._priority(path), rel_path, path))

        candidates.sort(key=lambda item: (item[0], item[1]))
        return [path for _, _, path in candidates[: self.max_files]]

    def _is_text_candidate(self, path: Path) -> bool:
        name = path.name.lower()
        if name in PRIORITY_FILENAMES:
            return True
        return path.suffix.lower() in TEXT_EXTENSIONS

    def _priority(self, path: Path) -> int:
        rel = path.relative_to(self.repo_path)
        name = path.name.lower()
        if name in PRIORITY_FILENAMES:
            return 0
        if len(rel.parts) == 1:
            return 1
        return 2

    def _read_file(self, path: Path) -> dict:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > self.max_chars_per_file:
            content = content[: self.max_chars_per_file].rstrip() + "\n... [truncated]"
        return {
            "path": path.relative_to(self.repo_path).as_posix(),
            "content": content,
        }
