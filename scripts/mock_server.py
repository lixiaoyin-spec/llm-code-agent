"""离线模拟的 OpenAI 兼容服务端：无网络 / 无 API Key 时演练与联调 CLI。

这不是 agent 的一部分，只是开发与录制演示用的替身服务：
- 按请求次数返回一段剧本化的 SSE 流，模拟"读目录 -> 读文件 -> 修复 + 写测试 ->
  运行测试 -> 总结"的完整 agent 会话；
- 同时把工具调用参数切成多个 chunk，覆盖客户端的增量拼接路径。

用法（两个终端）：
  python scripts/mock_server.py --port 8765 --scenario demo
  python agent.py "修复 demo 里的 bug 并补充单元测试" -w demo \
      --base-url http://127.0.0.1:8765/api --api-key mock --auto-approve
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXED_WORDFREQ = '''"""统计一段英文文本中每个单词出现的次数（忽略大小写与标点）。"""

import re


def count_words(text: str) -> dict[str, int]:
    words = re.findall(r"[A-Za-z]+", text)
    counts: dict[str, int] = {}
    for word in words:
        key = word.lower()
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    import sys

    sample = sys.stdin.read() if not sys.stdin.isatty() else "Hello, hello world!"
    print(count_words(sample))
'''

TEST_WORDFREQ = '''import unittest

from wordfreq import count_words


class TestCountWords(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(count_words("Hello hello World"), {"hello": 2, "world": 1})

    def test_ignores_punctuation(self):
        self.assertEqual(count_words("Hi! hi, HI."), {"hi": 3})

    def test_empty_text(self):
        self.assertEqual(count_words(""), {})

    def test_case_insensitive(self):
        self.assertEqual(count_words("Python python PYTHON"), {"python": 3})


if __name__ == "__main__":
    unittest.main()
'''


def split_args(raw: str, width: int = 40) -> list[str]:
    return [raw[i : i + width] for i in range(0, len(raw), width)]


def demo_script(count: int, body: dict) -> list[dict]:
    """按请求次数返回剧本化 chunk 列表。"""
    chunks: list[dict] = []
    if count == 1:
        chunks.append({"choices": [{"index": 0, "delta": {"role": "assistant", "content": "我先看一下目录结构。"}}]})
        args = '{"path": "."}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": args[:6]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[6:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 2:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "再看看 wordfreq.py 的实现。"}}]})
        args = '{"path": "wordfreq.py"}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": args[:8]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[8:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 3:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "发现 bug：counts.get(key, 0) 少了 +1。修复并补充单元测试。"}}]})
        args1 = json.dumps({"path": "wordfreq.py", "content": FIXED_WORDFREQ}, ensure_ascii=False)
        args2 = json.dumps({"path": "test_wordfreq.py", "content": TEST_WORDFREQ}, ensure_ascii=False)
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_3", "type": "function", "function": {"name": "write_file", "arguments": args1[:40]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args1[40:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 1, "id": "call_4", "type": "function", "function": {"name": "write_file", "arguments": args2[:40]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 1, "function": {"arguments": args2[40:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 4:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "运行测试验证一下。"}}]})
        args = '{"command": "python -m unittest discover -s . -v", "timeout": 120}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_5", "type": "function", "function": {"name": "run_command", "arguments": args[:50]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[50:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    else:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "任务完成：已修复 count_words 的计数 bug（counts.get(key, 0) 缺少 +1），新增 4 个单元测试，python -m unittest 全部通过。"}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    return chunks


def generic_script(count: int, body: dict) -> list[dict]:
    chunks: list[dict] = []
    if count == 1:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "（离线模拟）我先看看目录。"}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": '{"path": "."}'}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    else:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "（离线模拟）这是一个通用演示回复：真正的 agent 会在这里继续调用工具完成任务。"}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    return chunks


SCENARIOS = {"demo": demo_script, "generic": generic_script}


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        count = self.server.count + 1
        self.server.count = count
        print(f"[mock] 收到第 {count} 次请求（model={body.get('model')}, 消息数={len(body.get('messages', []))}）")
        chunks = self.server.script(count, body)
        lines = ["data: " + json.dumps(chunk, ensure_ascii=False) for chunk in chunks]
        lines.append("data: [DONE]")
        payload = ("\n\n".join(lines) + "\n\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        for start in range(0, len(payload), 512):
            self.wfile.write(payload[start : start + 512])
            self.wfile.flush()
            time.sleep(0.03)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="离线模拟 OpenAI 兼容服务端（开发联调用）")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="demo")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), MockHandler)
    server.count = 0
    server.script = SCENARIOS[args.scenario]
    print(f"[mock] 监听 http://127.0.0.1:{args.port}/api  （场景：{args.scenario}，Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock] 已退出")


if __name__ == "__main__":
    main()
