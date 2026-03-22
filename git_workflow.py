from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from utils import slugify


class GitWorkflow:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def prepare_branch(self, project_name: str, task: dict) -> dict:
        self._ensure_git_repo()
        if self.has_uncommitted_changes():
            raise RuntimeError(
                "Target repo has uncommitted changes. Commit or stash them before /implement."
            )

        self._run(["git", "fetch", "origin"], check=False)
        base_branch = self._resolve_base_branch()
        base_ref = self._resolve_base_ref(base_branch)
        branch_name = self._build_branch_name(project_name, task)

        if self._ref_exists(f"refs/heads/{branch_name}"):
            raise RuntimeError(f"Branch already exists: {branch_name}")

        self._run(["git", "checkout", "--detach", base_ref])
        self._run(["git", "switch", "-c", branch_name])
        return {"branch_name": branch_name, "base_branch": base_branch, "base_ref": base_ref}

    def has_uncommitted_changes(self) -> bool:
        result = self._run(["git", "status", "--porcelain"])
        return bool(result.stdout.strip())

    def commit_all(self, message: str) -> str:
        self._run(["git", "add", "-A"])
        self._run(["git", "commit", "-m", message])
        result = self._run(["git", "rev-parse", "HEAD"])
        return result.stdout.strip()

    def push_branch(self, branch_name: str) -> None:
        self._run(["git", "push", "-u", "origin", branch_name])

    def create_pr(self, base_branch: str, branch_name: str, title: str, body: str) -> dict:
        compare_url = self._build_compare_url(base_branch, branch_name)
        if shutil.which("gh"):
            result = self._run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base_branch,
                    "--head",
                    branch_name,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                check=False,
            )
            if result.returncode == 0:
                url = result.stdout.strip().splitlines()[-1]
                return {"pr_url": url, "compare_url": compare_url}
            return {
                "pr_url": "",
                "compare_url": compare_url,
                "error": result.stderr.strip() or result.stdout.strip(),
            }
        return {
            "pr_url": "",
            "compare_url": compare_url,
            "error": "GitHub CLI `gh` is not installed.",
        }

    def _ensure_git_repo(self) -> None:
        if not self.repo_path.exists():
            raise RuntimeError(f"Repo path does not exist: {self.repo_path}")
        if not (self.repo_path / ".git").exists():
            raise RuntimeError(f"Repo path is not a git repository: {self.repo_path}")

    def _resolve_base_branch(self) -> str:
        for candidate in ("main", "master"):
            if self._ref_exists(f"refs/remotes/origin/{candidate}") or self._ref_exists(
                f"refs/heads/{candidate}"
            ):
                return candidate
        raise RuntimeError("Could not find a `main` or `master` branch in the target repo.")

    def _resolve_base_ref(self, base_branch: str) -> str:
        remote_ref = f"origin/{base_branch}"
        if self._ref_exists(f"refs/remotes/{remote_ref}"):
            return remote_ref
        return base_branch

    def _ref_exists(self, ref_name: str) -> bool:
        result = self._run(["git", "show-ref", "--verify", "--quiet", ref_name], check=False)
        return result.returncode == 0

    def _build_branch_name(self, project_name: str, task: dict) -> str:
        task_slug = slugify(task.get("title") or task.get("id") or "task")
        project_slug = slugify(project_name or "project")
        return f"{project_slug}/{task_slug}"

    def _build_compare_url(self, base_branch: str, branch_name: str) -> str:
        remote_url = self._run(["git", "remote", "get-url", "origin"], check=False).stdout.strip()
        if remote_url.startswith("git@github.com:"):
            remote_url = remote_url.replace("git@github.com:", "https://github.com/")
        if remote_url.endswith(".git"):
            remote_url = remote_url[:-4]
        if remote_url.startswith("https://github.com/"):
            return f"{remote_url}/compare/{base_branch}...{branch_name}?expand=1"
        return ""

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "Git command failed."
            raise RuntimeError(stderr)
        return result
