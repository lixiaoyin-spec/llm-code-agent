"""本地工具集：工具定义、执行与安全防护。

安全设计（面试重点）：
- 路径沙箱：所有文件操作强制落在工作目录内，拒绝绝对路径逃逸与 .. 穿越
  （先 resolve 再与工作目录比较，符号链接也一并解析）；
- 命令确认：run_command 默认弹出人工确认（yes/no/always/skip），
  另加一层粗粒度危险命令拦截做"防呆"，二者互补；
- 输出截断：读文件、命令输出都有长度上限，避免撑爆上下文。

工具输出即"观察"，全部以自然语言回传给模型，构成其自我纠正的闭环。
"""

from __future__ import annotations

import locale
import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .skills import SkillError

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", ".idea", ".vscode", ".mypy_cache", ".pytest_cache"}

# 粗粒度"防呆"拦截：命中即拒绝。真正可靠的安全边界是人工确认，见 README。
_BLOCKED_FRAGMENTS = (
    "rm -rf /", "rm -fr /", "sudo rm -rf", "rm -rf ~", "rm -rf $home",
    "rd /s c:", "rd /s /q c:", "del /f /s c:", "del /s /q c:",
    "format c:", "format d:", "mkfs", "shutdown", "reboot",
    "dd if=", ":(){", "> /dev/sda", "> /dev/nvme",
)


class ToolError(Exception):
    """工具执行错误。消息会原样反馈给模型，帮助其自我纠正。"""


class Approver(Protocol):
    """命令确认器：返回 yes / no / always / skip。"""

    def approve(self, command: str) -> str: ...


class AutoApprover:
    """测试或 --auto-approve 场景：全部放行。"""

    def approve(self, command: str) -> str:
        return "yes"


@dataclass
class ToolContext:
    workspace: Path
    approver: Approver
    read_max_bytes: int = 96 * 1024
    read_max_lines: int = 2_000
    output_chars: int = 8_000
    search_max_matches: int = 40
    search_max_file_bytes: int = 512 * 1024
    command_max_timeout: int = 600
    skills: Any | None = None


@dataclass
class ToolResult:
    name: str = ""
    ok: bool = True
    output: str = ""
    truncated: bool = False
    duration_ms: int = 0


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出工作目录内某个子目录的内容（类型、大小、名称），用于了解项目结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的路径，默认 '.'（工作目录根）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件内容，带行号；大文件会被截断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的文件路径"},
                    "start_line": {"type": "integer", "description": "起始行号（1 起），默认 1"},
                    "end_line": {"type": "integer", "description": "结束行号（含），0 表示到结尾，默认 0"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或整体覆盖一个文本文件，自动创建父目录。大改动或新文件用这个。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的文件路径"},
                    "content": {"type": "string", "description": "文件完整内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "把文件中唯一出现的一段旧文本替换为新文本；old_text 必须与文件内容完全一致（含空白），且只允许出现一次，否则报错。小改动优先用这个。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的文件路径"},
                    "old_text": {"type": "string", "description": "要被替换的原文片段（精确匹配）"},
                    "new_text": {"type": "string", "description": "替换后的新内容"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "在工作目录内用正则表达式搜索文件内容，返回 文件:行号:内容 列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式"},
                    "path": {"type": "string", "description": "搜索起点，默认 '.'"},
                    "case_sensitive": {"type": "boolean", "description": "是否区分大小写，默认 false"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在工作目录内执行一条命令并返回退出码与输出；执行前需要用户确认。用测试、构建、git status 等验证改动。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的完整命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 30，上限 600；长驻服务探测建议传 10"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出当前可用的技能（skill）与用途。技能是可选的专门工作方法，任务匹配时按需加载。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "加载指定技能的完整说明到对话上下文，之后严格按其中的步骤执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称，来自 list_skills 或系统提示词"},
                },
                "required": ["name"],
            },
        },
    },
]


# ---------------------------------------------------------------- 路径安全

def resolve_workspace_path(raw: str, workspace: Path, *, must_exist: bool = False) -> Path:
    """把工具传入的路径解析并约束在工作目录内，否则抛 ToolError。"""
    if not raw or not raw.strip():
        raise ToolError("路径不能为空")
    try:
        path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
    except Exception as exc:
        raise ToolError(f"路径不合法：{raw!r}") from exc
    if not path.is_absolute():
        path = workspace / path
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        raise ToolError(f"路径超出工作目录范围，已拒绝：{raw!r}（工作目录：{workspace}）")
    if must_exist and not resolved.exists():
        raise ToolError(f"路径不存在：{raw!r}")
    return resolved


def _rel(path: Path, workspace: Path) -> str:
    try:
        return str(path.relative_to(workspace)) or "."
    except ValueError:
        return str(path)


