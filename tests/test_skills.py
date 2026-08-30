"""技能系统的离线测试：frontmatter 解析、目录发现、覆盖顺序、注册表与两个技能工具。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from coding_agent.skills import SkillError, SkillRegistry, discover_skills, parse_skill_markdown
from coding_agent.tools import AutoApprover, ToolContext, run_tool


class SkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skills-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_skill(self, root, name, text):
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skill_dir / "SKILL.md"

    def test_parse_with_frontmatter(self):
        text = "---\nname: review\ndescription: 审查改动\n---\n# 步骤\n先看 diff。"
        name, description, body = parse_skill_markdown(text, "fallback")
        self.assertEqual(name, "review")
        self.assertEqual(description, "审查改动")
        self.assertEqual(body, "# 步骤\n先看 diff。")

    def test_parse_without_frontmatter(self):
        text = "# 标题\n第一句说明。\n更多内容"
        name, description, body = parse_skill_markdown(text, "dir-name")
        self.assertEqual(name, "dir-name")
        self.assertEqual(description, "第一句说明。")
        self.assertEqual(body, text.strip())

    def test_discover_and_override_order(self):
        user_root = self.tmp / "user"
        project_root = self.tmp / "project"
        self.make_skill(user_root, "demo", "---\nname: demo\ndescription: 全局版\n---\nuser body")
        self.make_skill(project_root, "demo", "---\nname: demo\ndescription: 项目版\n---\nproject body")
        self.make_skill(project_root, "other", "---\nname: other\ndescription: 其它\n---\nbody")
        skills = discover_skills([(user_root, "user"), (project_root, "project")])
        self.assertEqual(sorted(s.name for s in skills), ["demo", "other"])
        demo = next(s for s in skills if s.name == "demo")
        self.assertEqual(demo.body, "project body")
        self.assertEqual(demo.source, "project")

    def test_registry_load_and_errors(self):
        root = self.tmp / "root"
        self.make_skill(root, "demo", "---\nname: demo\ndescription: 演示技能\n---\n步骤一。")
        registry = SkillRegistry([(root, "project")])
        self.assertIn("demo - 演示技能", registry.list_text())
        self.assertIn("步骤一。", registry.load_text("demo"))
        with self.assertRaises(SkillError):
            registry.load_text("missing")

    def test_empty_registry(self):
        registry = SkillRegistry([(self.tmp / "none", "project")])
        self.assertIn("暂无", registry.list_text())

    def test_tools_with_registry(self):
        root = self.tmp / "root"
        self.make_skill(root, "demo", "---\nname: demo\ndescription: 演示技能\n---\n第一步。\n第二步。")
        registry = SkillRegistry([(root, "project")])
        ctx = ToolContext(self.tmp, AutoApprover(), skills=registry)
        listed = run_tool("list_skills", {}, ctx)
        self.assertTrue(listed.ok, listed.output)
        self.assertIn("demo - 演示技能", listed.output)
        used = run_tool("use_skill", {"name": "demo"}, ctx)
        self.assertTrue(used.ok, used.output)
        self.assertIn("第一步。", used.output)
        self.assertIn("第二步。", used.output)
        missing = run_tool("use_skill", {"name": "nope"}, ctx)
        self.assertFalse(missing.ok)
        self.assertIn("未知技能", missing.output)

    def test_tools_without_registry(self):
        ctx = ToolContext(self.tmp, AutoApprover())
        listed = run_tool("list_skills", {}, ctx)
        self.assertTrue(listed.ok)
        self.assertIn("未启用", listed.output)
        used = run_tool("use_skill", {"name": "x"}, ctx)
        self.assertFalse(used.ok)
        self.assertIn("未启用", used.output)

    def test_system_prompt_includes_skills(self):
        from coding_agent.prompts import build_system_prompt
        text = build_system_prompt(self.tmp, skills_text="demo - 演示技能")
        self.assertIn("可用技能", text)
        self.assertIn("demo - 演示技能", text)
        self.assertIn("use_skill", text)
        plain = build_system_prompt(self.tmp)
        self.assertNotIn("可用技能", plain)


if __name__ == "__main__":
    unittest.main()
