"""会话保存与恢复：把完整消息历史落盘为 JSONL，可随时 --resume 续接。

会话文件保存在用户主目录 ~/.coding-agent/sessions 下，不进仓库，避免误提交。
列表展示的标题取第一条用户消息（类似 Claude Code），文件名保持不变。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass
class SessionEntry:
    path: Path
    name: str
    title: str
    size: int
    mtime: datetime


def derive_title(path: Path, max_chars: int = 24) -> str:
    """标题取第一条用户消息的首行，过长截断；没有则退回文件名主干。"""
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("role") == "user":
                    text = str(record.get("content") or "").strip()
                    if text:
                        title = " ".join(text.splitlines()[0].split())
                        if len(title) > max_chars:
                            title = title[: max_chars - 3] + "..."
                        return title or path.stem
        return path.stem
    except OSError:
        return path.stem


def list_sessions(limit: int = 10) -> list[SessionEntry]:
    directory = ensure_session_dir()
    files = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    entries: list[SessionEntry] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            stat = None
        entries.append(
            SessionEntry(
                path=path,
                name=path.name,
                title=derive_title(path),
                size=stat.st_size if stat else 0,
                mtime=datetime.fromtimestamp(stat.st_mtime) if stat else datetime.min,
            )
        )
    return entries


def resolve_session(name: str) -> Path:
    """按 完整文件名 / 文件名前缀 / 数字序号 / 标题（前缀或包含） 解析会话。"""
    directory = ensure_session_dir()
    files = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("没有找到已保存的会话。")
    key = (name or "").strip()
    exact = directory / (key if key.endswith(".jsonl") else key + ".jsonl")
    if exact in files:
        return exact
    if key.isdigit():
        index = int(key) - 1
        if 0 <= index < len(files):
            return files[index]
    for candidate in files:
        if candidate.name.startswith(key):
            return candidate
    lowered = key.lower()
    for candidate in files:
        title = derive_title(candidate).lower()
        if title.startswith(lowered) or lowered in title:
            return candidate
    raise FileNotFoundError(
        f"找不到会话 {name!r}，可用会话：\n"
        + "\n".join(f"  {i + 1}. {derive_title(f)}  ({f.name})" for i, f in enumerate(files[:10]))
    )
