"""会话保存/恢复的离线测试：往返、前缀解析、列表与文件名清洗。"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from coding_agent import session as session_mod
from coding_agent.context import MessageStore
from coding_agent.llm import AssistantTurn
from coding_agent.session import derive_title, list_sessions, load_session, new_session_path, resolve_session, save_session


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
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp / "prefix"):
            session_mod.ensure_session_dir()
            (self.tmp / "prefix" / "20260827-100000-a.jsonl").write_text(
                json.dumps({"role": "system", "content": "x"}) + "\n", encoding="utf-8"
            )
            (self.tmp / "prefix" / "20260827-110000-b.jsonl").write_text(
                json.dumps({"role": "system", "content": "y"}) + "\n", encoding="utf-8"
            )
            os.utime(self.tmp / "prefix" / "20260827-100000-a.jsonl", (1750000000, 1750000000))
            os.utime(self.tmp / "prefix" / "20260827-110000-b.jsonl", (1750000100, 1750000100))
            self.assertEqual(resolve_session("20260827-10").name, "20260827-100000-a.jsonl")
            self.assertEqual(resolve_session("20260827").name, "20260827-110000-b.jsonl")
            self.assertEqual(resolve_session("20260827-110000-b").name, "20260827-110000-b.jsonl")

    def test_resolve_session_missing(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp / "missing"):
            session_mod.ensure_session_dir()
            with self.assertRaises(FileNotFoundError):
                resolve_session("no-such-session")

    def test_list_sessions_empty(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp / "empty"):
            self.assertEqual(list_sessions(), [])

    def test_new_session_path_slug_cleanup(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp):
            path = new_session_path("任务: 修复 bug!@#")
            self.assertEqual(path.parent, self.tmp)
            self.assertTrue(path.name.endswith(".jsonl"))
            self.assertNotIn(":", path.name)
            self.assertNotIn(" ", path.name)
            self.assertNotIn("!", path.name)



    def test_derive_title_from_first_user_message(self):
        path = self.tmp / "s.jsonl"
        path.write_text(
            json.dumps({"role": "system", "content": "x"}) + "\n"
            + json.dumps({"role": "user", "content": "简历项目描述优化\n第二行"}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(derive_title(path), "简历项目描述优化")
        path.write_text(
            json.dumps({"role": "system", "content": "x"}) + "\n"
            + json.dumps({"role": "user", "content": "很" * 40}) + "\n",
            encoding="utf-8",
        )
        title = derive_title(path)
        self.assertEqual(len(title), 24)
        self.assertTrue(title.endswith("..."))

    def test_resolve_session_by_title_and_index(self):
        with mock.patch.object(session_mod, "SESSION_DIR", self.tmp / "title"):
            session_mod.ensure_session_dir()
            first = self.tmp / "title" / "20260830-100000-a.jsonl"
            second = self.tmp / "title" / "20260830-110000-b.jsonl"
            for path, text in ((first, "简历项目描述优化"), (second, "安装技能")):
                path.write_text(
                    json.dumps({"role": "system", "content": "x"}) + "\n"
                    + json.dumps({"role": "user", "content": text}) + "\n",
                    encoding="utf-8",
                )
            os.utime(first, (1750000000, 1750000000))
            os.utime(second, (1750000100, 1750000100))
            self.assertEqual(resolve_session("简历").name, first.name)
            self.assertEqual(resolve_session("2").name, first.name)
            self.assertEqual(resolve_session("1").name, second.name)

if __name__ == "__main__":
    unittest.main()
