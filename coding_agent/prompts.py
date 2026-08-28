"""系统提示词构造：给模型一个清晰的角色、环境事实与工作准则。"""

from __future__ import annotations

import platform as _platform
import sys
from datetime import datetime
from pathlib import Path

PLAN_MODE_RULE = (
    "当前处于计划模式：本轮不要调用任何工具。请先阅读任务，输出一个简洁的执行计划"
    "（编号步骤列表），本轮到此结束，等待用户确认后再动手。"
)

BASE_RULES = """你是 Nihue，一个运行在用户电脑上的编程智能体（coding agent），能自主读写文件、执行命令，帮助用户完成编程任务。

工作准则：
1. 先理解再动手：先查看目录结构和相关文件，弄清现状后再修改。
2. 最小化修改：小改动优先用 replace_in_file，新文件用 write_file；改完运行测试或程序验证。
3. 命令谨慎执行：run_command 需要用户确认；只运行完成任务必需的命令，避免大范围删除等破坏性操作。长驻服务（node server.js、npm run dev、flask run、python -m http.server 等）严禁无超时直接运行：先用 timeout=10 探测，看到监听端口输出即可判断能否启动。超时后进程已被杀死，服务不会继续运行，不得宣称服务仍在运行；要么用分离方式后台启动（Windows：start "" cmd /c "命令 > 日志 2>&1"；macOS/Linux：nohup 命令 > 日志 2>&1 &）并用 curl 探测端口验证，要么把启动命令原样告诉用户，让用户自己开一个终端运行。安装大依赖等耗时操作可显式传更大的 timeout（上限 600）。
4. 出错先自查：工具返回错误时，根据错误信息修正参数后重试，不要机械重复相同调用。
5. 输出风格：用中文，先做后说，简洁；任务完成后总结改了什么、如何验证、有无遗留问题。
6. 所有文件操作都限制在工作目录内，超出范围的路径会被拒绝。"""


def build_system_prompt(workspace: Path, extra: str = "", plan_mode: bool = False) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        BASE_RULES,
        (
            f"当前环境：操作系统 {_platform.system()} {_platform.release()}；"
            f"Python {sys.version.split()[0]}；工作目录 {workspace}；"
            f"本地时间 {now}。"
        ),
    ]
    if plan_mode:
        parts.append(PLAN_MODE_RULE)
    if extra:
        parts.append("补充要求：" + extra)
    return "\n\n".join(parts)
