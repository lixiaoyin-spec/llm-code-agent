import io
import json
import tempfile
import unittest
from pathlib import Path

from coding_agent.config import Config
from coding_agent.context import MessageStore
from coding_agent.llm import AssistantTurn, LLMError, ToolCall
from coding_agent.loop import Agent
from coding_agent.tools import AutoApprover, ToolContext
from coding_agent.ui import UI


def turn(content="", tool_calls=None):
    return AssistantTurn(content=content, tool_calls=tool_calls or [])


def read_call(call_id, path):
    return ToolCall(call_id, "read_file", json.dumps({"path": path}), {"path": path})


class ScriptedClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []

    def chat(self, messages, tools=None, **kwargs):
        self.requests.append(messages)
        if not self.turns:
            return turn("（无更多脚本回复）")
        return self.turns.pop(0)


class RaisingClient:
    def __init__(self, error):
        self.error = error

    def chat(self, *args, **kwargs):
        raise self.error


class FakeUI(UI):
    def __init__(self):
        super().__init__(color=False, stream=io.StringIO())
        self.plan_answer = True

    def ask_yes_no(self, question):
        return self.plan_answer


def make_agent(workspace, client, ui=None, **cfg_kwargs):
    config = Config(api_key="test", workspace=workspace, **cfg_kwargs)
    ui = ui or FakeUI()
    store = MessageStore(
        "系统提示", context_budget=config.context_budget, keep_recent=config.keep_recent
    )
    tools = ToolContext(workspace, AutoApprover())
    return Agent(config, client, store, tools, ui), store, ui


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="loop-test-"))

    def test_simple_task(self):
        (self.tmp / "a.txt").write_text("hello world", encoding="utf-8")
        client = ScriptedClient([
            turn("先读文件", [read_call("c1", "a.txt")]),
            turn("任务完成", []),
        ])
        agent, store, ui = make_agent(self.tmp, client)
        stats = agent.run("请读取 a.txt")
        self.assertEqual(stats.stop_reason, "model_finished")
        self.assertEqual(stats.turns, 2)
        self.assertEqual(stats.tool_calls, 1)
        self.assertEqual(
            [m["role"] for m in store.messages],
            ["system", "user", "assistant", "tool", "assistant"],
        )
        self.assertIn("hello world", store.messages[3]["content"])

    def test_max_turns(self):
        calls = [read_call("c1", "a.txt"), read_call("c2", "b.txt")] * 50
        client = ScriptedClient([turn("x", [call]) for call in calls])
        agent, store, ui = make_agent(self.tmp, client, max_turns=3)
        stats = agent.run("loop")
        self.assertEqual(stats.stop_reason, "max_turns")
        self.assertEqual(stats.turns, 3)

    def test_turn_budget_resets_after_limit(self):
        client = ScriptedClient([turn("回答")])
        agent, store, ui = make_agent(self.tmp, client, max_turns=30)
        agent.stats.turns = 30
        stats = agent.run("新任务")
        self.assertEqual(stats.stop_reason, "model_finished")
        self.assertEqual(stats.turns, 1)

    def test_repetition_detection(self):
        client = ScriptedClient([turn("x", [read_call("c1", "a.txt")])] * 100)
        agent, store, ui = make_agent(self.tmp, client, max_turns=10)
        stats = agent.run("loop")
        self.assertEqual(stats.stop_reason, "repeated_calls")
        self.assertEqual(stats.turns, 3)

    def test_tool_error_feedback(self):
        client = ScriptedClient([
            turn("读", [read_call("c1", "missing.txt")]),
            turn("完成", []),
        ])
        agent, store, ui = make_agent(self.tmp, client)
        agent.run("读不存在文件")
        tool_message = [m for m in store.messages if m["role"] == "tool"][0]
        self.assertIn("错误", tool_message["content"])
        self.assertIn("路径不存在", tool_message["content"])
        self.assertEqual(agent.stats.tool_failures, 1)

    def test_parallel_reads(self):
        (self.tmp / "a.txt").write_text("AAA", encoding="utf-8")
        (self.tmp / "b.txt").write_text("BBB", encoding="utf-8")
        client = ScriptedClient([
            turn("读两个", [read_call("c1", "a.txt"), read_call("c2", "b.txt")]),
            turn("完成", []),
        ])
        agent, store, ui = make_agent(self.tmp, client)
        agent.run("并行读取")
        tool_messages = [m for m in store.messages if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_messages], ["c1", "c2"])
        self.assertIn("AAA", tool_messages[0]["content"])
        self.assertIn("BBB", tool_messages[1]["content"])

    def test_plan_mode_approve(self):
        client = ScriptedClient([turn("计划：1.读 2.改", []), turn("执行完成", [])])
        agent, store, ui = make_agent(self.tmp, client, plan_first=True)
        ui.plan_answer = True
        stats = agent.run("任务")
        self.assertEqual(stats.stop_reason, "model_finished")
        self.assertIn("计划已确认", store.messages[3]["content"])

    def test_plan_mode_reject(self):
        client = ScriptedClient([turn("计划：1.读 2.改", [])])
        agent, store, ui = make_agent(self.tmp, client, plan_first=True)
        ui.plan_answer = False
        stats = agent.run("任务")
        self.assertEqual(stats.stop_reason, "plan_rejected")
        self.assertEqual(stats.turns, 1)

    def test_turn_header_only_in_verbose(self):
        agent, store, ui = make_agent(self.tmp, ScriptedClient([turn("完成", [])]))
        agent.run("任务")
        self.assertNotIn("第 1 轮", ui.stream.getvalue())
        agent2, store2, ui2 = make_agent(
            self.tmp, ScriptedClient([turn("完成", [])]), verbose=True
        )
        agent2.run("任务")
        self.assertIn("第 1 轮", ui2.stream.getvalue())

    def test_auth_error_stops(self):
        client = RaisingClient(LLMError("auth", "invalid key"))
        agent, store, ui = make_agent(self.tmp, client)
        stats = agent.run("任务")
        self.assertEqual(stats.stop_reason, "auth_error")
        self.assertFalse(stats.finished_naturally)

    def test_unknown_tool_feedback(self):
        client = ScriptedClient([
            turn("x", [ToolCall("c9", "hack_the_planet", "{}", {})]),
            turn("完成", []),
        ])
        agent, store, ui = make_agent(self.tmp, client)
        agent.run("x")
        tool_message = [m for m in store.messages if m["role"] == "tool"][0]
        self.assertIn("未知工具", tool_message["content"])


if __name__ == "__main__":
    unittest.main()
