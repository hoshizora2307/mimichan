"""記憶・パーソナライズ機能。

3層の記憶を持つ:
1. 短期記憶: 現在の会話履歴 (history.json に永続化。再起動しても続きから話せる)
2. 長期記憶: ユーザーに関する事実・過去の会話の要約 (memory.md)
3. 自動要約: 履歴が長くなったらAIに要約させ、長期記憶へ移す

メッセージは OpenAI Chat Completions 形式で保存する
(Gemini / Claude どちらもOpenAI互換エンドポイント経由で使うため)。
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

    def add(self, role: str, content: str) -> None:
        self.add_raw({"role": role, "content": content})

    def add_raw(self, message: dict) -> None:
        """tool_calls 付きassistantメッセージや role='tool' もそのまま保存する。"""
        self.messages.append(message)
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

    def compress(self, summarize) -> None:
        """古い履歴を要約して長期記憶に移し、直近だけを残す。

        summarize: プロンプト文字列を受け取り要約文字列を返す関数
                   (どのAIプロバイダーを使うかは呼び出し側が決める)

        注意: assistantのツール呼び出しと role='tool' の結果ペアが
        分断されないよう、残す先頭が user の通常メッセージになる位置まで調整する。
        """
        cut = len(self.messages) - self.keep_recent
        while cut < len(self.messages):
            m = self.messages[cut]
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                break
            cut += 1
        if cut <= 0:
            return

        old = self.messages[:cut]
        summary = summarize(
            "以下はAIアシスタントとユーザーの会話ログです。"
            "今後の会話で役立つ情報(ユーザーの好み・状況・決定事項・話題の流れ)を"
            "箇条書きで簡潔に要約してください。要約だけを出力してください。\n\n"
            + _to_text(old)
        ).strip()
        if summary:
            self.append_long_term(summary, section="会話の要約")
        self.messages = self.messages[cut:]
        self.save_history()


def _to_text(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
