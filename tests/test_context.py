import unittest

from coding_agent.context import MessageStore, estimate_tokens
from coding_agent.llm import AssistantTurn, LLMError, ToolCall


class FakeClient:
    def __init__(self, reply="这是摘要内容", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return AssistantTurn(content=self.reply)


class ContextTest(unittest.TestCase):
    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("中文测试"), 4)
        self.assertEqual(estimate_tokens("hello world"), 4)  # 11 字符 -> (11+2)//3

    def test_message_shapes(self):
        store = MessageStore("sys")
        store.add_user("任务")
        turn = AssistantTurn(
            content="回复",
            tool_calls=[ToolCall("c1", "read_file", '{"path":"a"}', {"path": "a"})],
        )
        store.add_assistant(turn)
        store.add_tool_result("c1", "read_file", "内容")
        messages = store.api_messages()
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "tool"])
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(messages[3]["tool_call_id"], "c1")

    def test_compaction(self):
        store = MessageStore("sys", context_budget=20, keep_recent=2)
        client = FakeClient("摘要：改了 a.py")
        for i in range(5):
            store.add_user(f"问题{i}")
            store.add_assistant(AssistantTurn(content=f"回答{i}"))
        self.assertTrue(store.needs_compaction())
        self.assertTrue(store.compact(client))
        self.assertIn("摘要", store.messages[1]["content"])
        self.assertEqual(store.messages[-2]["content"], "问题4")
        self.assertEqual(store.messages[-1]["content"], "回答4")
        self.assertEqual(store.compaction_count, 1)

    def test_compaction_drops_leading_tool_message(self):
        store = MessageStore("sys", context_budget=20, keep_recent=2)
        client = FakeClient("摘要")
        store.add_user("u1")
        store.add_assistant(
            AssistantTurn(content="a1", tool_calls=[ToolCall("c1", "read_file", "{}", {})])
        )
        store.add_tool_result("c1", "read_file", "r1")
        store.add_user("u2")
        store.add_assistant(
            AssistantTurn(content="a2", tool_calls=[ToolCall("c2", "read_file", "{}", {})])
        )
        store.add_tool_result("c2", "read_file", "r2")
        store.add_user("u3")
        self.assertTrue(store.compact(client))
        self.assertEqual([m["role"] for m in store.messages], ["system", "user", "user"])
        self.assertEqual(store.messages[-1]["content"], "u3")
        self.assertIn("摘要", store.messages[1]["content"])

    def test_compaction_failure_keeps_history(self):
        store = MessageStore("sys", context_budget=20, keep_recent=2)
        client = FakeClient(error=LLMError("server", "busy"))
        for i in range(3):
            store.add_user(f"问题{i}")
            store.add_assistant(AssistantTurn(content=f"回答{i}"))
        before = len(store.messages)
        self.assertFalse(store.compact(client))
        self.assertEqual(len(store.messages), before)

    def test_no_compaction_when_small(self):
        store = MessageStore("sys", context_budget=100_000)
        store.add_user("hi")
        self.assertFalse(store.needs_compaction())

    def test_roundtrip(self):
        store = MessageStore("sys")
        store.add_user("任务")
        store.add_assistant(AssistantTurn(content="好"))
        records = store.to_records()
        restored = MessageStore.from_records("sys", records)
        self.assertEqual(restored.api_messages(), store.api_messages())


if __name__ == "__main__":
    unittest.main()
