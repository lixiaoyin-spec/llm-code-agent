"""可插拔技能（skill）：目录扫描、frontmatter 解析与按需加载。

设计（面试可展开讲）：
1. 渐进式披露：启动时只把「技能名 + 一句简介」注入系统提示词，
   模型判断任务匹配时才调用 use_skill 拉取完整步骤，避免所有技能
   常驻上下文带来的 token 开销与注意力稀释；
2. 技能只是指令文本：技能目录不获得任何执行特权，技能里提到的脚本
   若要运行，仍走 run_command 的人工确认与危险命令拦截，安全边界不变；
3. 查找顺序：用户主目录 ~/.nihue/skills 兜底，工作目录 .nihue/skills
   其次，--skills-dir 指定的目录最后；同名技能后者覆盖前者。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SKILL_FILE = "SKILL.md"

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)\Z", re.S)
_FIELD_RE = re.compile(r"^(name|description)\s*:\s*(.+?)\s*$")


class SkillError(Exception):
    """技能加载错误。消息会反馈给模型，帮助其自我纠正。"""


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    source: str


def _first_sentence(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            return line[:80]
    return "（无描述）"


def parse_skill_markdown(text: str, fallback_name: str) -> tuple[str, str, str]:
    """解析 SKILL.md，返回 (name, description, body)。无 frontmatter 时用目录名兜底。"""
    match = _FRONTMATTER_RE.match(text)
    if match:
        header, body = match.group(1), match.group(2)
        fields: dict[str, str] = {}
        for raw in header.splitlines():
            field = _FIELD_RE.match(raw.strip())
            if field:
                fields[field.group(1)] = field.group(2).strip()
        name = (fields.get("name") or fallback_name).strip()
        description = fields.get("description") or _first_sentence(body)
        return name, description, body.strip()
    return fallback_name, _first_sentence(text), text.strip()


def discover_skills(roots: Sequence[tuple[Path, str]]) -> list[Skill]:
    """扫描各根目录下的 <name>/SKILL.md。同名技能按 roots 顺序，后者覆盖前者。"""
    found: dict[str, Skill] = {}
    for root, source in roots:
        if not root.is_dir():
            continue
        for skill_file in sorted(root.glob(f"*/{SKILL_FILE}")):
            try:
                text = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            fallback = skill_file.parent.name
            name, description, body = parse_skill_markdown(text, fallback)
            found[name] = Skill(
                name=name, description=description, body=body, path=skill_file, source=source
            )
    return sorted(found.values(), key=lambda skill: skill.name.lower())


class SkillRegistry:
    """技能的发现与按需加载。"""

    def __init__(self, roots: Sequence[tuple[Path, str]] | None = None):
        self.roots: list[tuple[Path, str]] = list(roots or [])
        self.skills: list[Skill] = discover_skills(self.roots)
        self._by_name = {skill.name: skill for skill in self.skills}

    def get(self, name: str) -> Skill | None:
        return self._by_name.get(name.strip())

    def list_text(self) -> str:
        if not self.skills:
            return "（暂无可用技能）"
        lines = [f"{skill.name} - {skill.description}（来源：{skill.source}）" for skill in self.skills]
        return "\n".join(lines)

    def load_text(self, name: str) -> str:
        skill = self.get(name)
        if skill is None:
            available = ", ".join(sorted(self._by_name)) or "无"
            raise SkillError(f"未知技能 {name!r}，可用技能：{available}")
        return f"# 技能：{skill.name}\n来源：{skill.path}\n\n{skill.body}"