"""终端交互：彩色输出、流式打印、用户确认。"""

from __future__ import annotations

import os
import re
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


def _wrap_display(text: str, width: int) -> list[str]:
    """按终端显示宽度折行（全角字符按 2 列），返回每行分段。"""
    if width <= 0:
        return [text]
    segments: list[str] = []
    for raw_line in text.split("\n"):
        current = ""
        used = 0
        for ch in raw_line:
            w = 2 if ord(ch) > 0x2E80 else 1
            if used + w > width:
                segments.append(current)
                current = ch
                used = w
            else:
                current += ch
                used += w
        segments.append(current)
    return segments


def _format_duration(ms: int) -> str:
    """把毫秒格式化为紧凑时长：ms / s / m。"""
    if ms < 1000:
        return f"{ms}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    return f"{ms // 60_000}m{ms % 60_000 // 1000}s"
class UI:
    def __init__(self, color: bool = True, stream: TextIO | None = None):
        self.stream = stream or sys.stdout
        self.color = bool(color) and self.stream.isatty()
        self._mid_line = False
        self._markdown = None
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

    def _term_width(self) -> int:
        if self.color:
            return max(40, min(shutil.get_terminal_size(fallback=(76, 24)).columns, 300))
        return _BOX_WIDTH
    def logo(self) -> None:
        for line in LOGO.strip("\n").splitlines():
            self._write(self.paint("cyan", line) + "\n")
        self._write(self.paint("dim", "Nihue -- 你的编程智能体") + "\n")

    # ---- 流式输出 ----
    def stream_text(self, chunk: str) -> None:
        self._flush_reasoning()
        if self._markdown is None:
            self._markdown = MarkdownStream(self)
        self._markdown.feed(chunk)

    def stream_reasoning(self, chunk: str) -> None:
        if not chunk:
            return
        if not self.color:
            if not getattr(self, "_reasoning_started", False):
                if not chunk.strip():
                    return
                self.newline()
                self._write("思考: ")
                self._reasoning_started = True
            self._write(chunk)
            return
        if not getattr(self, "_reasoning_started", False):
            if not chunk.strip():
                return
            self.newline()
            self._reasoning_width = self._term_width()
            self._reasoning_buf = ""
            self._write(self.paint("dim", "┌─ 思考 " + "─" * max(0, self._reasoning_width - 7) + "┐") + "\n")
            self._reasoning_started = True
        self._reasoning_buf += chunk.replace("\r\n", "\n")
        while "\n" in self._reasoning_buf:
            line, self._reasoning_buf = self._reasoning_buf.split("\n", 1)
            self._render_reasoning_line(line)

    def _flush_reasoning(self) -> None:
        if not getattr(self, "_reasoning_started", False):
            return
        if not self.color:
            self._reasoning_started = False
            return
        if getattr(self, "_reasoning_buf", ""):
            self._render_reasoning_line(self._reasoning_buf)
        self._reasoning_buf = ""
        self._write(self.paint("dim", "└" + "─" * max(0, self._reasoning_width - 2) + "┘") + "\n")
        self._reasoning_started = False

    def _render_reasoning_line(self, line: str) -> None:
        inner = max(8, self._reasoning_width - 4)
        for seg in _wrap_display(line, inner):
            pad = self._reasoning_width - 3 - _display_width(seg)
            self._write(self.paint("dim", "│ " + seg + " " * max(0, pad) + "│") + "\n")

    def end_turn(self) -> None:
        self._flush_reasoning()
        if self._markdown is not None:
            self._markdown.flush()
        self.newline()
    # ---- 常规输出 ----
    def turn_header(self, number: int, maximum: int) -> None:
        self.newline()
        self._write(self.paint("bold", f"==== 第 {number} 轮（上限 {maximum}）====\n"))

    def tool_call(self, name: str, args_preview: str) -> None:
        self._flush_reasoning()
        self.newline()
        if not self.color:
            self._write(f">> {name}({args_preview})\n")
            return
        line = self.paint("cyan", "▸ " + name)
        if args_preview:
            line += " " + self.paint("dim", args_preview)
        self._write(line + "\n")

    def tool_result(self, name: str, ok: bool, preview: str, duration_ms: int) -> None:
        if not self.color:
            marker = "OK" if ok else "FAIL"
            self._write(f"  [{marker}] {name} ({duration_ms}ms) -> {preview}\n")
            return
        status = self.paint("green", "✓") if ok else self.paint("red", "✗")
        prefix = "  " + status + " "
        lead = "  " + ("✓" if ok else "✗") + " " + _format_duration(duration_ms) + " · "
        cols = max(24, self._term_width() - _display_width(lead))
        segments = _wrap_display(preview, cols)
        self._write(prefix + self.paint("dim", _format_duration(duration_ms) + " · " + segments[0]) + "\n")
        indent = " " * _display_width(lead)
        for seg in segments[1:]:
            self._write(indent + self.paint("dim", seg) + "\n")
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

class MarkdownStream:
    """把模型流式输出的 Markdown 渲染为彩色终端文本；颜色关闭时原样透传。

    支持：标题、加粗/斜体、行内代码、围栏代码块、无序/有序列表、引用、水平线；
    其余内容（表格、链接等）保持原文输出。
    """

    _INLINE_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)")

    def __init__(self, ui: UI):
        self.ui = ui
        self._buffer = ""
        self._in_fence = False
        self._fence_lang = ""

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        if not self.ui.color:
            self.ui._write(chunk)
            return
        self._buffer += chunk.replace("\r\n", "\n")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._render_line(line)

    def flush(self) -> None:
        if self.ui.color and self._buffer:
            self._render_line(self._buffer)
        self._buffer = ""

    def _render_line(self, line: str) -> None:
        ui = self.ui
        stripped = line.strip()
        if stripped.startswith("```"):
            if not self._in_fence:
                self._in_fence = True
                self._fence_lang = stripped[3:].strip()
                ui._write(ui.paint("dim", "┌─ " + (self._fence_lang or "code")) + "\n")
            else:
                self._in_fence = False
                ui._write(ui.paint("dim", "└─") + "\n")
            return
        if self._in_fence:
            ui._write(ui.paint("cyan", "│ ") + line + "\n")
            return

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            color = {1: "yellow", 2: "cyan", 3: "green"}.get(level, "dim")
            ui._write(
                ui.paint("bold", heading.group(1) + " ")
                + ui.paint(color, self._render_inline(heading.group(2)))
                + "\n"
            )
            return

        bullet = re.match(r"^(\s*)([-*+])\s+(.*)$", line)
        if bullet:
            indent, marker, rest = bullet.groups()
            ui._write(indent + ui.paint("yellow", marker) + " " + self._render_inline(rest) + "\n")
            return

        numbered = re.match(r"^(\s*)(\d+[.)])\s+(.*)$", line)
        if numbered:
            indent, marker, rest = numbered.groups()
            ui._write(indent + ui.paint("cyan", marker) + " " + self._render_inline(rest) + "\n")
            return

        quote = re.match(r"^(\s*>\s?)(.*)$", line)
        if quote:
            ui._write(
                ui.paint("dim", quote.group(1))
                + ui.paint("dim", self._render_inline(quote.group(2)))
                + "\n"
            )
            return

        if stripped in ("---", "***", "___", "==="):
            ui._write(ui.paint("dim", line) + "\n")
            return

        ui._write(self._render_inline(line) + "\n")

    def _render_inline(self, text: str) -> str:
        ui = self.ui
        parts: list[str] = []
        pos = 0
        for match in self._INLINE_RE.finditer(text):
            parts.append(text[pos:match.start()])
            token = match.group(0)
            if token.startswith("`"):
                parts.append(ui.paint("cyan", token[1:-1]))
            elif token.startswith("**"):
                parts.append(ui.paint("bold", token[2:-2]))
            else:
                parts.append(ui.paint("green", token[1:-1]))
            pos = match.end()
        parts.append(text[pos:])
        return "".join(parts)