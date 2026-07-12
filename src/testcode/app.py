from __future__ import annotations

from pathlib import Path

from testcode.config.settings import AppSettings
from testcode.orchestrator import Orchestrator


def build_orchestrator(settings_path: str | Path | None = None, env_prefix: str = "TESTCODE_") -> Orchestrator:
    settings = AppSettings.load(settings_path, prefix=env_prefix)
    # 当通过YAML文件加载时，强制使用YAML中的值而非环境变量默认值
    if settings_path is not None:
        yaml_base = AppSettings.from_yaml(settings_path)
        if yaml_base.coze.base_url:
            settings.coze.base_url = yaml_base.coze.base_url
        if yaml_base.dify.base_url:
            settings.dify.base_url = yaml_base.dify.base_url
        if yaml_base.n8n.base_url:
            settings.n8n.base_url = yaml_base.n8n.base_url
    return Orchestrator.from_settings(settings)
