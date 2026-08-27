"""会话保存与恢复：把完整消息历史落盘为 JSONL，可随时 --resume 续接。

会话文件保存在用户主目录 ~/.coding-agent/sessions 下，不进仓库，避免误提交。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .context import MessageStore

SESSION_DIR = Path.home() / ".coding-agent" / "sessions"


def ensure_session_dir() -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR


def new_session_path(slug: str = "session") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in slug)[:24] or "session"
    return ensure_session_dir() / f"{stamp}-{safe}.jsonl"


def save_session(path: Path | None, store: MessageStore) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(message, ensure_ascii=False) for message in store.messages]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_session(path: Path, store: MessageStore) -> MessageStore:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    loaded = MessageStore.from_records(store.system_prompt, records)
    loaded.context_budget = store.context_budget
    loaded.keep_recent = store.keep_recent
    return loaded


def resolve_session(name: str) -> Path:
    """按文件名、前缀或序号解析会话文件。"""
    directory = ensure_session_dir()
    files = sorted(directory.glob("*.jsonl"), reverse=True)
    if not files:
        raise FileNotFoundError("没有找到已保存的会话。")
    exact = directory / (name if name.endswith(".jsonl") else name + ".jsonl")
    if exact in files:
        return exact
    for candidate in files:
        if candidate.name.startswith(name):
            return candidate
    raise FileNotFoundError(
        f"找不到会话 {name!r}，可用会话：\n" + "\n".join(f"  {f.name}" for f in files[:10])
    )


def list_sessions(limit: int = 10) -> list[str]:
    directory = ensure_session_dir()
    files = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    if not files:
        return ["（暂无已保存会话）"]
    lines = []
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        lines.append(f"{path.name}  ({size} 字节)")
    return lines
