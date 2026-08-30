---
name: git-commit
description: 按规范整理改动并生成清晰的提交：先看 diff，再分组提交，写规范 message。
---
# 提交整理技能

## 步骤
1. git status 与 git diff 浏览全部改动；
2. 将相关改动归为逻辑分组，逐个 git add 对应文件；
3. message 用"类型: 简述"格式（feat/fix/docs/test/refactor/chore），正文说明动机与影响；
4. 提交前用 git diff --cached 自查，确认没有混入凭据或无关文件。