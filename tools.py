"""AIが自分で実行できるツール群 (tool use)。

- calculator: 安全な数式計算 (ast で解析するので eval の危険なし)
- current_time: 現在の日時
- remember: ユーザーに関する事実を長期記憶に保存
- web_search: Web検索 (ddgs パッケージがあれば有効)
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime

TOOL_DEFINITIONS = [
    {
        "name": "calculator",
        "description": "数式を正確に計算する。四則演算・べき乗・剰余に対応。例: '(1200 * 1.1) / 3'",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "計算する数式"}
            },
            "required": ["expression"],
        },
    },
    {
        "name": "current_time",
        "description": "現在の日付と時刻を取得する。「今日」「今何時」などの質問で必ず使うこと。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "remember",
        "description": (
            "ユーザーに関する新しい情報(名前・好み・目標・状況など)や、"
            "覚えておくべき決定事項を長期記憶に保存する。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "記憶する内容(1文で簡潔に)"}
            },
            "required": ["fact"],
        },
    },
    {
        "name": "web_search",
        "description": "最新情報や知らないことをWebで検索する。ニュース・最新の事実確認に使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索キーワード"}
            },
            "required": ["query"],
        },
    },
]

# ---------- calculator ----------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("対応していない式です")


def calculator(expression: str) -> str:
    try:
        result = _safe_eval(ast.parse(expression, mode="eval"))
        return f"{expression} = {result}"
    except Exception as e:
        return f"計算エラー: {e}"


# ---------- web_search ----------

def web_search(query: str) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        return (
            "検索機能が無効です。有効にするには `pip install ddgs` を実行してください。"
        )
    try:
        results = list(DDGS().text(query, max_results=5))
        if not results:
            return "検索結果が見つかりませんでした。"
        lines = []
        for r in results:
            lines.append(f"- {r.get('title')}\n  {r.get('body')}\n  ({r.get('href')})")
        return "\n".join(lines)
    except Exception as e:
        return f"検索エラー: {e}"


# ---------- dispatcher ----------

def run_tool(name: str, tool_input: dict, memory) -> str:
    """ツール名に応じて実行し、結果文字列を返す。"""
    if name == "calculator":
        return calculator(tool_input.get("expression", ""))
    if name == "current_time":
        now = datetime.now()
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        return now.strftime(f"%Y年%m月%d日({weekdays[now.weekday()]}) %H:%M:%S")
    if name == "remember":
        fact = tool_input.get("fact", "").strip()
        if fact:
            memory.append_long_term(fact, section="ユーザー情報")
            return f"記憶しました: {fact}"
        return "記憶する内容が空です。"
    if name == "web_search":
        return web_search(tool_input.get("query", ""))
    return f"不明なツール: {name}"