def _int_arg(args: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = args.get(key, default)
    if value is None:
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ToolError(f"{key} 必须是整数，收到 {value!r}")
    if not minimum <= value <= maximum:
        raise ToolError(f"{key} 超出范围 [{minimum}, {maximum}]，收到 {value}")
    return value


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n[输出过长，已截断，共 {len(text)} 字符]", True


def _decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- 工具实现

def _tool_list_files(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    path = resolve_workspace_path(str(args.get("path") or "."), ctx.workspace, must_exist=True)
    if not path.is_dir():
        raise ToolError(f"不是目录：{_rel(path, ctx.workspace)}")
    entries: list[str] = []
    children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    for child in children:
        kind = "dir " if child.is_dir() else "file"
        try:
            size = str(child.stat().st_size) if child.is_file() else "-"
        except OSError:
            size = "?"
        entries.append(f"{kind} {size:>9}  {child.name}")
    if not entries:
        return ToolResult("list_files", True, f"目录为空：{_rel(path, ctx.workspace)}")
    if len(entries) > 200:
        entries = entries[:200] + [f"... 共 {len(children)} 项，仅显示前 200 项"]
    return ToolResult("list_files", True, "\n".join(entries))


def _tool_read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    path = resolve_workspace_path(str(args.get("path") or ""), ctx.workspace, must_exist=True)
    if not path.is_file():
        raise ToolError(f"不是文件：{_rel(path, ctx.workspace)}")
    start = _int_arg(args, "start_line", 1, 1, 10 ** 7)
    end = _int_arg(args, "end_line", 0, 0, 10 ** 7)
    if end and end < start:
        raise ToolError(f"end_line（{end}）不能小于 start_line（{start}）")

    size = path.stat().st_size
    truncated = False
    if size > ctx.read_max_bytes:
        with path.open("rb") as handle:
            raw = handle.read(ctx.read_max_bytes)
        text = raw.decode("utf-8", errors="replace")
        truncated = True
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    lines = text.splitlines()
    too_many = len(lines) > ctx.read_max_lines
    if too_many:
        lines = lines[: ctx.read_max_lines]
    selected = lines[start - 1 : end if end > 0 else None]
    if not selected:
        return ToolResult("read_file", True, "(所选区间无内容)")
    numbered = [f"{i:>6}| {line}" for i, line in enumerate(selected, start)]
    output = "\n".join(numbered)
    notes: list[str] = []
    if truncated:
        notes.append(f"文件较大（{size} 字节），仅读取前 {ctx.read_max_bytes} 字节")
    if too_many and (end == 0 or end > ctx.read_max_lines):
        notes.append(f"共 {len(text.splitlines())} 行，仅显示前 {ctx.read_max_lines} 行")
    if notes:
        output += "\n[提示] " + "；".join(notes)
    return ToolResult("read_file", True, output)


def _tool_write_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    path = resolve_workspace_path(str(args.get("path") or ""), ctx.workspace)
    content = args.get("content")
    if content is None:
        raise ToolError("缺少 content 参数")
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content), encoding="utf-8")
    action = "已更新" if existed else "已创建"
    return ToolResult("write_file", True, f"{action} {_rel(path, ctx.workspace)}（{len(content)} 字符）")


def _tool_replace_in_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    path = resolve_workspace_path(str(args.get("path") or ""), ctx.workspace, must_exist=True)
    if not path.is_file():
        raise ToolError(f"不是文件：{_rel(path, ctx.workspace)}")
    old = args.get("old_text")
    new = args.get("new_text")
    if old is None or new is None:
        raise ToolError("缺少 old_text / new_text 参数")
    if old == "":
        raise ToolError("old_text 不能为空")
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise ToolError(
            f"未找到要替换的内容（出现 0 次）。old_text 必须与文件内容完全一致（含空白）。"
            f"old_text 开头：{old[:80]!r}"
        )
    if count > 1:
        raise ToolError(
            f"old_text 在文件中出现 {count} 次，不够唯一。请补充更多上下文使 old_text 只匹配一处，"
            f"或改用 write_file 整文件重写。"
        )
    updated = text.replace(old, new)
    path.write_text(updated, encoding="utf-8")
    return ToolResult("replace_in_file", True, f"已替换 1 处（{_rel(path, ctx.workspace)}），文件现共 {len(updated)} 字符")


