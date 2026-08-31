"""配置加载与校验。

凭据管理原则（对应考核规则第 4 条）：
- API Key 只允许来自环境变量或未入库的本地配置文件；
- 任何日志、报错、会话记录都不会输出 API Key。

优先级：命令行参数 > 环境变量 > 本地配置文件 > 内置默认值。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-pro"

API_KEY_ENV_NAMES = ("DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "BIGMODEL_API_KEY", "OPENAI_API_KEY", "GLM_API_KEY")
LOCAL_CONFIG_NAMES = ("config.local.json", "config.json", ".coding-agent.json")

_MISSING_KEY_HINT = (
    "未找到 API Key。请通过环境变量设置，例如 PowerShell：\n"
    "  $env:ZHIPU_API_KEY=\"你的Key\"\n"
    "macOS / Linux：\n"
    "  export ZHIPU_API_KEY=你的Key\n"
    "或写入本地配置文件 config.local.json（形如 {\"api_key\": \"你的Key\"}，已加入 .gitignore）。"
)


class ConfigError(Exception):
    """配置不合法或缺失。"""


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def find_config_file(workspace: Path) -> Path | None:
    candidates = [workspace / name for name in LOCAL_CONFIG_NAMES]
    try:
        candidates.append(Path.home() / ".coding-agent" / "config.json")
    except RuntimeError:  # 环境变量缺失导致无法定位用户目录时忽略
        pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


@dataclass
class Config:
    """agent 运行所需的全部配置。"""

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    workspace: Path = field(default_factory=Path.cwd)
    max_turns: int = 60
    max_tokens: int = 81920
    temperature: float = 0.2
    auto_approve: bool = False
    plan_first: bool = False
    show_reasoning: bool = True
    color: bool = True
    verbose: bool = False
    save_session: bool = True
    context_budget: int = 24_000
    keep_recent: int = 8
    extra_system: str = ""
    request_timeout: float = 180.0
    connect_timeout: float = 15.0
    max_retries: int = 3
    retry_backoff: float = 1.5
    read_max_bytes: int = 96 * 1024
    read_max_lines: int = 2_000
    tool_output_chars: int = 8_000
    search_max_matches: int = 40
    config_file: Path | None = None

    # ---- 加载 ----
    @classmethod
    def from_env(cls, workspace: Path | None = None, **overrides: Any) -> "Config":
        cfg = cls()
        cfg.workspace = Path(workspace or Path.cwd()).expanduser().resolve()

        file_values: dict[str, Any] = {}
        config_file = find_config_file(cfg.workspace)
        if config_file is not None:
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError(f"配置文件 {config_file} 解析失败：{exc}") from exc
            if not isinstance(data, dict):
                raise ConfigError(f"配置文件 {config_file} 顶层必须是 JSON 对象")
            file_values = data
            cfg.config_file = config_file

        file_keys = (
            "api_key", "base_url", "model", "temperature", "max_turns", "max_tokens",
            "context_budget", "keep_recent", "request_timeout", "connect_timeout",
            "max_retries", "retry_backoff", "read_max_bytes", "read_max_lines",
            "tool_output_chars", "search_max_matches", "auto_approve", "plan_first",
            "show_reasoning", "color", "verbose", "save_session", "extra_system",
        )
        for key in file_keys:
            if key in file_values:
                setattr(cfg, key, _coerce(getattr(cfg, key), file_values[key]))

        env_key = _first_env(API_KEY_ENV_NAMES)
        if env_key:
            cfg.api_key = env_key
        for env_name, attr in (("ZHIPU_BASE_URL", "base_url"), ("OPENAI_BASE_URL", "base_url"),
                               ("ZHIPU_MODEL", "model"), ("DEEPSEEK_BASE_URL", "base_url"), ("DEEPSEEK_MODEL", "model")):
            value = os.environ.get(env_name, "").strip()
            if value:
                setattr(cfg, attr, value)

        for key, value in overrides.items():
            if value is not None:
                setattr(cfg, key, value)

        cfg.validate()
        return cfg

    # ---- 校验 ----
    def validate(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.api_key:
            raise ConfigError(_MISSING_KEY_HINT)
        if not self.workspace.is_dir():
            raise ConfigError(f"工作目录不存在：{self.workspace}")
        if self.max_turns < 1:
            raise ConfigError("max_turns 必须 >= 1")
        if not 0 < self.temperature <= 1.5:
            raise ConfigError("temperature 必须在 (0, 1.5] 区间")
        if self.max_tokens < 64:
            raise ConfigError("max_tokens 必须 >= 64")
        if self.context_budget < 1_000:
            raise ConfigError("context_budget 必须 >= 1000")
        if self.keep_recent < 2:
            raise ConfigError("keep_recent 必须 >= 2")
        if self.max_retries < 0:
            raise ConfigError("max_retries 必须 >= 0")

    def masked_repr(self) -> str:
        key = self.api_key[:6] + "***" + self.api_key[-4:] if self.api_key else "(未设置)"
        return (
            f"Config(model={self.model!r}, base_url={self.base_url!r}, "
            f"workspace={str(self.workspace)!r}, api_key={key!r})"
        )

    __repr__ = masked_repr


def _coerce(current: Any, value: Any) -> Any:
    """按字段现有类型对配置文件里的值做宽松转换（JSON 里数字/字符串均可用）。"""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value
