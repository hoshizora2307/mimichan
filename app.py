#!/usr/bin/env python3
"""ミミちゃんとチャットできるWebアプリ(マルチユーザー対応)。

© 株式会社MONDOCOLO / Produced by MONDOCOLO STUDIO

Gemini / Claude のどちらでも動きます (config.json の "provider" で切り替え)。
どちらもOpenAI互換エンドポイント経由で呼び出すため、コードは共通です。

ローカル起動 (Gemini の場合):
    export GEMINI_API_KEY="AIza..."
    export APP_PASSCODE="社内の合言葉"   # 省略するとパスコードなしで動く
    python app.py
    → ブラウザで http://localhost:5000

本番 (Render など) では gunicorn で起動:
    gunicorn app:app
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading

try:
    from flask import Flask, jsonify, render_template, request, session
    from openai import OpenAI
except ImportError:
    print("必要なパッケージをインストールしてください: pip install -r requirements.txt")
    sys.exit(1)

from memory import MemoryManager
from tools import TOOL_DEFINITIONS, run_tool

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)
CONFIG["persona_file"] = os.path.join(BASE_DIR, CONFIG["persona_file"])

# ---------- AIプロバイダー設定 ----------

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/",
        "key_env": "ANTHROPIC_API_KEY",
    },
}

PROVIDER = CONFIG.get("provider", "gemini")
if PROVIDER not in PROVIDERS:
    print(f"config.json の provider は {list(PROVIDERS)} のどれかにしてください")
    sys.exit(1)
KEY_ENV = PROVIDERS[PROVIDER]["key_env"]

client = OpenAI(
    base_url=PROVIDERS[PROVIDER]["base_url"],
    api_key=os.environ.get(KEY_ENV, "unset"),
)

DATA_DIR = os.path.join(BASE_DIR, "data", "users")
PASSCODE = os.environ.get("APP_PASSCODE", "")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 365  # 1年

# ユーザーごとの記憶とロック
_memories: dict[str, MemoryManager] = {}
_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def get_user_id() -> str:
    """セッションCookieからユーザーIDを取得(なければ発行)。"""
    if "uid" not in session:
        session["uid"] = secrets.token_hex(16)
        session.permanent = True
    return session["uid"]


def get_memory(uid: str) -> MemoryManager:
    with _global_lock:
        if uid not in _memories:
            safe = re.sub(r"[^a-f0-9]", "", uid)[:32]
            user_dir = os.path.join(DATA_DIR, safe)
            cfg = dict(CONFIG)
            cfg["history_file"] = os.path.join(user_dir, "history.json")
            cfg["memory_file"] = os.path.join(user_dir, "memory.md")
            _memories[uid] = MemoryManager(cfg)
            _locks[uid] = threading.Lock()
        return _memories[uid]


def is_authed() -> bool:
    return not PASSCODE or session.get("authed", False)


def build_system_prompt(memory: MemoryManager) -> str:
    with open(CONFIG["persona_file"], encoding="utf-8") as f:
        persona = f.read()
    return (
        f"{persona}\n\n"
        "# 長期記憶(この相手との過去の会話から学んだこと)\n"
        f"{memory.load_long_term()}\n\n"
        "# 指示\n"
        "- 長期記憶の内容を自然に会話へ活かすこと\n"
        "- 事実確認・計算・日時はツールを使い、憶測で答えないこと\n"
    )


def summarize(prompt: str) -> str:
    """履歴圧縮用のワンショット要約呼び出し。"""
    response = client.chat.completions.create(
        model=CONFIG["model"],
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def chat(memory: MemoryManager, user_input: str) -> str:
    """1ターンの対話。ツール使用があれば解決するまでループし、最終テキストを返す。"""
    memory.add("user", user_input)
    system_msg = {"role": "system", "content": build_system_prompt(memory)}

    for _ in range(8):  # ツールループの上限(暴走防止)
        response = client.chat.completions.create(
            model=CONFIG["model"],
            max_tokens=CONFIG["max_tokens"],
            messages=[system_msg] + memory.messages,
            tools=TOOL_DEFINITIONS,
        )
        msg = response.choices[0].message

        assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        memory.add_raw(assistant_msg)

        if not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            output = run_tool(tc.function.name, args, memory)
            memory.add_raw({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": output,
            })

    return "ごめん、うまく処理できなかった💦 もう一回言ってみて!"


# ---------- ルート ----------

@app.route("/")
def index():
    return render_template(
        "index.html",
        name=CONFIG["character_name"],
        need_passcode=not is_authed(),
    )


@app.route("/api/login", methods=["POST"])
def api_login():
    code = (request.json or {}).get("passcode", "")
    if not PASSCODE or secrets.compare_digest(code, PASSCODE):
        session["authed"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "合言葉が違うよ〜💦"}), 401


@app.route("/api/history")
def api_history():
    if not is_authed():
        return jsonify({"error": "unauthorized"}), 401
    memory = get_memory(get_user_id())
    out = []
    for m in memory.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "user" and isinstance(content, str):
            out.append({"role": "user", "text": content})
        elif role == "assistant" and isinstance(content, str) and content.strip():
            out.append({"role": "assistant", "text": content})
    return jsonify(out)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not is_authed():
        return jsonify({"error": "unauthorized"}), 401
    user_input = (request.json or {}).get("message", "").strip()
    if not user_input:
        return jsonify({"error": "メッセージが空です"}), 400
    if len(user_input) > 4000:
        return jsonify({"error": "メッセージが長すぎます"}), 400

    uid = get_user_id()
    memory = get_memory(uid)
    with _locks[uid]:
        try:
            reply = chat(memory, user_input)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        if memory.needs_summary():
            try:
                memory.compress(summarize)
            except Exception:
                pass
    return jsonify({"reply": reply})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    if not is_authed():
        return jsonify({"error": "unauthorized"}), 401
    uid = get_user_id()
    memory = get_memory(uid)
    with _locks[uid]:
        memory.reset_history()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not os.environ.get(KEY_ENV):
        print(f"環境変数 {KEY_ENV} を設定してください。")
        if PROVIDER == "gemini":
            print("  Geminiのキーは https://aistudio.google.com/apikey で無料取得できます")
        sys.exit(1)
    port = int(os.environ.get("PORT", 5000))
    print(f"[{PROVIDER} / {CONFIG['model']}] ブラウザで http://localhost:{port} を開いてね!")
    app.run(host="0.0.0.0", port=port, debug=False)
