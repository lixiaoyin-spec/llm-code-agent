# 任务：从零实现命令行 TODO 应用

在本目录（demo/todo_cli）从零实现一个命令行 TODO 管理器 `todo.py`，并补充单元测试。

## 功能规格

1. 子命令（用 argparse 实现）：
   - `python todo.py add <内容>`：添加一条任务，自动分配递增编号，并输出确认信息（包含编号与内容）。
   - `python todo.py list`：列出所有未完成任务，每行格式 `#<编号> <内容>`；没有任务时输出“暂无任务”。
   - `python todo.py done <编号>`：将对应任务标记为完成并输出确认；编号不存在时输出友好报错，并以非零退出码退出。
2. 持久化：任务保存在本目录 `todo.json`（文件不存在时自动创建），格式自定；重启程序后数据不丢失。
3. 只使用 Python 标准库，不安装第三方依赖。

## 验收标准

- 单元测试：用 unittest 覆盖 add、list、done、持久化读写、done 不存在编号时的报错与退出码，`python -m unittest` 全部通过。
- 手动冒烟：依次执行 add、list、done，输出符合上述规格。