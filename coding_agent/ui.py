"""终端交互：彩色输出、流式打印、用户确认。"""

from __future__ import annotations

import os
import sys
from typing import TextIO

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


def _display_width(text: str) -> int:
    """终端显示宽度：中日韩等全角字符按 2 列计算，用于对齐边框。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _box_line(content: str, left: str, right: str, fill: str) -> str:
    inner = _BOX_WIDTH - 2
    return left + content + fill * max(0, inner - _display_width(content)) + right


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

    # ---- 流式输出 ----
    def stream_text(self, chunk: str) -> None:
        self._write(chunk)

    def stream_reasoning(self, chunk: str) -> None:
        if not getattr(self, "_reasoning_started", False):
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
        """带上下边框的任务输入框。EOF 时抛 EOFError，KeyboardInterrupt 原样上抛。"""
        hint = " 输入任务（/help 查看命令，/exit 退出）"
        self.newline()
        self._write(self.paint("dim", _box_line(hint, "┌", "┐", "─") + "\n"))
        eof = False
        try:
            text = input(self.paint("cyan", "│ " + label + " › "))
        except EOFError:
            text = ""
            eof = True
        self._write(self.paint("dim", _box_line("", "└", "┘", "─") + "\n"))
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
