"""
Feishu API client — authentication, send/receive messages.

Uses lark-oapi SDK. Credentials from .env (FEISHU_APP_ID, FEISHU_APP_SECRET).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lark_oapi import Client as LarkClient
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ListMessageRequest,
    ListMessageResponse,
    GetMessageRequest,
    GetMessageResponse,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

FEISHU_HOST = "https://open.feishu.cn"


class FeishuError(Exception):
    """Raised when a Feishu API call fails."""


@dataclass
class ChatMessage:
    message_id: str
    chat_id: str
    sender_id: str
    sender_name: str
    content: str
    msg_type: str
    sender_type: str = ""
    root_id: str | None = None  # non-empty if this is a reply to another message


def _get_credentials() -> tuple[str, str]:
    # Delegate .env loading to core.config (single source of truth)
    from core.config import _load_dotenv
    _load_dotenv(Path(__file__).resolve().parent.parent)

    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        raise FeishuError(
            "FEISHU_APP_ID and FEISHU_APP_SECRET must be set in .env. "
            "Create a Feishu app at https://open.feishu.cn."
        )
    return app_id, app_secret


class FeishuClient:
    """Wraps lark-oapi Client for message operations."""

    def __init__(self) -> None:
        app_id, app_secret = _get_credentials()
        self._client: LarkClient = LarkClient.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .build()

    def send_text(self, chat_id: str, text: str) -> str:
        """Send a text message to a chat. Returns message_id."""
        content = json.dumps({"text": text}, ensure_ascii=False)
        req = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(content)
                .build()) \
            .build()
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            raise FeishuError(f"Send text failed: code={resp.code}, msg={resp.msg}")
        return str(resp.data.message_id)

    def send_post(self, chat_id: str, title: str, paragraphs: list[list[dict[str, Any]]]) -> str:
        """Send a rich-text post message. Returns message_id.

        Args:
            chat_id: Target chat ID.
            title: Post title.
            paragraphs: List of paragraph lines, each a list of tag dicts.
                e.g. [[{"tag": "text", "text": "hello"}],
                      [{"tag": "a", "text": "link", "href": "https://..."}]]
        """
        content = json.dumps({"zh_cn": {"title": title, "content": paragraphs}}, ensure_ascii=False)
        req = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("post")
                .content(content)
                .build()) \
            .build()
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            raise FeishuError(f"Send post failed: code={resp.code}, msg={resp.msg}")
        return str(resp.data.message_id)

    def list_messages(self, chat_id: str, limit: int = 50) -> list[ChatMessage]:
        """List recent messages in a chat."""
        req = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id(chat_id) \
            .page_size(limit) \
            .sort_type("ByCreateTimeDesc") \
            .build()
        resp: ListMessageResponse = self._client.im.v1.message.list(req)
        if not resp.success():
            raise FeishuError(f"List messages failed: code={resp.code}, msg={resp.msg}")

        messages: list[ChatMessage] = []
        items = resp.data.items if resp.data and resp.data.items else []
        for item in items:
            msg_id = item.message_id or ""
            content = self._extract_text_content(msg_id)
            sender = item.sender
            sender_name = ""
            sender_id = ""
            if sender and hasattr(sender, "id"):
                sender_id = str(sender.id)
            if sender and hasattr(sender, "name"):
                sender_name = sender.name or ""
            sender_type = ""
            if sender and hasattr(sender, "sender_type"):
                sender_type = sender.sender_type or ""
            messages.append(ChatMessage(
                message_id=msg_id,
                chat_id=item.chat_id or chat_id,
                sender_id=sender_id,
                sender_name=sender_name or (f"user_{sender_id[-8:]}" if sender_id else ""),
                content=content,
                msg_type=item.msg_type or "unknown",
                sender_type=sender_type,
                root_id=item.root_id or None,
            ))
        return messages

    def get_message_content(self, message_id: str) -> str:
        """Get full message content as plain text."""
        req = GetMessageRequest.builder() \
            .message_id(message_id) \
            .build()
        resp: GetMessageResponse = self._client.im.v1.message.get(req)
        if not resp.success():
            raise FeishuError(f"Get message failed: code={resp.code}, msg={resp.msg}")

        items = resp.data.items if resp.data else []
        if not items:
            return ""

        item = items[0]
        body = item.body
        if not body:
            return ""

        content = body.content or ""
        msg_type = item.msg_type or ""

        if msg_type == "text":
            try:
                data = json.loads(content)
                return data.get("text", "")
            except json.JSONDecodeError:
                return content
        elif msg_type == "post":
            try:
                data = json.loads(content)
                return self._flatten_post(data)
            except json.JSONDecodeError:
                return content
        return content

    def _extract_text_content(self, message_id: str) -> str:
        """Extract plain text from a message (used in list_messages)."""
        try:
            return self.get_message_content(message_id)
        except Exception:
            return ""

    @staticmethod
    def _flatten_post(data: dict[str, Any]) -> str:
        """Flatten a post message into plain text."""
        lines: list[str] = []
        zh_cn = data.get("zh_cn", data)
        title = zh_cn.get("title", "")
        if title:
            lines.append(title)

        for para in zh_cn.get("content", []):
            parts: list[str] = []
            for elem in para:
                tag = elem.get("tag", "")
                if tag == "text":
                    parts.append(elem.get("text", ""))
                elif tag == "a":
                    parts.append(elem.get("text", ""))
                elif tag == "at":
                    parts.append(f"@{elem.get('user_name', '')}")
            if parts:
                lines.append("".join(parts))
        return "\n".join(lines)

    def reply_text(self, message_id: str, text: str) -> str:
        """Reply to a message with text. Returns reply message_id."""
        content = json.dumps({"text": text}, ensure_ascii=False)
        req = ReplyMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(ReplyMessageRequestBody.builder()
                .content(content)
                .msg_type("text")
                .body(ReplyMessageRequestBody.Body.builder()
                    .content(content)
                    .build())
                .build()) \
            .build()
        resp = self._client.im.v1.message.reply(req)
        if not resp.success():
            raise FeishuError(f"Reply failed: code={resp.code}, msg={resp.msg}")
        return str(resp.data.message_id)

    def upload_file(self, file_path: Path, file_type: str = "stream") -> str:
        """Upload a file to Feishu. Returns file_key.

        Args:
            file_path: Local file path.
            file_type: 'stream' for temporary files (valid 72h), 'bin' for permanent.
        """
        import requests
        token = self._get_access_token()
        url = f"{FEISHU_HOST}/open-apis/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers=headers,
                files={"file": (file_path.name, f, "application/octet-stream")},
                data={"file_type": file_type, "file_name": file_path.name},
            )
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuError(f"Upload file failed: code={data.get('code')}, msg={data.get('msg')}")
        return str(data["data"]["file_key"])

    def send_file(self, chat_id: str, file_key: str) -> str:
        """Send a file message to a chat. Returns message_id."""
        content = json.dumps({"file_key": file_key}, ensure_ascii=False)
        req = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("file")
                .content(content)
                .build()) \
            .build()
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            raise FeishuError(f"Send file failed: code={resp.code}, msg={resp.msg}")
        return str(resp.data.message_id)

    def _get_access_token(self) -> str:
        """Get tenant access token for raw API calls."""
        import requests
        app_id, app_secret = _get_credentials()
        resp = requests.post(
            f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuError(f"Auth failed: code={data.get('code')}, msg={data.get('msg')}")
        return str(data["tenant_access_token"])

    def list_chats(self, limit: int = 50) -> list[dict[str, str]]:
        """List chats the bot has joined."""
        from lark_oapi.api.im.v1 import ListChatRequest, ListChatResponse
        req = ListChatRequest.builder() \
            .page_size(limit) \
            .build()
        resp: ListChatResponse = self._client.im.v1.chat.list(req)
        if not resp.success():
            raise FeishuError(f"List chats failed: code={resp.code}, msg={resp.msg}")

        chats: list[dict[str, str]] = []
        for item in resp.data.items or []:
            chats.append({
                "chat_id": item.chat_id or "",
                "name": item.name or "",
                "description": item.description or "",
            })
        return chats
