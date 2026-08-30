#!/usr/bin/env python3
"""编程智能体 CLI 入口。

用法示例：
  python agent.py "修复 demo 里的 bug 并补上单元测试" --workspace demo
  python agent.py                              # 进入交互模式
  python agent.py --resume 20260827-103000    # 恢复会话

凭据：通过环境变量 ZHIPU_API_KEY 提供，或写入 config.local.json（不入库）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from coding_agent import __version__
from coding_agent.config import DEFAULT_BASE_URL, DEFAULT_MODEL, Config, ConfigError
from coding_agent.context import MessageStore
from coding_agent.llm import LLMClient
from coding_agent.loop import Agent, RunStats, format_stats
from coding_agent.prompts import build_system_prompt
from coding_agent.skills import SkillRegistry
from coding_agent.session import (
    list_sessions,
    load_session,
    new_session_path,
    resolve_session,
    save_session,
)
from coding_agent.tools import ToolContext
from coding_agent.ui import TerminalApprover, UI

HELP_TEXT = """内置命令：
  /help     显示本帮助
  /clear    清空对话历史（保留系统提示）
  /compact  立即压缩对话历史
  /sessions 选择并恢复会话（↑↓ 选择，Enter 恢复）
  /sessions resume <名称>  切换会话
  /skills   列出可用技能
  /stats    显示当前任务统计
  /exit     保存会话并退出"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nihue",
        description="Nihue：与大语言模型交互，自主读写文件、执行命令完成编程任务的智能体。",
    )
    parser.add_argument("task", nargs="*", help="任务描述（留空进入交互模式）")
    parser.add_argument("-w", "--workspace", default=".", help="工作目录（文件操作限制在内），默认当前目录")
    parser.add_argument("-m", "--model", help=f"模型名，默认 {DEFAULT_MODEL}（智谱控制台可用模型为准）")
    parser.add_argument("--base-url", help=f"OpenAI 兼容接口地址，默认智谱官方 {DEFAULT_BASE_URL}")
    parser.add_argument("--api-key", help="API Key（推荐用环境变量 ZHIPU_API_KEY）")
    parser.add_argument("--max-turns", type=int, help="最大轮数，默认 30")
    parser.add_argument("--max-tokens", type=int, help="单次回复最大 token，默认 4096")
    parser.add_argument("--temperature", type=float, help="采样温度，默认 0.2")
    parser.add_argument("--auto-approve", action="store_true", help="自动放行所有命令（仅限可信环境/录制演示）")
    parser.add_argument("--plan", action="store_true", help="先输出计划，人工确认后再执行")
    parser.add_argument("--no-reasoning", action="store_true", help="隐藏模型思考过程")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    parser.add_argument("--no-save", action="store_true", help="不保存会话记录")
    parser.add_argument("--context-budget", type=int, help="触发历史压缩的 token 预算，默认 24000")
    parser.add_argument("--resume", metavar="SESSION", help="恢复会话（文件名或前缀）")
    parser.add_argument("--list-sessions", action="store_true", help="列出已保存会话")
    parser.add_argument("--skills-dir", dest="skills_dirs", action="append", help="额外技能目录（可多次指定，同名技能覆盖内置目录）")
    parser.add_argument("--list-skills", action="store_true", help="列出可用技能")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印调试信息（不会打印 API Key）")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def cli_overrides(args: argparse.Namespace) -> dict:
    return {
        "api_key": args.api_key,
        "model": args.model,
        "base_url": args.base_url,
        "max_turns": args.max_turns,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "context_budget": args.context_budget,
        "auto_approve": True if args.auto_approve else None,
        "plan_first": True if args.plan else None,
        "show_reasoning": False if args.no_reasoning else None,
        "color": False if args.no_color else None,
        "save_session": False if args.no_save else None,
        "verbose": True if args.verbose else None,
    }


