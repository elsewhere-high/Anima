# 中文居家陪伴系统

当前运行入口为 V5，包含中文对话、语音、视觉、成员记忆与居家陪护功能。

## 启动

双击 `启动体验.cmd`，或执行 `./start_v5.ps1 -Profile balanced`。

打开 http://127.0.0.1:8768/ 。CPU 使用 `./start_cpu.ps1`，GPU 使用 `./start_gpu.ps1`；停止服务使用 `./stop_v5.ps1`。

## 代码结构

- `v5/`：当前应用、网页、脚本与测试。
- `v4/social_v4/`：V5 使用的共享推理、对话和响应检查模块。
- `v2/social_world_zh/`：V5 使用的模型、策略、数据结构和记忆基础模块。
- `v2/reports/calibration.json`、`v4/models/release.json`：运行必需配置。

V1、V3 独立旧版本及其入口已移至不提交的 `.local-archive/`。V2、V4 仍是当前依赖。

## 环境与模型

本机启动脚本使用 `.venv_zh/Scripts/python.exe`，依赖快照见 `v5/requirements.lock.txt`。Git 保存源码与必要配置，环境、模型、训练数据、运行数据库和生成报告不提交。

新机器需另外准备 `v2/models/qwen35_2B`、`v2/models/social_zh/best`、`v4/models/release.json` 引用的适配器及 `v5/models/` 的感知模型；CPU 量化运行还需 `v4/models/cpu_base_int8.pt`。克隆源码不包含这些资产。

详细说明见 [V5 文档](v5/README.md) 和 [部署说明](v5/deliverables/社会情感升级部署说明.md)。历史报告链接对应本地保留的材料。

## 验证

```powershell
./.venv_zh/Scripts/python.exe v5/scripts/verify_upgrade_regression.py
node --test v5/tests/test_turn_detector.cjs v5/tests/test_voice_queue.cjs
```
