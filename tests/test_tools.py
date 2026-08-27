import sys
import tempfile
import unittest
from pathlib import Path

from coding_agent.tools import AutoApprover, ToolContext, run_tool


class DenyApprover:
    def approve(self, command):
        return "no"


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tools-test-"))
        self.ctx = ToolContext(self.tmp, AutoApprover())

    def call(self, name, args):
        return run_tool(name, args, self.ctx)

    def make(self, name, content=""):
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_write_and_read_roundtrip(self):
        result = self.call("write_file", {"path": "a/b.txt", "content": "line1\nline2\nline3"})
        self.assertTrue(result.ok, result.output)
        result = self.call("read_file", {"path": "a/b.txt"})
        self.assertTrue(result.ok)
        self.assertIn("1| line1", result.output)
        self.assertIn("3| line3", result.output)
        result = self.call("read_file", {"path": "a/b.txt", "start_line": 2, "end_line": 3})
        self.assertIn("2| line2", result.output)
        self.assertNotIn("1| line1", result.output)

    def test_read_missing(self):
        result = self.call("read_file", {"path": "nope.txt"})
        self.assertFalse(result.ok)
        self.assertIn("错误", result.output)

    def test_path_escape_blocked(self):
        result = self.call("write_file", {"path": "../evil.txt", "content": "x"})
        self.assertFalse(result.ok)
        self.assertIn("超出工作目录", result.output)
        outside = str(self.tmp.parent / "evil.txt")
        result = self.call("write_file", {"path": outside, "content": "x"})
        self.assertFalse(result.ok)
        self.assertIn("超出工作目录", result.output)

    def test_replace_unique(self):
        self.make("f.txt", "hello world\nhello again\n")
        result = self.call("replace_in_file", {"path": "f.txt", "old_text": "hello world", "new_text": "bye"})
        self.assertTrue(result.ok, result.output)
        self.assertIn("bye", (self.tmp / "f.txt").read_text(encoding="utf-8"))

    def test_replace_not_found(self):
        self.make("f.txt", "hello world\n")
        result = self.call("replace_in_file", {"path": "f.txt", "old_text": "zzz", "new_text": "x"})
        self.assertFalse(result.ok)
        self.assertIn("0 次", result.output)

    def test_replace_ambiguous(self):
        self.make("f.txt", "hello\nhello\n")
        result = self.call("replace_in_file", {"path": "f.txt", "old_text": "hello", "new_text": "x"})
        self.assertFalse(result.ok)
        self.assertIn("2 次", result.output)

    def test_list_files(self):
        self.make("b.txt")
        self.make("a.txt")
        (self.tmp / "sub").mkdir()
        result = self.call("list_files", {"path": "."})
        self.assertTrue(result.ok)
        self.assertIn("a.txt", result.output)
        self.assertIn("b.txt", result.output)
        self.assertIn("sub", result.output)

    def test_search_files(self):
        self.make("x.py", "needle here\nother line\n")
        self.make("y.py", "NeeDle again\n")
        result = self.call("search_files", {"pattern": "needle"})
        self.assertIn("x.py:1", result.output)
        self.assertIn("y.py:1", result.output)
        result = self.call("search_files", {"pattern": "needle", "case_sensitive": True})
        self.assertIn("x.py:1", result.output)
        self.assertNotIn("y.py", result.output)

    def test_search_invalid_regex(self):
        result = self.call("search_files", {"pattern": "("})
        self.assertFalse(result.ok)
        self.assertIn("正则", result.output)

    def test_run_command_echo(self):
        result = self.call("run_command", {"command": "echo hello-agent"})
        self.assertTrue(result.ok, result.output)
        self.assertIn("hello-agent", result.output)
        self.assertIn("退出码：0", result.output)

    def test_run_command_nonzero_exit(self):
        command = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
        result = self.call("run_command", {"command": command})
        self.assertFalse(result.ok)
        self.assertIn("退出码：3", result.output)

    def test_run_command_timeout(self):
        command = f'"{sys.executable}" -c "import time; time.sleep(10)"'
        result = self.call("run_command", {"command": command, "timeout": 1})
        self.assertFalse(result.ok)
        self.assertIn("超时", result.output)

    def test_run_command_denied(self):
        ctx = ToolContext(self.tmp, DenyApprover())
        result = run_tool("run_command", {"command": "echo hi"}, ctx)
        self.assertFalse(result.ok)
        self.assertIn("拒绝", result.output)

    def test_run_command_blocklist(self):
        result = self.call("run_command", {"command": "rm -rf /"})
        self.assertFalse(result.ok)
        self.assertIn("拦截", result.output)

    def test_unknown_tool(self):
        result = self.call("hack_the_planet", {})
        self.assertFalse(result.ok)
        self.assertIn("未知工具", result.output)

    def test_write_overwrite(self):
        path = self.make("w.txt", "old")
        result = self.call("write_file", {"path": "w.txt", "content": "new"})
        self.assertTrue(result.ok)
        self.assertIn("已更新", result.output)
        self.assertEqual(path.read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
