"""终端交互：彩色输出、流式打印、用户确认。"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Any, TextIO

_COLORS = {
    "dim": "\x1b[2m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "cyan": "\x1b[36m",
    "bold": "\x1b[1m",
    "reset": "\x1b[0m",
}

_BOX_WIDTH = 76

LOGO = r"""
 _   _  ___  _   _  _   _  _____
| \ | | |_ _| | | | | | | | | ____|
|  \| |  | |  | |_| | | | | |  _|
| |\  |  | |  |  _  | | |_| | |___
|_| \_| |___| |_| |_|  \___/  |_____|
"""


def _display_width(text: str) -> int:
    """终端显示宽度：中日韩等全角字符按 2 列计算，用于对齐边框。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _box_line(content: str, left: str, right: str, fill: str) -> str:
    inner = _BOX_WIDTH - 2
    return left + content + fill * max(0, inner - _display_width(content)) + right


def _fill_line(text: str, width: int, fill: str = "─") -> str:
    """文本在左，填充字符一直延伸到指定宽度。"""
    return text + fill * max(0, width - _display_width(text))


def _two_sides(left: str, right: str, width: int) -> str:
    """左右两端文本，中间用空格填满整行。"""
    gap = max(1, width - _display_width(left) - _display_width(right))
    return left + " " * gap + right


