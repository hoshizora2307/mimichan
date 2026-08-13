"""記憶・パーソナライズ機能。

3層の記憶を持つ:
1. 短期記憶: 現在の会話履歴 (history.json に永続化。再起動しても続きから話せる)
2. 長期記憶: ユーザーに関する事実・過去の会話の要約 (memory.md)
3. 自動要約: 履歴が長くなったら古い部分をAI自身に要約させ、長期記憶へ移す
"""

from __future__ import annotations

import json
import os
from datetime import datetime


class MemoryManager:
    def __init__(self, config: dict):
        self.history_file = config["history_file"]
        self.memory_file = config["memory_file"]
        self.summary_trigger = config.get("summary_trigger_messages", 40)
        self.keep_recent = config.get("keep_recent_messages", 12)
        os.makedirs(os.path.dirname(self.history_file) or ".", exist_ok=True)
        self.messages: list[dict] = self._load_history()

    # ---------- 短期記憶(会話履歴) ----------

    def _load_history(self) -> list[dict]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def save_history(self) -> None:
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=1)

    def add(self, role: str, content) -> None:
        self.messages.append({"role": role, "content": content})
        self.save_history()

    def reset_history(self) -> None:
        self.messages = []
        self.save_history()

    # ---------- 長期記憶 ----------

    def load_long_term(self) -> str:
        if os.path.exists(self.memory_file):
            with open(self.memory_file, encoding="utf-8") as f:
                return f.read().strip()
        return "(まだ長期記憶はありません)"

    def append_long_term(self, text: str, section: str = "メモ") -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(self.memory_file, "a", encoding="utf-8") as f:
            f.write(f"\n- [{stamp}][{section}] {text}")

    # ---------- 自動要約(圧縮) ----------

    def needs_summary(self) -> bool:
        return len(self.messages) >= self.summary_trigger

    def compress(self, client, model: str) -> None:
        """古い履歴をAIに要約させて長期記憶に移し、直近だけを残す。

        注意: tool_use と tool_result のペアが分断されないよう、
        残す先頭が user の通常メッセージになる位置まで調整する。
        """
        cut = len(self.messages) - self.keep_recent
        while cut < len(self.messages):
            m = self.messages[cut]
            if m["role"] == "user" and isinstance(m["content"], str):
                break
            cut += 1
        if cut <= 0:
            return

        old = self.messages[:cut]
        transcript = _to_text(old)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "以下はAIアシスタントとユーザーの会話ログです。"
                    "今後の会話で役立つ情報(ユーザーの好み・状況・決定事項・話題の流れ)を"
                    "箇条書きで簡潔に要約してください。要約だけを出力してください。\n\n"
                    + transcript
                ),
            }],
        )
        summary = response.content[0].text.strip()
        self.append_long_term(summary, section="会話の要約")
        self.messages = self.messages[cut:]
        self.save_history()


def _to_text(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            lines.append(f"{m['role']}: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    lines.append(f"{m['role']}: {block['text']}")
    return "\n".join(lines)
