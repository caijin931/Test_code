Testcode 项目说明

Testcode 是一个以 Python 为核心的编排脚手架，用于协调 Dify、Coze 和 n8n 之间的测试自动化工作。

项目概述

这个项目为你提供了：
一个统一的 Python 控制平面，用于测试生成与执行；
针对 Dify、Coze 和 n8n 的适配器；
面向测试的编排器，可生成测试用例、用外部数据丰富用例内容，并触发自动化流程；
一个命令行工具，轻松跑通端到端流程；
缓存、配置管理、Docker 打包以及持续集成支持。

安装指南

本地开发：
首先创建并激活 Python 3.11 以上版本的虚拟环境，然后运行以下命令安装项目及其开发依赖：
pip install -e .[dev]
如果未安装 PyYAML，应用会使用内置的回退解析器读取示例配置文件，但我们强烈建议正常安装所有依赖，以免踩坑。

Docker 方式：
构建镜像：
docker build -t testcode:latest .
运行容器，并将配置文件挂载进去，例如：
docker run --rm -e TESTCODE_COZE_ACCESS_TOKEN=你的token -e TESTCODE_DIFY_API_KEY=你的key -v ${PWD}/config:/app/config testcode:latest health --settings config/settings.example.yaml

Docker Compose 方式：
复制示例环境变量文件并根据本地环境调整：
cp .env.example .env
一键启动应用、Redis 和可选的 n8n 服务：
docker compose up --build
Compose 栈会暴露以下服务：app 是 Testcode CLI 和运行时容器；redis 是可选的缓存后端（用于 Dify 缓存）；n8n 是本地工作流引擎，通过 Webhook 触发自动化任务。

配置说明

请以 config/settings.example.yaml 为蓝本，配置本地或容器化环境。

核心配置项包括：
coze.access_token、coze.base_url、coze.timeout_seconds；
dify.api_key、dify.base_url、dify.timeout_seconds；
n8n.base_url、n8n.timeout_seconds。

缓存相关配置包括：
dify.cache_enabled、dify.cache_directory、dify.cache_ttl_seconds、dify.cache_backend、dify.cache_redis_url、dify.cache_redis_prefix。

环境变量支持用变量覆盖配置，默认前缀为 TESTCODE_，具体变量列表请参考原文档。

快速上手

首先准备配置文件（例如 config/settings.example.yaml），然后导出密钥或配置好环境变量。
运行健康检查看看一切是否就绪：
python -m testcode health --settings config/settings.example.yaml
执行完整的测试流程：
python -m testcode run-test-flow --settings config/settings.example.yaml --requirement "测试登录功能" --n8n-webhook-url https://example.com/webhook --output artifacts/report.json
查看缓存后端状态：
python -m testcode cache-health --settings config/settings.example.yaml

CLI 命令一览

health 输出编排器的健康状态摘要；
cache-health 查看当前 Dify 缓存后端的情况；
run 演示 Provider 链式调用；
run-test-flow 执行完整的测试生成加自动化流程。

架构设计

工作流程是这样的：
TestRequirement 捕获用户的测试需求；
TestOrchestrator 生成测试用例并补充外部数据；
WorkflowOrchestrator 与各 Provider 客户端协作，驱动下游工作流执行；
N8nClient 触发自动化工作流，并可轮询等待执行完成；
最终报告以 JSON 格式输出，归档在 artifacts 目录下。
若想搭建一个轻量本地 n8n 环境，可参考 docs/n8n-local-webhook.md。

各 Provider 职责划分：
Dify 负责生成测试用例和总结报告；
Coze 利用外部数据或插件输出对测试用例进行增强；
n8n 执行自动化工作流并收集执行结果。

测试

运行单元测试：pytest
运行集成测试：pytest -m integration
运行测试并生成覆盖率报告：pytest --cov=testcode --cov-report=term-missing --cov-report=html

项目结构

src 目录存放应用核心代码、适配器、编排逻辑和共享工具；
config 目录存放环境、Provider 和工作流配置文件；
tests 目录存放单元测试和集成测试；
docs 目录存放架构文档、图表和实现参考；
scripts 目录存放自动化脚本和开发辅助脚本；
artifacts 目录存放生成的输出、导出文件和临时交付物。

贡献指南请阅读 CONTRIBUTING.md；发布流程请参考 RELEASE.md 和 docs/release-checklist.md。发布前务必过一遍检查清单。

一些贴心提示：
Redis 缓存是可选的，如果 Redis 不可用，缓存注册中心会自动回退到文件缓存。
如果遇到 RedisDifyCache 导入错误，请确认 src/testcode/cache/init.py 中正确导出了该类，并在当前 Python 解释器中重新执行 pip install -e .[dev]。
如果遇到 N8nClient 属性错误，请重新运行程序，并确保 src/testcode/adapters/n8n.py 已经更新，同时你的 IDE 使用的是安装了最新代码的解释器。
请务必将密钥等敏感信息排除在版本控制之外。
artifacts 目录用来存放生成的报告和输出文件，这些文件通常不应提交到代码仓库中。