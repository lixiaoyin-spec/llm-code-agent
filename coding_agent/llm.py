"""DeepSeek 的 OpenAI 兼容协议客户端。

只使用 requests 完成 HTTP 调用与 SSE 流式解析，不依赖任何 agent 框架/SDK。
自行实现：
- 流式增量解析（content / reasoning_content / tool_calls 跨块拼接）；
- 工具参数 JSON 的容错解析（兼容 markdown 代码块包裹）；
- 429/5xx 指数退避重试（尊重 Retry-After）；
- 错误分类（auth / bad_request / rate_limit / server / network / bad_stream），
  供主循环决定是重试、反馈模型还是中止。
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .config import Config


class LLMError(Exception):
    """模型调用错误。kind 决定上层处理策略。"""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_json: str = ""
    arguments: Any = None
    parse_error: str = ""

    @property
    def signature(self) -> tuple[str, str]:
        """用于主循环的重复调用检测。"""
        return (self.name, self.arguments_json)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class AssistantTurn:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: Usage = field(default_factory=Usage)


def parse_arguments(raw: str) -> tuple[Any, str]:
    """把模型输出的参数字符串解析成对象，失败时返回错误说明（会反馈给模型自纠）。"""
    candidates = [raw]
    stripped = raw.strip()
    if stripped.startswith("```"):
        inner = stripped.strip("`").strip()
        if inner.lower().startswith("json"):
            inner = inner[4:].lstrip()
        candidates.append(inner)
    for candidate in candidates:
        try:
            return json.loads(candidate), ""
        except json.JSONDecodeError:
            continue
    return None, f"工具参数不是合法 JSON：{raw[:200]}"


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.url = config.base_url.rstrip("/") + "/chat/completions"

    # ---- 对外接口 ----
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str = "auto",
        on_text: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantTurn:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        response = self._post_with_retry(payload)
        return self._consume_stream(response, on_text, on_reasoning)

    # ---- 重试与错误分类 ----
    def _post_with_retry(self, payload: dict[str, Any]) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: LLMError | None = None
        for attempt in range(self.config.max_retries + 1):
            retry_after: float | None = None
            try:
                response = self.session.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=(self.config.connect_timeout, self.config.request_timeout),
                )
            except requests.exceptions.Timeout:
                last_error = LLMError("network", "请求超时，请检查网络或接口地址。")
            except requests.exceptions.RequestException as exc:
                last_error = LLMError("network", f"网络错误：{exc}")
            else:
                if response.status_code == 200:
                    return response
                body = self._error_body(response)
                if response.status_code in (401, 403):
                    raise LLMError("auth", "API Key 无效或没有权限，请检查密钥配置。", response.status_code)
                if response.status_code in (400, 404):
                    raise LLMError("bad_request", f"请求被接口拒绝（HTTP {response.status_code}）：{body}", response.status_code)
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = LLMError(
                        "rate_limit" if response.status_code == 429 else "server",
                        f"服务繁忙（HTTP {response.status_code}）：{body}",
                        response.status_code,
                    )
                    header = response.headers.get("Retry-After")
                    if header:
                        try:
                            retry_after = min(float(header), 30.0)
                        except ValueError:
                            retry_after = None
                else:
                    raise LLMError("bad_request", f"未预期的 HTTP 状态 {response.status_code}：{body}", response.status_code)
            if attempt >= self.config.max_retries:
                break
            delay = self._backoff(attempt, retry_after)
            self._log(f"请求失败，{delay:.1f}s 后重试（第 {attempt + 1}/{self.config.max_retries} 次）")
            time.sleep(delay)
        raise last_error or LLMError("network", "模型请求失败")

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        base = self.config.retry_backoff * (2 ** attempt)
        return min(base, 30.0) * (0.7 + 0.6 * random.random())

    @staticmethod
    def _error_body(response: requests.Response) -> str:
        try:
            body = response.text[:500]
        except requests.RequestException:
            body = "(无法读取响应体)"
        finally:
            response.close()
        return body.replace("\n", " ")

    # ---- SSE 流式解析 ----
    def _consume_stream(
        self,
        response: requests.Response,
        on_text: Callable[[str], None] | None,
        on_reasoning: Callable[[str], None] | None,
    ) -> AssistantTurn:
        content: list[str] = []
        reasoning: list[str] = []
        tool_slots: dict[int, dict[str, Any]] = {}
        finish_reason = ""
        usage = Usage()
        if not response.encoding or response.encoding.lower() in ("iso-8859-1", "latin-1"):
            response.encoding = "utf-8"  # 部分网关不下发 charset，避免中文被按 latin-1 解码
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue  # 个别损坏的 SSE 行直接跳过，不影响整体
                finish, chunk_usage = self._apply_chunk(
                    chunk, content, reasoning, tool_slots, on_text, on_reasoning
                )
                if finish:
                    finish_reason = finish
                if chunk_usage is not None:
                    usage = chunk_usage
        finally:
            response.close()

        if finish_reason == "" and not content and not tool_slots:
            raise LLMError("bad_stream", "模型返回了空响应流，请检查模型名与接口地址。")

        turn = AssistantTurn(
            content="".join(content),
            reasoning="".join(reasoning),
            finish_reason=finish_reason or "stop",
            usage=usage,
        )
        for index in sorted(tool_slots):
            slot = tool_slots[index]
            name = "".join(slot["name_parts"])
            if not name:
                continue
            raw_args = "".join(slot["arg_parts"])
            call = ToolCall(id=slot["id"] or f"call_{index}", name=name, arguments_json=raw_args)
            call.arguments, call.parse_error = parse_arguments(raw_args)
            turn.tool_calls.append(call)
        if finish_reason == "tool_calls" and not turn.tool_calls:
            raise LLMError("bad_stream", "模型返回 tool_calls 结束标志，但未解析到任何工具调用。")
        return turn

    @staticmethod
    def _apply_chunk(
        chunk: dict[str, Any],
        content: list[str],
        reasoning: list[str],
        tool_slots: dict[int, dict[str, Any]],
        on_text: Callable[[str], None] | None,
        on_reasoning: Callable[[str], None] | None,
    ) -> tuple[str | None, Usage | None]:
        """把一个 SSE chunk 并入累积状态，返回 (finish_reason, usage)。"""
        finish: str | None = None
        usage: Usage | None = None
        raw_usage = chunk.get("usage")
        if isinstance(raw_usage, dict):
            usage = Usage(
                int(raw_usage.get("prompt_tokens") or 0),
                int(raw_usage.get("completion_tokens") or 0),
            )
        choices = chunk.get("choices") or []
        if not choices:
            return finish, usage
        choice = choices[0]
        if choice.get("finish_reason"):
            finish = choice["finish_reason"]
        delta = choice.get("delta") or {}
        if delta.get("content"):
            text = delta["content"]
            content.append(text)
            if on_text:
                on_text(text)
        if delta.get("reasoning_content"):
            text = delta["reasoning_content"]
            reasoning.append(text)
            if on_reasoning:
                on_reasoning(text)
        for item in delta.get("tool_calls") or []:
            index = int(item.get("index", 0))
            slot = tool_slots.setdefault(index, {"id": "", "name_parts": [], "arg_parts": []})
            if item.get("id"):
                slot["id"] = item["id"]
            fn = item.get("function") or {}
            if fn.get("name"):
                slot["name_parts"].append(fn["name"])
            if fn.get("arguments"):
                slot["arg_parts"].append(fn["arguments"])
        return finish, usage

    def _log(self, message: str) -> None:
        if self.config.verbose:
            print(f"[llm] {message}", file=sys.stderr)
