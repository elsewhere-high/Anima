"""Set workspace entry points to V2 while preserving the previous V1 launchers."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parents[1];WORKSPACE=ROOT.parent
for name in ['README.md','start_gpu.cmd','start_cpu.cmd','start_gpu.ps1','start_cpu.ps1']:
    source=WORKSPACE/name
    backup=WORKSPACE/(('README_V1.md') if name=='README.md' else name.replace('start_','start_v1_'))
    if source.exists() and not backup.exists():shutil.copy2(source,backup)
for device in ['gpu','cpu']:
    (WORKSPACE/f'start_{device}.cmd').write_text(f'@echo off\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0v2\\start_{device}.ps1"\npause\n',encoding='ascii')
    (WORKSPACE/f'start_{device}.ps1').write_text(f"$ErrorActionPreference = 'Stop'\n& (Join-Path $PSScriptRoot 'v2\\start_{device}.ps1')\n",encoding='utf-8')
ev=json.loads((ROOT/'reports/evaluation.json').read_text(encoding='utf-8'))
gpu=json.loads((ROOT/'reports/runtime_cuda.json').read_text(encoding='utf-8'))
cpu=json.loads((ROOT/'reports/runtime_cpu.json').read_text(encoding='utf-8'))
text=f'''# 中文居家机器人社会世界模型 V2

本机已完成 Qwen3.5-2B 文本主干的 LoRA 多任务训练，并提供真实权重、中文 HTTP 服务、用户边界与记忆、候选回应条件下的单步状态预测、CPU 量化导出和模拟控制器。

当前交付适用于本机联调与受控验证。当前情绪与未来状态预测仍明显偏弱，尚未达到可靠自主社会规划或真实家庭产品验收要求。没有实机控制电机、连接真实灯具或编译到机器人 BPU。

## 立即使用

双击本目录的 `start_gpu.cmd`。等待启动成功，打开 http://127.0.0.1:8766/docs。无需重新下载或训练。CPU 使用 `start_cpu.cmd`，两个版本不能同时占用同一端口。

```powershell
.\\.venv_zh\\Scripts\\python.exe v2/examples/robot_client.py
```

演示包含问候、拒绝与恢复、边界记忆、明确确认的客厅灯请求及模拟回执，以及两个候选回应的下一轮分布。确认字段必须来自可信上游对当前请求的确认，不能直接把模型猜测当授权。

## 交付材料

- [中文使用指南](v2/deliverables/中文居家社会世界模型使用指南.docx)
- [负责人训练与交付报告](v2/deliverables/中文居家社会世界模型训练与交付报告.docx)
- [可直接阅读的技术指南](v2/README.md)
- [训练与测试报告 Markdown](v2/deliverables/训练与交付报告.md)
- [数据调研](v2/reports/RESEARCH.md)与[第三方来源和许可](v2/THIRD_PARTY_NOTICES.md)
- [训练权重目录](v2/models/social_zh/best)、[CPU 量化权重](v2/models/social_zh/cpu_int8.pt)

## 真实测试结果

正式训练 34,626 条去重样本、2 轮、9,266 步，用时约 65 分钟，PyTorch 峰值分配显存 4.37 GiB。底座、数据、划分和随机种子均固定并记录。

| 项目 | 结果 | 解释 |
|---|---|---|
| 中文任务意图 | 准确率 {ev['heads']['intent']['accuracy']:.1%} | MASSIVE zh-CN 测试子集 |
| 当前情绪 | 宏 F1 {ev['heads']['emotion']['macro_f1']:.1%} | 13 类，能力偏弱 |
| 下一轮情绪 | 宏 F1 {ev['heads']['next_emotion']['macro_f1']:.1%} | 实验性观察预测 |
| 下一轮对话行为 | 宏 F1 {ev['heads']['next_act']['macro_f1']:.1%} | 不能当作可靠社会规划器 |
| 居家策略 | 准确率 {ev['heads']['policy']['accuracy']:.1%} | 合成措辞测试，非真实家庭成功率 |
| GPU 状态更新 | P50 {gpu['latency']['p50_ms']:.0f} ms | 本机完整状态更新，非生成延迟 |
| CPU 状态更新 | P50 {cpu['latency']['p50_ms']:.0f} ms | 本机量化版，精度有漂移 |

CPU 文件是 x86 PyTorch INT8 线性层与 BF16 词嵌入的混合格式，不是通用 ONNX、RKNN 或 BPU 文件。云端接口可配置，但未调用实际外部推理服务；GPU 同一底座的本地短回答已实际验证。

## 版本与校验

正式交付内容集中在 `v2/`，环境在 `.venv_zh/`。旧版 0.6B 代码和权重仍留在原位置，旧入口另存为 `start_v1_gpu.cmd`、`start_v1_cpu.cmd`，旧说明为 `README_V1.md`。根目录默认启动入口现为 V2。

```powershell
.\\.venv_zh\\Scripts\\python.exe v2/scripts/artifact_manifest.py --verify
```

模型和文件的 SHA256 清单为 `v2/deliverables/artifact_manifest.json`。详细运行证据见 `v2/reports/`。如果重新训练，先备份现有 V2 权重和报告，重新校准并导出后再部署。
'''
(WORKSPACE/'README.md').write_text(text,encoding='utf-8')
print('V2 is now the default; V1 entry points preserved')
