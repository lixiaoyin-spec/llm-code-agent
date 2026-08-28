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


if __name__ == "__main__":
    unittest.main()
