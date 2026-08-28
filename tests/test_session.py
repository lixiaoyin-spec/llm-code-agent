"""会话保存/恢复的离线测试：往返、前缀解析、列表与文件名清洗。"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from coding_agent import session as session_mod
from coding_agent.context import MessageStore
from coding_agent.llm import AssistantTurn
from coding_agent.session import list_sessions, load_session, new_session_path, resolve_session, save_session


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="nihue-session-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_roundtrip(self):
        store = MessageStore("system-line")
        store.add_user("第一条消息")
        store.add_assistant(AssistantTurn(content="第一条回复"))
        store.add_user("第二条消息")
        store.add_tool_result("call-1", "read_file", "文件内容")
        path = self.tmp / "s.jsonl"
        save_session(path, store)
        loaded = load_session(path, MessageStore("system-line"))
        self.assertEqual(len(loaded.messages), len(store.messages))
        self.assertEqual(loaded.messages[0]["role"], "system")
        self.assertEqual(loaded.messages[1]["content"], "第一条消息")
        self.assertEqual(loaded.messages[2]["content"], "第一条回复")
        self.assertEqual(loaded.messages[3]["content"], "第二条消息")
        self.assertEqual(loaded.messages[4]["content"], "文件内容")

    def test_resolve_session_by_prefix(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp):
            session_mod.ensure_session_dir()
            (self.tmp / "20260827-100000-a.jsonl").write_text(
                json.dumps({"role": "system", "content": "x"}) + "\n", encoding="utf-8"
            )
            (self.tmp / "20260827-110000-b.jsonl").write_text(
                json.dumps({"role": "system", "content": "y"}) + "\n", encoding="utf-8"
            )
            self.assertEqual(resolve_session("20260827-10").name, "20260827-100000-a.jsonl")
            self.assertEqual(resolve_session("20260827").name, "20260827-110000-b.jsonl")
            self.assertEqual(resolve_session("20260827-110000-b").name, "20260827-110000-b.jsonl")

    def test_resolve_session_missing(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp):
            session_mod.ensure_session_dir()
            with self.assertRaises(FileNotFoundError):
                resolve_session("no-such-session")

    def test_list_sessions_empty(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp):
            self.assertEqual(list_sessions(), ["（暂无已保存会话）"])

    def test_new_session_path_slug_cleanup(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp):
            path = new_session_path("任务: 修复 bug!@#")
            self.assertEqual(path.parent, self.tmp)
            self.assertTrue(path.name.endswith(".jsonl"))
            self.assertNotIn(":", path.name)
            self.assertNotIn(" ", path.name)
            self.assertNotIn("!", path.name)


if __name__ == "__main__":
    unittest.main()
