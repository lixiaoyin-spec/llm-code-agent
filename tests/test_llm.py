import http.server
import json
import socket
import threading
import unittest

from coding_agent.config import Config
from coding_agent.llm import LLMClient, LLMError, parse_arguments

CHUNKS = [
    {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "我来"}}]},
    {"choices": [{"index": 0, "delta": {"content": "读取文件"}}]},
    {"choices": [{"index": 0, "delta": {"reasoning_content": "先看"}}]},
    {"choices": [{"index": 0, "delta": {"reasoning_content": "一下"}}]},
    {
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "call_1", "type": "function",
                         "function": {"name": "read_", "arguments": ""}}
                    ]
                },
            }
        ]
    },
    {
        "choices": [
            {"index": 0, "delta": {"tool_calls": [
                {"index": 0, "function": {"name": "file", "arguments": "{\"path\":"}}]}}
        ]
    },
    {
        "choices": [
            {"index": 0, "delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "\"a.txt\"}"}}]}}
        ]
    },
    {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 9}},
]


class MockHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        scenario = self.server.scenario
        if scenario.get("auth_error"):
            self._reply_json(401, {"error": {"message": "invalid key"}})
            return
        if scenario.get("bad_request"):
            self._reply_json(400, {"error": {"message": "bad payload"}})
            return
        if scenario.get("fail_first") and self.server.count == 0:
            self.server.count += 1
            self._reply_json(500, {"error": {"message": "boom"}})
            return
        self.server.count += 1
        lines = ["data: " + json.dumps(chunk, ensure_ascii=False) for chunk in scenario.get("chunks", [])]
        lines.append("data: [DONE]")
        body = ("\n\n".join(lines) + "\n\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reply_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_server(scenario):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    server.scenario = scenario
    server.count = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def make_config(port, **kwargs):
    values = dict(
        api_key="test-key",
        base_url=f"http://127.0.0.1:{port}/api",
        max_retries=2,
        retry_backoff=0.01,
        connect_timeout=3,
        request_timeout=10,
        max_tokens=64,
    )
    values.update(kwargs)
    return Config(**values)


class LLMClientTest(unittest.TestCase):
    def setUp(self):
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def start(self, scenario):
        server = start_server(scenario)
        self.servers.append(server)
        return server

    def test_stream_parsing(self):
        server = self.start({"chunks": CHUNKS})
        client = LLMClient(make_config(server.server_port))
        texts, reasons = [], []
        turn = client.chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function"}],
            on_text=texts.append,
            on_reasoning=reasons.append,
        )
        self.assertEqual(turn.content, "我来读取文件")
        self.assertEqual(turn.reasoning, "先看一下")
        self.assertEqual(turn.finish_reason, "tool_calls")
        self.assertEqual(len(turn.tool_calls), 1)
        self.assertEqual(turn.tool_calls[0].name, "read_file")
        self.assertEqual(turn.tool_calls[0].arguments, {"path": "a.txt"})
        self.assertEqual(turn.tool_calls[0].parse_error, "")
        self.assertEqual(turn.usage.prompt_tokens, 12)
        self.assertEqual("".join(texts), "我来读取文件")

    def test_retry_then_success(self):
        server = self.start({"fail_first": True, "chunks": [
            {"choices": [{"delta": {"content": "ok"}}]}]})
        client = LLMClient(make_config(server.server_port))
        turn = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(turn.content, "ok")
        self.assertEqual(server.count, 2)

    def test_auth_error(self):
        server = self.start({"auth_error": True})
        client = LLMClient(make_config(server.server_port))
        with self.assertRaises(LLMError) as caught:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "auth")

    def test_bad_request(self):
        server = self.start({"bad_request": True})
        client = LLMClient(make_config(server.server_port))
        with self.assertRaises(LLMError) as caught:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "bad_request")

    def test_network_error(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        client = LLMClient(make_config(port, max_retries=1))
        with self.assertRaises(LLMError) as caught:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "network")

    def test_empty_stream(self):
        server = self.start({"chunks": []})
        client = LLMClient(make_config(server.server_port))
        with self.assertRaises(LLMError) as caught:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "bad_stream")

    def test_parse_arguments_markdown(self):
        value, error = parse_arguments("```json\n{\"a\": 1}\n```")
        self.assertEqual(value, {"a": 1})
        self.assertEqual(error, "")
        value, error = parse_arguments("not json")
        self.assertIsNone(value)
        self.assertIn("不是合法 JSON", error)


if __name__ == "__main__":
    unittest.main()
