"""离线模拟的 OpenAI 兼容服务端：无网络 / 无 API Key 时演练与联调 CLI。

这不是 agent 的一部分，只是开发与录制演示用的替身服务：
- 按请求次数返回一段剧本化的 SSE 流，模拟"读目录 -> 读文件 -> 修复 + 写测试 ->
  运行测试 -> 总结"的完整 agent 会话；
- 同时把工具调用参数切成多个 chunk，覆盖客户端的增量拼接路径。

用法（两个终端）：
  python scripts/mock_server.py --port 8765 --scenario demo
  python agent.py "给 wordfreq.py 增加一个 --top N 命令行参数：按词频从高到低只输出前 N 个词（默认输出全部），并补充对应的单元测试，运行测试确保全部通过" -w demo \
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



TOPN_WORDFREQ = "\"\"\"统计一段英文文本中每个单词出现的次数（忽略大小写与标点）。\"\"\"\n\nimport re\nimport sys\nimport argparse\n\n\ndef count_words(text: str, top: int = None) -> dict[str, int]:\n    words = re.findall(r\"[A-Za-z]+\", text)\n    counts: dict[str, int] = {}\n    for word in words:\n        key = word.lower()\n        counts[key] = counts.get(key, 0) + 1\n    \n    # 按词频从高到低排序，词频相同时按字母顺序排序\n    sorted_counts = dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))\n    \n    # 如果指定了top参数，只返回前N个\n    if top is not None and top > 0:\n        # 取前top个，如果top大于实际数量则返回全部\n        items = list(sorted_counts.items())[:top]\n        return dict(items)\n    elif top is not None and top <= 0:\n        # top <= 0 时返回空字典\n        return {}\n    \n    return sorted_counts\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=\"统计英文单词出现频率\")\n    parser.add_argument(\"--top\", type=int, default=None, \n                       help=\"只输出前N个高频词（默认输出全部）\")\n    args = parser.parse_args()\n    \n    sample = sys.stdin.read() if not sys.stdin.isatty() else \"Hello, hello world!\"\n    result = count_words(sample, args.top)\n    print(result)\n\n\nif __name__ == \"__main__\":\n    main()\n"

TOPN_TESTS = "\"\"\"单元测试：统计英文单词出现次数\"\"\"\n\nimport unittest\nfrom wordfreq import count_words\n\n\nclass TestWordFreq(unittest.TestCase):\n    def test_empty_text(self):\n        \"\"\"测试空文本\"\"\"\n        result = count_words(\"\")\n        self.assertEqual(result, {})\n    \n    def test_single_word(self):\n        \"\"\"测试单个单词\"\"\"\n        result = count_words(\"hello\")\n        self.assertEqual(result, {\"hello\": 1})\n    \n    def test_case_insensitive(self):\n        \"\"\"测试大小写不敏感\"\"\"\n        result = count_words(\"Hello hello HELLO\")\n        self.assertEqual(result, {\"hello\": 3})\n    \n    def test_with_punctuation(self):\n        \"\"\"测试包含标点符号\"\"\"\n        result = count_words(\"Hello, world! Hello, everyone.\")\n        self.assertEqual(result, {\"hello\": 2, \"world\": 1, \"everyone\": 1})\n    \n    def test_mixed_content(self):\n        \"\"\"测试混合内容\"\"\"\n        result = count_words(\"The quick brown fox jumps over the lazy dog. The dog was not amused.\")\n        expected = {\n            \"the\": 3, \"quick\": 1, \"brown\": 1, \"fox\": 1, \n            \"jumps\": 1, \"over\": 1, \"lazy\": 1, \"dog\": 2, \n            \"was\": 1, \"not\": 1, \"amused\": 1\n        }\n        self.assertEqual(result, expected)\n    \n    def test_numbers_and_symbols(self):\n        \"\"\"测试数字和符号被忽略\"\"\"\n        result = count_words(\"123 test 456 test! @#$ test\")\n        self.assertEqual(result, {\"test\": 3})\n    \n    def test_sorted_output(self):\n        \"\"\"测试输出按字母顺序排序\"\"\"\n        result = count_words(\"zebra apple banana apple zebra\")\n        expected = {\"apple\": 2, \"banana\": 1, \"zebra\": 2}\n        self.assertEqual(result, expected)\n    \n    def test_top_parameter(self):\n        \"\"\"测试top参数功能\"\"\"\n        text = \"apple banana apple orange banana apple orange orange\"\n        # 不限制top，应该返回所有词（按词频排序）\n        result = count_words(text)\n        expected = {\"apple\": 3, \"orange\": 3, \"banana\": 2}\n        self.assertEqual(result, expected)\n        \n        # 限制top=2，应该返回前2个高频词\n        result_top2 = count_words(text, top=2)\n        expected_top2 = {\"apple\": 3, \"orange\": 3}\n        self.assertEqual(result_top2, expected_top2)\n        \n        # 限制top=1，应该返回最高频词\n        result_top1 = count_words(text, top=1)\n        expected_top1 = {\"apple\": 3}\n        self.assertEqual(result_top1, expected_top1)\n        \n        # 限制top=0，应该返回空字典\n        result_top0 = count_words(text, top=0)\n        self.assertEqual(result_top0, {})\n        \n        # 限制top大于实际词数，应该返回全部\n        result_top10 = count_words(text, top=10)\n        expected_top10 = {\"apple\": 3, \"orange\": 3, \"banana\": 2}\n        self.assertEqual(result_top10, expected_top10)\n    \n    def test_top_parameter_with_ties(self):\n        \"\"\"测试top参数处理词频相同的情况\"\"\"\n        text = \"a a b b c d\"\n        # top=3，应该返回前3个（a和b都是2次，c是1次）\n        result = count_words(text, top=3)\n        expected = {\"a\": 2, \"b\": 2, \"c\": 1}\n        self.assertEqual(result, expected)\n        \n        # top=2，应该返回前2个（a和b都是2次）\n        result = count_words(text, top=2)\n        expected = {\"a\": 2, \"b\": 2}\n        self.assertEqual(result, expected)\n\n\nif __name__ == \"__main__\":\n    unittest.main()"


def topn_script(count: int, body: dict) -> list[dict]:
    """新增 --top N 功能任务的剧本（基于真实模型产出的最终文件状态）。"""
    chunks: list[dict] = []
    if count == 1:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "我先看一下目录结构。"}}]})
        args = '{"path": "."}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": args[:6]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[6:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 2:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "看看 wordfreq.py 的现状。"}}]})
        args = '{"path": "wordfreq.py"}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": args[:8]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[8:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 3:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "再看看现有测试。"}}]})
        args = '{"path": "test_wordfreq.py"}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_3", "type": "function", "function": {"name": "read_file", "arguments": args[:8]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[8:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 4:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "现在给 wordfreq.py 增加 --top N 参数。"}}]})
        args = json.dumps({"path": "wordfreq.py", "content": TOPN_WORDFREQ}, ensure_ascii=False)
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_4", "type": "function", "function": {"name": "write_file", "arguments": args[:40]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[40:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 5:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "补充对应的单元测试。"}}]})
        args = json.dumps({"path": "test_wordfreq.py", "content": TOPN_TESTS}, ensure_ascii=False)
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_5", "type": "function", "function": {"name": "write_file", "arguments": args[:40]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[40:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    elif count == 6:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "运行测试验证。"}}]})
        args = '{"command": "python -m pytest test_wordfreq.py -v", "timeout": 120}'
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_6", "type": "function", "function": {"name": "run_command", "arguments": args[:50]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[50:]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    else:
        chunks.append({"choices": [{"index": 0, "delta": {"content": "任务完成：已为 wordfreq.py 增加 --top N 参数并补充单元测试，pytest 全部通过。"}}]})
        chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    return chunks

SCENARIOS = {"demo": demo_script, "generic": generic_script, "topn": topn_script}


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
