"""UI 渲染的离线测试：logo 与非交互输入栏回退。"""

from __future__ import annotations

import io
import unittest
from unittest import mock

from coding_agent.ui import LOGO, UI


class UiTests(unittest.TestCase):
    def test_logo_renders_name(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.logo()
        out = stream.getvalue()
        self.assertIn("Nihue", out)
        self.assertIn("_   _", out)
        self.assertGreaterEqual(out.count("\n"), 6)

    def test_logo_constant_rows(self):
        self.assertEqual(len(LOGO.strip("\n").splitlines()), 5)

    def test_task_input_non_interactive(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        with mock.patch("builtins.input", return_value="hello"):
            text = ui.task_input()
        self.assertEqual(text, "hello")
        self.assertIn("输入任务", stream.getvalue())


    def test_pick_session_numbered_fallback(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        with mock.patch("builtins.input", return_value="2"):
            self.assertEqual(ui.pick_session([("甲", "a"), ("乙", "b")]), 1)
        with mock.patch("builtins.input", return_value=""):
            self.assertIsNone(ui.pick_session([("甲", "a")]))
        self.assertIsNone(ui.pick_session([]))
        self.assertIn("1. 甲", stream.getvalue())


    def test_show_history_renders_turns(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你？", "tool_calls": []},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "工具结果"},
            {"role": "user", "content": "再见"},
        ]
        ui.show_history(messages)
        out = stream.getvalue()
        self.assertIn("你 › 你好", out)
        self.assertIn("你好！有什么可以帮你？", out)
        self.assertIn("调用工具 1 次", out)
        self.assertNotIn("工具结果", out)
        self.assertNotIn("sys", out)
        self.assertIn("你 › 再见", out)


if __name__ == "__main__":
    unittest.main()
