from __future__ import annotations

import json
from pathlib import Path

import httpx


class GoogleDriveReportStore:
    def __init__(self, access_token: str | None, folder_id: str | None) -> None:
        self.access_token = access_token
        self.folder_id = folder_id

    def upload_report(self, report_path: Path, existing_file_id: str | None = None) -> dict:
        if not self.access_token:
            raise RuntimeError("Missing GOOGLE_DRIVE_ACCESS_TOKEN.")
        metadata = {"name": report_path.name}
        if self.folder_id:
            metadata["parents"] = [self.folder_id]

        headers = {"Authorization": f"Bearer {self.access_token}"}
        with httpx.Client(timeout=60.0) as client:
            if existing_file_id:
                client.patch(
                    f"https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}",
                    params={"uploadType": "media"},
                    headers={
                        **headers,
                        "Content-Type": "text/markdown; charset=utf-8",
                    },
                    content=report_path.read_bytes(),
                ).raise_for_status()
                file_id = existing_file_id
            else:
                files = {
                    "metadata": ("metadata", json.dumps(metadata), "application/json"),
                    "file": (
                        report_path.name,
                        report_path.read_bytes(),
                        "text/markdown",
                    ),
                }
                response = client.post(
                    "https://www.googleapis.com/upload/drive/v3/files",
                    params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                    headers=headers,
                    files=files,
                )
                response.raise_for_status()
                created = response.json()
                file_id = created["id"]

                permission_response = client.post(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                    params={"fields": "id"},
                    headers=headers,
                    json={"role": "reader", "type": "anyone"},
                )
                permission_response.raise_for_status()

            details = client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"fields": "id,name,webViewLink,webContentLink"},
                headers=headers,
            )
            details.raise_for_status()
            return details.json()

    def delete_report(self, file_id: str) -> None:
        if not self.access_token:
            raise RuntimeError("Missing GOOGLE_DRIVE_ACCESS_TOKEN.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        with httpx.Client(timeout=60.0) as client:
            response = client.delete(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
            )
            response.raise_for_status()
