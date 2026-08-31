# Nihue -- 编程智能体（coding-agent）

Nihue 是南京大学软件工程专业推免项目作品：个人独立设计并实现的编程智能体。它通过与 DeepSeek（OpenAI 兼容协议）交互，自主地读写文件、执行命令，完成交给它的编程任务——类似一个简化的 Claude Code / Codex。

核心原则：**不依赖任何 agent 框架 / SDK**。仅使用 `requests` 做 HTTP 通信，对话历史与上下文管理、工具定义与本地执行、模型输出解析、循环终止条件、错误处理均为自行实现。

## 特性

- 零框架：直连 OpenAI 兼容接口，SSE 流式输出逐字打印，`tool_calls` 跨 chunk 增量拼接，工具参数 JSON 容错解析（兼容 markdown 代码块包裹）
- 八个本地工具：六个基础工具（`list_files` / `read_file` / `write_file` / `replace_in_file` / `search_files` / `run_command`）+ 两个技能工具（`list_skills` / `use_skill`）
- 安全：文件路径沙箱（强制工作目录内）、命令执行人工确认（yes/no/always/skip）、危险命令防呆拦截、工具输出截断
- 上下文管理：启发式 token 估算，超预算自动把早期历史压缩为摘要（保留近期消息），保证消息序列始终合法
- 主循环：多轮自主迭代、只读工具并行执行、连续重复调用检测、轮数上限、Ctrl+C 中断、API 错误分类与指数退避重试
- 会话保存 / 恢复：历史落盘为 JSONL，`--resume` 随时续接；`/sessions` 方向键选择恢复（标题取首条用户消息），`/sessions resume <名称>` 直接切换
- 技能（skill）：渐进式披露的指令包——启动只注入技能名与简介，模型按需 `use_skill` 拉取完整步骤；内置写测试/代码审查/提交整理三个示例技能
- 计划模式：`--plan` 先输出计划、人工确认后执行
- 思考过程展示：模型的 `reasoning_content` 以灰色实时显示（`--no-reasoning` 关闭）

## 快速开始

要求：Python 3.10+，`requests` 已安装。

```bash
pip install -r requirements.txt
```

准备 DeepSeek API Key（凭据只走环境变量或未入库的配置文件）：

```powershell
# Windows PowerShell
$env:DEEPSEEK_API_KEY="你的Key"
```

```bash
# macOS / Linux
export DEEPSEEK_API_KEY=你的Key
```

也可以写入 `config.local.json`（已被 `.gitignore` 排除）：

```json
{"api_key": "你的Key", "model": "deepseek-v4-pro"}
```

运行：

```bash
# 一次性任务
python agent.py "给 wordfreq.py 增加一个 --top N 命令行参数：按词频从高到低只输出前 N 个词（默认输出全部），并补充对应的单元测试，运行测试确保全部通过" --workspace demo

# 交互模式（内置命令 /help /clear /compact /sessions /skills /stats /exit）
python agent.py
```

没有网络或 Key 时，可以用内置的模拟服务端离线演练完整流程（开发/录制演示用）：

```bash
python scripts/mock_server.py --port 8765 --scenario topn
python agent.py "给 wordfreq.py 增加一个 --top N 命令行参数：按词频从高到低只输出前 N 个词（默认输出全部），并补充对应的单元测试，运行测试确保全部通过" -w demo \
    --base-url http://127.0.0.1:8765/api --api-key mock --auto-approve
```

## 快速启动（可选）

Windows PowerShell 用户可在个人配置文件中定义 `nihue` 函数，之后直接输入 `nihue` 即可启动（任意参数透传）：

```powershell
function nihue { python "D:\你的路径\agent.py" @args }
```

用法示例：`nihue`（交互模式）、`nihue "任务描述" -w demo`、`nihue --resume <会话名>`、`nihue --list-skills`。

## 命令行参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `task` | 任务描述（留空进入交互模式） | - |
| `-w, --workspace` | 工作目录，文件操作被限制在内 | 当前目录 |
| `-m, --model` | 模型名（DeepSeek 平台可用模型为准） | `deepseek-v4-pro` |
| `--base-url` | OpenAI 兼容接口地址 | DeepSeek 官方 |
| `--api-key` | API Key（推荐用环境变量） | - |
| `--max-turns` | 最大轮数 | 60 |
| `--max-tokens` | 单次回复最大 token | 8192 |
| `--temperature` | 采样温度 | 0.2 |
| `--auto-approve` | 自动放行所有命令（仅限可信环境/录制演示） | 关 |
| `--plan` | 计划模式：先出计划、确认后执行 | 关 |
| `--no-reasoning` | 隐藏模型思考过程 | 关 |
| `--context-budget` | 触发历史压缩的 token 预算 | 24000 |
| `--resume SESSION` | 恢复会话 | - |
| `--list-sessions` | 列出已保存会话 | - |
| `--list-skills` | 列出可用技能 | - |
| `--skills-dir DIR` | 额外技能目录（可多次指定，同名覆盖内置目录） | - |
| `-v, --verbose` | 打印调试信息与每轮标题（不会打印 API Key） | 关 |
| `--no-save` | 不保存会话 | 关 |

