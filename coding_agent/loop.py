"""Agent 主循环：模型调用 -> 输出解析 -> 工具执行 -> 结果反馈，直到满足终止条件。

终止条件（每个都经过设计，面试可展开讲）：
1. 模型返回不带 tool_calls 的回复 —— 自然完成任务；
2. 达到 max_turns 上限 —— 防止失控长跑、烧 token；
3. 连续 3 轮发出完全相同的工具调用 —— 防止死循环；
4. 用户 Ctrl+C 中断 —— 立即停止并保留会话；
5. API 认证失败 —— 立即退出并给出配置指引；网络/服务错误经客户端
   重试仍失败则中止，不假装成功。

执行策略：只读工具（list_files / read_file / search_files）无副作用，可并行；
写文件与命令有副作用且可能相互依赖，必须按模型给出的顺序串行执行。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import Config
from .context import MessageStore
from .llm import AssistantTurn, LLMClient, LLMError, ToolCall
from .tools import TOOL_SCHEMAS, ToolContext, ToolResult, run_tool
from .ui import UI

READ_ONLY_TOOLS = {"list_files", "read_file", "search_files"}


@dataclass
class RunStats:
    turns: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_seconds: float = 0.0
    finished_naturally: bool = True
    stop_reason: str = ""


class Agent:
    def __init__(self, config: Config, client: LLMClient, store: MessageStore, tools: ToolContext, ui: UI):
        self.config = config
        self.client = client
        self.store = store
        self.tools = tools
        self.ui = ui
        self.stats = RunStats()
        self._plan_pending = False
        self._recent_signatures: list[tuple[tuple[str, str], ...]] = []

    # ---- 对外入口 ----
    def run(self, task: str) -> RunStats:
        """执行一条用户任务，直到自然结束或触发终止条件。"""
        message = task
        if self.config.plan_first:
            self._plan_pending = True
            message += "\n\n（当前为计划模式：请先阅读任务，输出简洁的执行计划步骤列表，本轮不要调用任何工具。）"
        self.store.add_user(message)
        return self._run_until_stop()

    # ---- 主循环 ----
    def _run_until_stop(self) -> RunStats:
        start = time.monotonic()
        while self.stats.turns < self.config.max_turns:
            if self.store.needs_compaction():
                self.ui.info("上下文接近预算，正在压缩历史...")
                if self.store.compact(self.client):
                    self.ui.info(f"已压缩（累计第 {self.store.compaction_count} 次）")
                else:
                    self.ui.warn("压缩未执行（摘要调用失败），继续运行。")

            self.stats.turns += 1
            self.ui.turn_header(self.stats.turns, self.config.max_turns)
            try:
                turn = self.client.chat(
                    self.store.api_messages(),
                    TOOL_SCHEMAS,
                    on_text=self.ui.stream_text,
                    on_reasoning=self.ui.stream_reasoning if self.config.show_reasoning else None,
                )
            except KeyboardInterrupt:
                self.ui.newline()
                self.stats.stop_reason = "user_interrupt"
                self.stats.finished_naturally = False
                break
            except LLMError as exc:
                if exc.kind == "auth":
                    self.ui.error(f"API 认证失败：{exc.message}")
                    self.ui.error("请设置环境变量 ZHIPU_API_KEY（或写入 config.local.json）后重试。")
                    self.stats.stop_reason = "auth_error"
                else:
                    self.ui.error(f"模型调用失败（{exc.kind}）：{exc.message}")
                    self.stats.stop_reason = "llm_error"
                self.stats.finished_naturally = False
                break

            self.ui.end_turn()
            self.store.add_assistant(turn)
            if turn.usage.prompt_tokens:
                self.stats.prompt_tokens += turn.usage.prompt_tokens
            self.stats.completion_tokens += turn.usage.completion_tokens

            if not turn.tool_calls:
                if self._plan_pending:
                    self._plan_pending = False
                    self.ui.newline()
                    if self.ui.ask_yes_no("是否按此计划执行？"):
                        self.store.add_user("计划已确认，请开始执行。")
                        continue
                    self.stats.stop_reason = "plan_rejected"
                else:
                    self.stats.stop_reason = "model_finished"
                break

            try:
                self._execute_and_feedback(turn.tool_calls)
            except KeyboardInterrupt:
                self.ui.newline()
                self.stats.stop_reason = "user_interrupt"
                self.stats.finished_naturally = False
                break

            if self._detect_repetition(turn.tool_calls):
                self.ui.warn("检测到连续 3 轮完全相同的工具调用，疑似死循环，已中止。")
                self.stats.stop_reason = "repeated_calls"
                self.stats.finished_naturally = False
                break
        else:
            self.ui.warn(f"达到最大轮数上限（{self.config.max_turns}），已停止。可用 --max-turns 调大。")
            self.stats.stop_reason = "max_turns"
            self.stats.finished_naturally = False

        self.stats.wall_seconds = time.monotonic() - start
        self.stats.prompt_tokens = max(self.stats.prompt_tokens, self.store.estimated_tokens())
        return self.stats

    # ---- 工具执行 ----
    def _execute_and_feedback(self, calls: list[ToolCall]) -> None:
        results: list[ToolResult | None] = [None] * len(calls)
        read_indices = [i for i, call in enumerate(calls) if call.name in READ_ONLY_TOOLS]
        other_indices = [i for i in range(len(calls)) if i not in read_indices]

        if read_indices:
            with ThreadPoolExecutor(max_workers=min(4, len(read_indices))) as pool:
                futures = {
                    pool.submit(run_tool, calls[i].name, calls[i].arguments, self.tools): i
                    for i in read_indices
                }
                for future, index in futures.items():
                    results[index] = future.result()
        for index in other_indices:
            results[index] = run_tool(calls[index].name, calls[index].arguments, self.tools)

        for call, result in zip(calls, results):
            assert result is not None
            preview = result.output.replace("\n", " ")[:120]
            self.ui.tool_call(call.name, self._args_preview(call))
            self.ui.tool_result(call.name, result.ok, preview, result.duration_ms)
            self.stats.tool_calls += 1
            if not result.ok:
                self.stats.tool_failures += 1
            content = result.output if result.ok else f"错误：{result.output}"
            self.store.add_tool_result(call.id, call.name, content)

    @staticmethod
    def _args_preview(call: ToolCall) -> str:
        if call.parse_error:
            return call.parse_error
        if isinstance(call.arguments, dict):
            short = {key: (str(value)[:40] + "..." if len(str(value)) > 40 else value)
                     for key, value in call.arguments.items()}
            return json.dumps(short, ensure_ascii=False)
        return str(call.arguments)[:80]

    def _detect_repetition(self, calls: list[ToolCall]) -> bool:
        signature = tuple(call.signature for call in calls)
        self._recent_signatures.append(signature)
        if len(self._recent_signatures) > 3:
            self._recent_signatures.pop(0)
        return (
            len(self._recent_signatures) == 3
            and self._recent_signatures[0] == signature
            and self._recent_signatures[1] == signature
        )


def format_stats(store: MessageStore, stats: RunStats) -> str:
    return (
        f"停止原因：{stats.stop_reason or '-'} ｜ 轮数 {stats.turns} ｜ "
        f"工具调用 {stats.tool_calls} 次（失败 {stats.tool_failures}）｜ "
        f"耗时 {stats.wall_seconds:.1f}s ｜ 上下文约 {store.estimated_tokens()} tokens"
        f"（压缩 {store.compaction_count} 次）"
    )