def run_repl(agent: Agent, ui: UI, session_path: Path | None, skills: SkillRegistry | None = None) -> None:
    ui.info("输入任务描述开始（/help 查看内置命令，/exit 退出）。")
    while True:
        try:
            line = ui.task_input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/exit":
            break
        if line == "/clear":
            agent.store.reset()
            agent.stats = RunStats()
            ui.info("历史已清空。")
            continue
        if line == "/compact":
            if agent.store.compact(agent.client):
                ui.info("压缩完成。")
            else:
                ui.info("当前无需压缩，或压缩失败。")
            continue
        if line == "/stats":
            ui.info(format_stats(agent.store, agent.stats))
            continue
        if line == "/sessions":
            entries = list_sessions()
            choice = ui.pick_session(
                [(entry.title, f"{entry.mtime:%m-%d %H:%M}  {entry.size} 字节") for entry in entries]
            )
            if choice is None:
                continue
            path = entries[choice].path
            agent.store = load_session(path, agent.store)
            agent.stats = RunStats()
            session_path = path
            ui.info(f"已切换会话：{path.name}（{len(agent.store.messages)} 条消息）")
            continue
        if line.startswith("/sessions resume "):
            try:
                path = resolve_session(line.split(maxsplit=2)[2])
            except FileNotFoundError as exc:
                ui.warn(str(exc))
                continue
            agent.store = load_session(path, agent.store)
            agent.stats = RunStats()
            session_path = path
            ui.info(f"已切换会话：{path.name}（{len(agent.store.messages)} 条消息）")
            continue
        if line.startswith("/sessions"):
            ui.warn("用法：/sessions（列出）或 /sessions resume <会话名或前缀>")
            continue
        if line == "/skills":
            if skills is None:
                ui.warn("技能功能未启用。")
            else:
                ui.info(skills.list_text())
            continue
        if line == "/help":
            ui.info(HELP_TEXT)
            continue
        if line.startswith("/"):
            ui.warn(f"未知命令：{line}（/help 查看内置命令）")
            continue
        stats = agent.run(line)
        ui.info(format_stats(agent.store, stats))
        if session_path is not None:
            save_session(session_path, agent.store)



def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.from_env(Path(args.workspace), **cli_overrides(args))
    except ConfigError as exc:
        print(f"配置错误：{exc}")
        return 1

    ui = UI(color=config.color)

    if args.list_sessions:
        entries = list_sessions()
        if not entries:
            print("（暂无已保存会话）")
        for entry in entries:
            print(f"{entry.title}  （{entry.name}，{entry.mtime:%m-%d %H:%M}，{entry.size} 字节）")
        return 0

    skill_roots: list[tuple[Path, str]] = [(Path.home() / ".nihue" / "skills", "user")]
    workspace_skills = Path(args.workspace).resolve() / ".nihue" / "skills"
    if workspace_skills != skill_roots[0][0]:
        skill_roots.append((workspace_skills, "project"))
    for extra_dir in args.skills_dirs or []:
        skill_roots.append((Path(extra_dir).expanduser().resolve(), "extra"))
    skills = SkillRegistry(skill_roots)

    if args.list_skills:
        print(skills.list_text())
        return 0

    ui.logo()

    client = LLMClient(config)
    store = MessageStore(
        build_system_prompt(config.workspace, extra=config.extra_system, plan_mode=config.plan_first, skills_text=skills.list_text()),
        context_budget=config.context_budget,
        keep_recent=config.keep_recent,
    )

    session_path: Path | None = None
    if config.save_session:
        if args.resume:
            try:
                session_path = resolve_session(args.resume)
            except FileNotFoundError as exc:
                ui.error(str(exc))
                return 1
            store = load_session(session_path, store)
            ui.info(f"已恢复会话：{session_path.name}（{len(store.messages)} 条消息）")
        else:
            slug = " ".join(args.task).strip() or "interactive"
            session_path = new_session_path(slug=slug)

    approver = TerminalApprover(ui, auto_approve=config.auto_approve)
    tools = ToolContext(
        config.workspace,
        approver,
        read_max_bytes=config.read_max_bytes,
        read_max_lines=config.read_max_lines,
        output_chars=config.tool_output_chars,
        search_max_matches=config.search_max_matches,
        skills=skills,
    )
    agent = Agent(config, client, store, tools, ui)

    task = " ".join(args.task).strip()
    ui.info(f"模型：{config.model} ｜ 工作目录：{config.workspace}")
    if task:
        stats = agent.run(task)
        ui.info(format_stats(agent.store, stats))
    else:
        run_repl(agent, ui, session_path, skills)

    if session_path is not None:
        save_session(session_path, agent.store)
        ui.info(f"会话已保存：{session_path}")

    if agent.stats.stop_reason in ("auth_error", "llm_error"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