def _tool_search_files(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        raise ToolError("缺少 pattern 参数")
    flags = 0 if args.get("case_sensitive") else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError(f"正则表达式无效：{exc}") from exc
    base = resolve_workspace_path(str(args.get("path") or "."), ctx.workspace, must_exist=True)

    matches: list[str] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if filename.startswith("."):
                continue
            file_path = Path(root) / filename
            try:
                if file_path.stat().st_size > ctx.search_max_file_bytes:
                    continue
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{_rel(file_path, ctx.workspace)}:{lineno}: {line.strip()[:200]}")
                    if len(matches) >= ctx.search_max_matches:
                        break
            if len(matches) >= ctx.search_max_matches:
                break
    if not matches:
        return ToolResult("search_files", True, f"未找到匹配 {pattern!r} 的内容。")
    output = "\n".join(matches)
    if len(matches) == ctx.search_max_matches:
        output += f"\n[提示] 已达上限，仅显示前 {ctx.search_max_matches} 条"
    return ToolResult("search_files", True, output)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """终止整个进程树：Windows 用 taskkill /T /F，POSIX 用进程组信号。"""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _tool_run_command(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    command = str(args.get("command") or "").strip()
    if not command:
        raise ToolError("缺少 command 参数")
    lowered = command.lower()
    for fragment in _BLOCKED_FRAGMENTS:
        if fragment in lowered:
            raise ToolError(
                f"命令被安全策略拦截（命中危险片段 {fragment!r}）。如确需执行，请自行在终端运行并说明原因。"
            )
    timeout = _int_arg(args, "timeout", 30, 1, ctx.command_max_timeout)

    verdict = ctx.approver.approve(command)
    if verdict in ("no", "skip"):
        message = "用户拒绝了该命令的执行。" if verdict == "no" else "用户跳过了该命令。"
        return ToolResult("run_command", False, message)

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    start = time.monotonic()
    timed_out = False
    returncode: int | None = None
    stdout_bytes = b""
    stderr_bytes = b""
    try:
        # 输出写入临时文件而非管道：即使孙进程存活，也不会因为管道句柄
        # 未关闭导致主进程永久阻塞（Windows 上的已知陷阱）。
        with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
            popen_kwargs: dict[str, Any] = {
                "shell": True,
                "cwd": str(ctx.workspace),
                "stdout": out_file,
                "stderr": err_file,
                "env": env,
            }
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True  # 独立进程组，便于整组击杀
            proc = subprocess.Popen(command, **popen_kwargs)
            try:
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(proc)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            out_file.seek(0)
            err_file.seek(0)
            stdout_bytes = out_file.read()
            stderr_bytes = err_file.read()
    except OSError as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ToolResult("run_command", False, f"命令无法执行：{exc}", duration_ms=elapsed)

    stdout, _ = _truncate(_decode_output(stdout_bytes), ctx.output_chars)
    stderr, _ = _truncate(_decode_output(stderr_bytes), ctx.output_chars)
    if timed_out:
        status_line = f"退出码：超时（>{timeout}s，已终止整个进程树）"
        ok = False
    else:
        status_line = f"退出码：{returncode}"
        ok = returncode == 0
    output = "\n".join([status_line, "--- stdout ---", stdout or "(无输出)", "--- stderr ---", stderr or "(无输出)"])
    if timed_out:
        output += "\n[重要] 该命令及其子进程已被强制终止，任何服务都不会继续运行；如需后台运行：Windows 用 start \"\" cmd /c \"命令 > 日志 2>&1\"，macOS/Linux 用 nohup 命令 > 日志 2>&1 &，随后用 curl 探测端口验证。"
    elapsed = int((time.monotonic() - start) * 1000)
    return ToolResult("run_command", ok, output, duration_ms=elapsed)


def _tool_list_skills(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    registry = ctx.skills
    if registry is None:
        return ToolResult("list_skills", True, "技能功能未启用（未配置技能目录）。")
    return ToolResult("list_skills", True, registry.list_text())


def _tool_use_skill(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    registry = ctx.skills
    if registry is None:
        return ToolResult("use_skill", False, "技能功能未启用（未配置技能目录）。")
    name = str(args.get("name") or "").strip()
    if not name:
        raise ToolError("缺少 name 参数")
    try:
        return ToolResult("use_skill", True, registry.load_text(name))
    except SkillError as exc:
        raise ToolError(str(exc)) from exc


_IMPLEMENTATIONS: dict[str, Callable[[dict[str, Any], ToolContext], ToolResult]] = {
    "list_files": _tool_list_files,
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "replace_in_file": _tool_replace_in_file,
    "search_files": _tool_search_files,
    "run_command": _tool_run_command,
    "list_skills": _tool_list_skills,
    "use_skill": _tool_use_skill,
}


def run_tool(name: str, arguments: Any, ctx: ToolContext) -> ToolResult:
    """统一入口：未知工具 / ToolError / 未预期异常都转成反馈给模型的文本，绝不让主循环崩溃。"""
    impl = _IMPLEMENTATIONS.get(name)
    if impl is None:
        return ToolResult(name, False, f"未知工具 {name!r}，可用工具：{', '.join(sorted(_IMPLEMENTATIONS))}")
    args = arguments if isinstance(arguments, dict) else {}
    start = time.monotonic()
    try:
        result = impl(args, ctx)
    except ToolError as exc:
        result = ToolResult(name, False, f"错误：{exc}")
    except Exception as exc:  # 兜底：任何未预期异常都回传给模型
        result = ToolResult(name, False, f"未预期错误：{type(exc).__name__}: {exc}")
    result.name = name
    result.duration_ms = int((time.monotonic() - start) * 1000)
    return result