## 工具一览

| 工具 | 作用 | 安全措施 |
| --- | --- | --- |
| `list_files` | 列目录内容 | 路径沙箱 |
| `read_file` | 带行号读取文件 | 路径沙箱、96KB/2000 行截断 |
| `write_file` | 创建/覆盖文件 | 路径沙箱 |
| `replace_in_file` | 唯一匹配替换 | 要求 old_text 恰好出现一次 |
| `search_files` | 正则搜索内容 | 跳过 .git/node_modules 等目录 |
| `list_skills` | 列出可用技能 | 只读，无副作用 |
| `use_skill` | 按需加载技能完整说明 | 只读，仅允许读取技能目录 |
| `run_command` | 执行命令 | 人工确认 + 危险命令防呆拦截 + 超时终止整个进程树 + 输出截断 |

## 架构

```
agent.py                    命令行入口：参数解析、REPL、会话保存
coding_agent/
  config.py                 配置加载（环境变量 > 本地配置 > 默认值），凭据脱敏
  prompts.py                系统提示词
  llm.py                    OpenAI 兼容客户端：SSE 流式解析、重试、错误分类
  tools.py                  工具定义与本地执行：路径沙箱、命令确认、输出截断
  context.py                对话历史、token 估算、自动压缩
  loop.py                   主循环：终止条件、只读并行、重复调用检测
  ui.py                     终端交互与人工确认器
  session.py                会话 JSONL 保存/恢复
  skills.py                 技能扫描、frontmatter 解析与按需加载
scripts/mock_server.py      离线模拟服务端（演练用，非 agent 组成部分）
demo/                       演示任务现场（wordfreq.py 与单元测试）
.nihue/skills/              内置示例技能（写测试/代码审查/提交整理）
tests/                      65 个离线单元测试
```

主循环（每轮）：

```
[消息历史] -> 模型(流式) -> 解析(content/reasoning/tool_calls)
     ^                            |
     |                   有工具调用？
     +-- 工具结果回传 <- 执行工具(只读并行/写与命令串行) <-+
                              无工具调用 -> 任务结束
```

## 设计决策（面试答辩要点）

- **为什么不用框架、连官方 SDK 都不用？** 题目要求核心逻辑自研。直接基于 `requests` 实现协议层只有几百行，流式解析、重试策略、错误分类全部可见可控，也便于面试讲清每一处行为。
- **为什么工具集是这 6 个？** 感知（list/read/search）与行动（write/replace/run）的最小完备集。`replace_in_file` 强制 old_text 唯一出现，比整文件重写更能防止模型误伤无关代码。
- **为什么只读工具并行、写与命令串行？** 只读无副作用，并行能明显降低多工具轮次延迟；写文件与命令有副作用且可能相互依赖，必须按模型给定的顺序执行，保证行为确定、便于审查。
- **为什么命令执行靠人工确认，而不是自动放行？** 静态解析 shell 语法不可靠，会带来虚假安全感；确认（yes/no/always/skip）是可靠的安全边界。防呆拦截清单只是第一道粗筛。
- **为什么不精确计算 token？** 估算只用于"何时压缩"的阈值决策，阈值留足冗余即可，精确计数需要额外 tokenizer 依赖，得不偿失。
- **为什么压缩用"摘要 + 保留近期"？** 全量丢弃会丢失长程信息，全量保留成本线性增长；摘要保住目标与关键事实，近期消息保住当前工作状态。
- **为什么有 5 种终止条件？** 正常完成、轮数上限、重复调用检测、用户中断、API 失败分别对应不同的失控模式，缺一不可。
- **为什么错误回传给模型而不是中断？** 工具错误（路径不存在、参数非法）大多是模型可自行纠正的，回传构成自我修复闭环；只有认证失败这类不可恢复错误才立即停止。
- **为什么默认温度 0.2？** agent 任务里工具参数的正确性比文本多样性重要，低温减少参数幻觉。
- **为什么技能用"按需加载"而不是全部注入提示词？** 常驻全部技能会推高每轮 token 并稀释注意力；只注入名称与简介，模型判断匹配时再 `use_skill` 拉取全文，是最简的"渐进式披露"实现。
- **为什么会话标题取第一条用户消息、恢复用方向键选择器？** 日期编号文件名不可读；标题一眼可辨，选择器一次按键即可恢复，交互与 Claude Code 一致。标题只影响展示，文件名保持稳定。

## 测试

全部测试离线可跑，不依赖网络与 API Key：

```bash
python -m unittest discover -s tests -v   # 65 个用例
```

覆盖：配置加载与凭据脱敏、SSE 流式解析（本地模拟服务端）、重试与错误分类、路径沙箱、命令确认/拦截/超时、上下文压缩、主循环终止条件、并行执行、计划模式。

## 凭据与安全

- API Key 只允许来自环境变量（`DEEPSEEK_API_KEY` 等）或 `config.local.json`（已 gitignore）；任何日志、会话文件都不会输出 Key
- 会话记录保存在 `~/.coding-agent/sessions/`，不进仓库
- 若曾误提交 Key，请立即在 DeepSeek 平台作废更换（题目规则第 4 条）
