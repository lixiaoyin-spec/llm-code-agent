Nihue——编程智能体（软件工程专业推免项目）

一、仓库地址
https://github.com/lixiaoyin-spec/llm-code-agent

二、如何运行
1. 安装依赖：pip install -r requirements.txt（仅需 requests，Python 3.10+）
2. 准备 DeepSeek API Key（OpenAI 兼容）：
   PowerShell：$env:DEEPSEEK_API_KEY="你的Key"
   macOS/Linux：export DEEPSEEK_API_KEY=你的Key
   也可写入 config.local.json（已被 .gitignore 排除，不会入库）
3. 运行：
   python agent.py "你的编程任务" --workspace demo
   python agent.py            # 交互模式，内置 /help /clear /sessions /skills /stats /exit
   其它参数见 --help；无 Key 时配合 scripts/mock_server.py 可离线演练。
4. 快捷启动（Windows 可选，配置一次即可）：
   在 PowerShell 执行 notepad $PROFILE，在文件末尾加入一行（路径改成你的仓库目录）：
     function nihue { python "D:\你的路径\llm-code-agent\agent.py" @args }
   保存后新开任意 PowerShell（任意目录），直接输入 nihue 即可启动；
   参数用法与 python agent.py 一致，例如：nihue --workspace demo

三、特色功能
- 零 agent 框架：仅用 requests 直连 OpenAI 兼容接口，SSE 流式解析、工具调用增量拼接、参数容错；
- 八个本地工具：六个基础工具加 list_skills/use_skill 两个技能工具；
- 安全：路径沙箱限制在工作目录内；命令执行前人工确认（yes/no/always/skip）加危险命令防呆拦截；输出截断；
- 上下文管理：启发式 token 估算，超预算自动把早期历史压缩为摘要并保留近期消息；会话保存与 --resume 恢复；
- 技能（skill）：只注入名称与简介，use_skill 按需加载完整步骤；内置三个示例；
- 主循环：多轮自主迭代、只读工具并行执行、连续重复调用检测、轮数上限、Ctrl+C 中断、API 错误分类重试；
- 计划模式（--plan）：先出计划经确认再执行；思考过程简略展示（--reasoning-limit N 设字数上限，0 不限制，--no-reasoning 关闭）。

四、其它说明
- 模型默认 deepseek-v4-pro，可用 --model 更换；--base-url 可切换任何 OpenAI 兼容服务；
- 对话历史管理、工具定义与本地执行、输出解析、循环终止、错误处理等核心逻辑全部自行实现，未使用任何 agent 框架/SDK；
- 测试：python -m unittest discover -s tests（83 个用例，离线可跑）。