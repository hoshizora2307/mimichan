#!/usr/bin/env python3
"""ミミちゃんとチャットできるWebアプリ。

© 株式会社MONDOCOLO / Produced by MONDOCOLO STUDIO

使い方:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python app.py
    → ブラウザで http://localhost:5000 を開く
"""

from __future__ import annotations

import json
import os
import sys
import threading

try:
    from anthropic import Anthropic
    from flask import Flask, jsonify, render_template, request
except ImportError:
    print("必要なパッケージをインストールしてください: pip install -r requirements.txt")
    sys.exit(1)

from memory import MemoryManager
from tools import TOOL_DEFINITIONS, run_tool

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)
for _key in ("history_file", "memory_file", "persona_file"):
    CONFIG[_key] = os.path.join(BASE_DIR, CONFIG[_key])

app = Flask(__name__)
memory = MemoryManager(CONFIG)
client = Anthropic()
_lock = threading.Lock()  # 同時リクエストで履歴が壊れないように


def build_system_prompt() -> str:
    with open(CONFIG["persona_file"], encoding="utf-8") as f:
        persona = f.read()
    return (
        f"{persona}\n\n"
        "# 長期記憶(過去の会話から学んだこと)\n"
        f"{memory.load_long_term()}\n\n"
        "# 指示\n"
        "- 長期記憶の内容を自然に会話へ活かすこと\n"
        "- 事実確認・計算・日時はツールを使い、憶測で答えないこと\n"
    )


def chat(user_input: str) -> str:
    """1ターンの対話。ツール使用があれば解決するまでループし、最終テキストを返す。"""
    memory.add("user", user_input)
    system = build_system_prompt()

    while True:
        response = client.messages.create(
            model=CONFIG["model"],
            max_tokens=CONFIG["max_tokens"],
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=memory.messages,
        )
        memory.add("assistant", [b.model_dump() for b in response.content])

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = run_tool(block.name, block.input, memory)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        memory.add("user", results)


@app.route("/")
def index():
    return render_template("index.html", name=CONFIG["character_name"])


@app.route("/api/history")
def api_history():
    """ページ再読み込み時に過去のチャットを復元する。"""
    out = []
    for m in memory.messages:
        content = m["content"]
        if m["role"] == "user" and isinstance(content, str):
            out.append({"role": "user", "text": content})
        elif m["role"] == "assistant" and isinstance(content, list):
            text = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                out.append({"role": "assistant", "text": text})
    return jsonify(out)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    user_input = (request.json or {}).get("message", "").strip()
    if not user_input:
        return jsonify({"error": "メッセージが空です"}), 400
    with _lock:
        try:
            reply = chat(user_input)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        # 会話が長くなったら自動要約して長期記憶へ
        if memory.needs_summary():
            try:
                memory.compress(client, CONFIG["model"])
            except Exception:
                pass
    return jsonify({"reply": reply})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    with _lock:
        memory.reset_history()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("環境変数 ANTHROPIC_API_KEY を設定してください。")
        print('  例: export ANTHROPIC_API_KEY="sk-ant-..."')
        sys.exit(1)
    print("ブラウザで http://localhost:5000 を開いてね!")
    app.run(host="127.0.0.1", port=5000, debug=False)
