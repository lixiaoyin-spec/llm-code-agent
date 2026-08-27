"""对话历史与上下文管理。

- 维护 OpenAI 兼容格式的消息列表（system / user / assistant / tool）；
- 用启发式估算 token（中文按 1 字符 ≈ 1 token，其余 3 字符 ≈ 1 token）。
  估算只用于"何时压缩"的决策，阈值留有冗余，不需要精确；
- 超过预算时把早期消息压缩成一段模型生成的摘要，保留最近若干条完整消息，
  兼顾上下文连贯性与成本/延迟；压缩失败则按兵不动，宁可继续跑也不丢历史。

注意 tool 角色消息必须紧跟产生它的 assistant 消息，因此压缩截断时要
把开头悬挂的 tool 消息丢掉，保证发往 API 的序列永远合法。
"""

from __future__ import annotations

import json
from typing import Any

from .llm import AssistantTurn, LLMClient, LLMError


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 2) // 3


class MessageStore:
    def __init__(self, system_prompt: str, *, context_budget: int = 24_000, keep_recent: int = 8):
        self.system_prompt = system_prompt
        self.context_budget = context_budget
        self.keep_recent = max(2, keep_recent)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.compaction_count = 0

    # ---- 写入 ----
    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, turn: AssistantTurn) -> None:
        message: dict[str, Any] = {"role": "assistant", "content": turn.content or ""}
        if turn.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments_json},
                }
                for call in turn.tool_calls
            ]
        self.messages.append(message)

    def add_tool_result(self, call_id: str, name: str, text: str) -> None:
        self.messages.append(
            {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}
        )

    # ---- 读取 ----
    def api_messages(self) -> list[dict[str, Any]]:
        """返回可发往 API 的消息列表（浅拷贝，调用方不得修改）。"""
        return [dict(m) for m in self.messages]

    def estimated_tokens(self) -> int:
        total = 0
        for message in self.messages:
            total += 4  # 每条消息的结构开销
            content = message.get("content")
            if isinstance(content, str):
                total += estimate_tokens(content)
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                total += 16
                total += estimate_tokens(str(fn.get("name", "")))
                total += estimate_tokens(str(fn.get("arguments", "")))
        return total

    # ---- 压缩 ----
    def needs_compaction(self) -> bool:
        return self.estimated_tokens() > self.context_budget and len(self.messages) > self.keep_recent + 4

    def compact(self, client: LLMClient) -> bool:
        """超过预算时压缩历史，成功返回 True。"""
        if not self.needs_compaction():
            return False
        tail = self.messages[1:]
        keep = tail[-self.keep_recent:]
        while keep and keep[0].get("role") == "tool":
            keep.pop(0)  # 保证截断后的序列合法
        history = tail[: len(tail) - len(keep)]
        summary = self._summarize(client, history)
        if not summary:
            return False
        self.messages = [
            self.messages[0],
            {"role": "user", "content": "【此前对话摘要】\n" + summary},
        ] + keep
        self.compaction_count += 1
        return True

    def _summarize(self, client: LLMClient, history: list[dict[str, Any]]) -> str:
        serialized = json.dumps(history, ensure_ascii=False)
        if len(serialized) > 16_000:
            serialized = serialized[:16_000] + "（截断）"
        ask = [
            {
                "role": "system",
                "content": (
                    "你是对话压缩助手。把下面的历史消息压缩成一段中文摘要，保留：任务目标、"
                    "已修改/创建的文件、关键发现与错误、进行中事项、用户约束。不超过 300 字，直接输出摘要。"
                ),
            },
            {"role": "user", "content": serialized},
        ]
        try:
            turn = client.chat(ask, tools=None, max_tokens=600, temperature=0.1)
        except LLMError:
            return ""
        return (turn.content or "").strip()

    # ---- 序列化（供会话保存/恢复） ----
    def to_records(self) -> list[dict[str, Any]]:
        return [dict(m) for m in self.messages]

    @classmethod
    def from_records(
        cls, system_prompt: str, records: list[dict[str, Any]], **kwargs: Any
    ) -> "MessageStore":
        store = cls(system_prompt, **kwargs)
        store.messages = [
            {"role": "system", "content": system_prompt}
        ] + [dict(record) for record in records if record.get("role") != "system"]
        return store
