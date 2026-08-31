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
            {
                "role": "assistant",
                "content": "你好！有什么可以帮你？",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "list_files", "arguments": '{"path": "."}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "list_files", "content": "工具结果"},
            {"role": "user", "content": "再见"},
        ]
        ui.show_history(messages)
        out = stream.getvalue()
        self.assertIn("你 › 你好", out)
        self.assertIn("你好！有什么可以帮你？", out)
        self.assertIn(">> list_files", out)
        self.assertIn("[工具] list_files:", out)
        self.assertIn("工具结果", out)
        self.assertNotIn("sys", out)
        self.assertIn("你 › 再见", out)



class MarkdownRenderTests(unittest.TestCase):
    def test_passthrough_without_color(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.stream_text("# 标题\n**加粗** `代码`")
        ui.end_turn()
        out = stream.getvalue()
        self.assertEqual(out, "# 标题\n**加粗** `代码`\n")

    def test_renders_headings_bold_code_lists_fence_quote(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        md = "# 标题\n\n**加粗** 和 `代码`\n\n- 项目一\n- 项目二\n\n1. 第一\n2. 第二\n\n> 引用\n\n```python\nprint(1)\n```\n"
        ui.stream_text(md)
        ui.end_turn()
        out = stream.getvalue()
        self.assertIn("\x1b[33m标题", out)
        self.assertIn("\x1b[1m加粗", out)
        self.assertIn("\x1b[36m代码", out)
        self.assertIn("项目一", out)
        self.assertIn("第一", out)
        self.assertIn("引用", out)
        self.assertIn("┌─ python", out)
        self.assertIn("print(1)", out)
        self.assertIn("└─", out)

    def test_flushes_partial_line_on_end_turn(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        ui.stream_text("没有换行的结尾")
        ui.end_turn()
        self.assertIn("没有换行的结尾", stream.getvalue())
        self.assertTrue(stream.getvalue().endswith("\n"))

    def test_table_renders_as_box(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        md = "| 文件 | 作用 |\n|------|------|\n| index.html | 页面骨架 |\n| game.js | 核心逻辑 |\n"
        ui.stream_text(md)
        ui.end_turn()
        out = stream.getvalue()
        self.assertIn("┌", out)
        self.assertIn("├", out)
        self.assertIn("└", out)
        self.assertIn("文件", out)
        self.assertIn("index.html", out)
        self.assertIn("核心逻辑", out)
        self.assertNotIn("|------|", out)
    def test_streams_across_arbitrary_chunks(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        for ch in "# 标题\n- 项目\n":
            ui.stream_text(ch)
        ui.end_turn()
        out = stream.getvalue()
        self.assertIn("标题", out)
        self.assertIn("项目", out)
        self.assertEqual(out.count("标题"), 1)

class ReasoningAndToolRenderTests(unittest.TestCase):
    def test_reasoning_streams_text_with_live_timer(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        ui.stream_reasoning("用户想知道这是什么项目。\n我应该先查看目录结构。")
        ui.end_turn()
        out = stream.getvalue()
        self.assertIn("✻ 思考", out)
        self.assertIn("✻ 思考中", out)
        self.assertIn("用户想知道这是什么项目。", out)
        self.assertIn("我应该先查看目录结构。", out)
        self.assertRegex(out, r"✻ 思考 \d+\.\d+s")

    def test_reasoning_limit_truncates_with_ellipsis(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream, reasoning_limit=10)
        ui.color = True
        ui.stream_reasoning("一二三四五六七八九十十一\n第二行不会显示")
        ui.end_turn()
        out = stream.getvalue()
        self.assertIn("一二三四五六七八九十…", out)
        self.assertNotIn("十一", out)
        self.assertNotIn("第二行不会显示", out)
    def test_reasoning_pipe_passthrough(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.stream_reasoning("\n\n用户想知道。")
        ui.end_turn()
        self.assertEqual(stream.getvalue(), "思考: \n\n用户想知道。\n")

    def test_tool_call_and_result_styled(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        ui.tool_call("list_files", '{"path": "."}')
        ui.tool_result("list_files", True, "file 16 demo_inputs.txt", 3)
        ui.tool_result("run_command", False, "命令执行超时", 122368)
        out = stream.getvalue()
        self.assertIn("● list_files", out)
        self.assertIn('{"path": "."}', out)
        self.assertIn("⎿", out)
        self.assertIn("3ms · file 16 demo_inputs.txt", out)
        self.assertIn("2m2s", out)

    def test_tool_result_collapses_long_output(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.color = True
        long_output = "\n".join("line-" + str(i) + " " + "x" * 60 for i in range(12))
        ui.tool_result("read_file", True, long_output, 8)
        out = stream.getvalue()
        self.assertIn("line-0", out)
        self.assertIn("… +4 行", out)
        self.assertNotIn("line-11", out)
    def test_tool_output_pipe_passthrough(self):
        stream = io.StringIO()
        ui = UI(color=False, stream=stream)
        ui.tool_call("read_file", '{"path":"a"}')
        ui.tool_result("read_file", True, "内容", 5)
        out = stream.getvalue()
        self.assertEqual(out, '>> read_file({"path":"a"})\n  [OK] read_file (5ms) -> 内容\n')

if __name__ == "__main__":
    unittest.main()