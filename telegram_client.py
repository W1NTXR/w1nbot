from __future__ import annotations
from dotenv import load_dotenv

import httpx


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        chat_id: str | None = None,
        poll_seconds: int = 20,
    ) -> None:
        self.chat_id = str(chat_id) if chat_id else None
        self.poll_seconds = poll_seconds
        self.offset = 0
        self.client = httpx.Client(timeout=poll_seconds + 10)
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str) -> None:
        if not self.chat_id:
            raise RuntimeError("TELEGRAM_CHAT_ID is required to send messages.")
        response = self.client.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": self.chat_id, "text": text},
        )
        response.raise_for_status()

    def wait_for_command_or_message(self) -> str:
        while True:
            response = self.client.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.offset, "timeout": self.poll_seconds},
            )
            response.raise_for_status()
            payload = response.json()
            for update in payload.get("result", []):
                self.offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                chat_id = str(message["chat"]["id"])
                if self.chat_id and chat_id != self.chat_id:
                    continue
                if not self.chat_id:
                    self.chat_id = chat_id
                text = (message.get("text") or "").strip()
                if text:
                    return text