class UI:
    def __init__(self, color: bool = True, stream: TextIO | None = None):
        self.stream = stream or sys.stdout
        self.color = bool(color) and self.stream.isatty()
        self._mid_line = False
        if os.name == "nt" and self.color:
            self._enable_vt()

    @staticmethod
    def _enable_vt() -> None:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

    def paint(self, color: str, text: str) -> str:
        return f"{_COLORS[color]}{text}{_COLORS['reset']}" if self.color else text

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()
        self._mid_line = not text.endswith("\n")

    def newline(self) -> None:
        if self._mid_line:
            self._write("\n")

    def logo(self) -> None:
        for line in LOGO.strip("\n").splitlines():
            self._write(self.paint("cyan", line) + "\n")
        self._write(self.paint("dim", "Nihue -- 你的编程智能体") + "\n")

    # ---- 流式输出 ----
    def stream_text(self, chunk: str) -> None:
        self._write(chunk)

    def stream_reasoning(self, chunk: str) -> None:
        if not getattr(self, "_reasoning_started", False):
            if not chunk.strip():
                return  # 丢弃开头无可见内容的空白片段，避免出现孤立的"思考:"
            self.newline()
            self._write(self.paint("dim", "思考: "))
            self._reasoning_started = True
        self._write(self.paint("dim", chunk))

    def end_turn(self) -> None:
        self._reasoning_started = False
        self.newline()

    # ---- 常规输出 ----
    def turn_header(self, number: int, maximum: int) -> None:
        self.newline()
        self._write(self.paint("bold", f"==== 第 {number} 轮（上限 {maximum}）====\n"))

    def tool_call(self, name: str, args_preview: str) -> None:
        self._write(self.paint("cyan", f">> {name}({args_preview})\n"))

    def tool_result(self, name: str, ok: bool, preview: str, duration_ms: int) -> None:
        marker = self.paint("green", "OK  ") if ok else self.paint("red", "FAIL")
        self._write(f"  [{marker}] {name} ({duration_ms}ms) -> {preview}\n")

    def info(self, text: str) -> None:
        self.newline()
        self._write(self.paint("dim", f"- {text}\n"))

    def ok(self, text: str) -> None:
        self.newline()
        self._write(self.paint("green", f"+ {text}\n"))

    def warn(self, text: str) -> None:
        self.newline()
        self._write(self.paint("yellow", f"! {text}\n"))

    def error(self, text: str) -> None:
        self.newline()
        self._write(self.paint("red", f"x {text}\n"))

    def _read_key(self) -> str:
        """读取一个按键：Windows 用 msvcrt，POSIX 用 termios 原始模式。"""
        if os.name == "nt":
            import msvcrt
            first = msvcrt.getch()
            if first in (b"\xe0", b"\x00"):
                second = msvcrt.getch()
                return {"H": "up", "P": "down"}.get(second.decode("latin-1"), "other")
            if first == b"\r":
                return "enter"
            if first == b"\x1b":
                return "esc"
            return "other"
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            first = sys.stdin.buffer.read(1)
            if first == b"\x1b":
                seq = sys.stdin.buffer.read(2)
                return {"[A": "up", "[B": "down"}.get(seq.decode("latin-1"), "esc")
            if first in (b"\r", b"\n"):
                return "enter"
            return "other"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def pick_session(self, entries: list[tuple[str, str]]) -> int | None:
        """方向键选择会话：↑↓ 移动、Enter 恢复、Esc 取消；非交互终端回退为数字输入。"""
        if not entries:
            self.info("（暂无已保存会话）")
            return None
        if not (self.color and self.stream is sys.stdout and sys.stdin.isatty()):
            self._write("\n".join(f"{i + 1}. {title}   {sublabel}" for i, (title, sublabel) in enumerate(entries)) + "\n")
            return self._pick_numbered(entries)
        height = len(entries) + 4
        index = 0
        first_draw = True
        while True:
            if not first_draw:
                self._write(f"\x1b[{height}A")
            first_draw = False
            self._write(self._picker_block(entries, index) + "\n")
            try:
                key = self._read_key()
            except OSError:
                self._write("\n")
                return self._pick_numbered(entries)
            except (EOFError, KeyboardInterrupt):
                self._write("\n")
                return None
            if key == "up":
                index = (index - 1) % len(entries)
            elif key == "down":
                index = (index + 1) % len(entries)
            elif key == "enter":
                self._write("\n")
                return index
            elif key == "esc":
                self._write("\n")
                return None

    def _pick_numbered(self, entries: list[tuple[str, str]]) -> int | None:
        try:
            answer = input("输入序号恢复，直接回车取消：").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(entries):
            return int(answer) - 1
        return None

    def _picker_block(self, entries: list[tuple[str, str]], index: int) -> str:
        width = max(40, min(shutil.get_terminal_size(fallback=(76, 24)).columns, 300))
        border = self.paint("dim", "─" * width)
        caption = self.paint("dim", " 选择会话：↑↓ 移动 · Enter 恢复 · Esc 取消")
        lines = [caption, border]
        for i, (title, sublabel) in enumerate(entries):
            marker = ">" if i == index else " "
            line = f"  {marker} {title}   {sublabel}"
            if i == index:
                line = self.paint("bold", line)
            lines.append(line + "\x1b[K")
        lines.append(border)
        lines.append(self.paint("dim", " ? ↑↓ 选择 · Enter 恢复 · Esc 取消"))
        return "\n".join(lines)

    def show_history(self, messages: list[dict[str, Any]], max_assistant_chars: int = 2000, max_detail_chars: int = 240) -> None:
        """回放恢复的会话历史：用户消息与助手回复全文展示，工具调用与结果给出摘要细节。"""
        self.newline()
        for message in messages:
            role = message.get("role")
            if role == "user":
                self._write(self.paint("cyan", "你 › ") + str(message.get("content") or "") + "\n")
            elif role == "assistant":
                content = str(message.get("content") or "").strip()
                calls = message.get("tool_calls") or []
                if content:
                    if len(content) > max_assistant_chars:
                        content = content[:max_assistant_chars] + "\n[回复过长，中间部分已省略]"
                    self._write(content + "\n")
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name") or "unknown"
                    args_preview = " ".join(str(function.get("arguments") or "").split())
                    if len(args_preview) > max_detail_chars:
                        args_preview = args_preview[: max_detail_chars - 3] + "..."
                    self._write(self.paint("cyan", f">> {name}({args_preview})\n"))
            elif role == "tool":
                name = str(message.get("name") or "tool")
                preview = " ".join(str(message.get("content") or "").split())
                if len(preview) > max_detail_chars:
                    preview = preview[: max_detail_chars - 3] + "..."
                self._write(self.paint("dim", f"  [工具] {name}: {preview}\n"))

    # ---- 交互 ----
    def ask_yes_no(self, question: str) -> bool:
        self.newline()
        while True:
            try:
                answer = input(f"{question} [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False
            if answer in ("y", "yes"):
                return True
            if answer in ("", "n", "no"):
                return False

    def ask(self, prompt: str) -> str:
        self.newline()
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    def task_input(self, label: str = "你") -> str:
        """Claude Code 风格的全宽输入栏。EOF 时抛 EOFError，KeyboardInterrupt 原样上抛。

        真实交互终端里：按终端实际宽度画出上横线（含任务提示）、空输入行、
        下横线、快捷键提示行，再用 ANSI 光标上移回到输入行等待输入；
        管道/重定向等非交互场景回退为固定宽度角框，避免输出转义序列。
        """
        self.newline()
        if self.color and self.stream is sys.stdout:
            return self._fancy_task_input(label)
        hint = " 输入任务（/help 查看命令，/exit 退出）"
        top = self.paint("dim", _box_line(hint, "┌", "┐", "─"))
        bottom = self.paint("dim", _box_line("", "└", "┘", "─"))
        self._write(top + "\n")
        eof = False
        try:
            text = input(self.paint("cyan", "│ " + label + " › "))
        except EOFError:
            text = ""
            eof = True
        self._write(bottom + "\n")
        self._mid_line = False
        if eof:
            raise EOFError
        return text

    def _fancy_task_input(self, label: str) -> str:
        width = max(40, min(shutil.get_terminal_size(fallback=(76, 24)).columns, 300))
        caption = self.paint("dim", " 输入任务（/help 查看命令，/exit 退出）")
        top = self.paint("dim", "─" * width)
        bottom = self.paint("dim", "─" * width)
        hints = self.paint(
            "dim", _two_sides(" ? /help 查看命令 · /exit 退出", "● /clear 清空 · /stats 统计", width)
        )
        # 布局：提示行 / 上边界 / 输入行 / 下边界 / 快捷键行，光标上移回到输入行
        self.stream.write(caption + "\n" + top + "\n\n" + bottom + "\n" + hints + "\n\x1b[3A")
        self.stream.flush()
        eof = False
        try:
            text = input(self.paint("cyan", label + " › "))
        except EOFError:
            text = ""
            eof = True
        self.stream.write("\n\n")
        self.stream.flush()
        self._mid_line = False
        if eof:
            raise EOFError
        return text


class TerminalApprover:
    """run_command 的人工确认器：y 执行一次 / n 拒绝 / a 本次会话全部放行 / s 跳过。"""

    def __init__(self, ui: UI, auto_approve: bool = False):
        self.ui = ui
        self.auto_approve = auto_approve

    def approve(self, command: str) -> str:
        if self.auto_approve:
            return "yes"
        self.ui.warn(f"模型请求执行命令：\n    {command}")
        while True:
            try:
                choice = input("    [y]运行  [n]拒绝  [a]本次会话全部放行  [s]跳过 > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "no"
            if choice in ("", "y", "yes"):
                return "yes"
            if choice in ("n", "no"):
                return "no"
            if choice in ("a", "all", "always"):
                self.auto_approve = True
                return "yes"
            if choice in ("s", "skip"):
                return "skip"
