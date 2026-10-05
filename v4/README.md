# 中文社会交互模型 V4：当前理解与多轮回应

2026-09-26 用户重新确定重点：做好当前情绪识别、对话行为、任务理解、社会策略与中文对话。预测／推演不作为本阶段优化及发布要求；旧 V2/V3 证据原样保留。

本轮已完成当前状态训练、两阶段中文回复微调、固定评估，以及 GPU／CPU 实际运行检查。推荐在本机 RTX 4060 上使用 GPU 服务；一个 Qwen3.5-2B 物理底座共享原任务、当前情绪和回复适配层。它是可对接机器人的社会交互组件，尚未经真实家庭现场验收。

公开基准成绩与真实家庭现场表现分开报告。记忆、关系和动作控制保留明确来源，生成文本不等于设备已经执行动作。

## 直接使用

交付时 GPU 服务已在 `http://127.0.0.1:8767` 后台启动。项目根目录执行：

```powershell
Invoke-RestMethod http://127.0.0.1:8767/health
.\.venv_zh\Scripts\python.exe v4/scripts/chat_client.py
```

后台服务停止命令为 `./stop_v4.ps1`。以后启动用 `./start_v4_gpu.ps1`，在前台按 Ctrl+C 停止。模型首次加载需要等待 `/health` ready；不要同时启动多个服务。

接口：`POST /v1/step`，UTF-8 JSON，结构为 `{"observation":{"user_id":"demo","session_id":"home","speech":"今天有点烦，我只想说说，先不用建议。"}}`。连续对话保持相同用户和会话 ID，读取 `response`，分类和分布在 `state`。

## 实测结果

| GPU 固定测试准确率 | 原版 | V4 |
|---|---:|---:|
| CPED 当前情绪，2,398条 | 32.28% | 33.53% |
| CPED 对话行为，2,398条 | 64.43% | 65.01% |
| CPED 正负情感，2,398条 | 54.92% | 55.00% |
| 中文 MEDD 情绪，312条 | 56.73% | 87.18% |

CPED 增益有限，不能用 MEDD 成绩代表所有家庭中文。宏 F1、分组置信区间、逐类别结果和数据来源见报告。原意图／策略参数保留，任务切换前后原分类 logits 实测完全一致。

回复第一轮因视觉幻觉被拒绝发布，随后实际进行修复训练。最终原始回复开发审查为底座 23／48 分、微调候选 34／48 分；这是已知开发题的项目内部评分，不是对话准确率。部署层补充缺失图像处理、设备未执行声明检查，并修复上下文被旧澄清路由截断的问题。

**仍然存在具体错误**：送餐建议有时答非所问，部分知识解释错误，部分故事逻辑较弱。原始回答与失败记录均保留。不能承诺每次情绪识别、安慰或问答都正确。

CPU INT8 可以运行，但属于**实验兼容入口**：96 条验证探针上的情绪标签与 GPU 一致率仅 72.92%，不是与 GPU 等价的验收配置。`start_v4_cpu.ps1` 不能沿用上表精度声明。Linux／ARM／BPU 尚未实机验证。

## 交付文件与证据

- [训练与交付报告](deliverables/训练与交付报告.docx)：适合负责人查看，附实际训练过程、对照结果和限制。
- [使用指南](deliverables/使用指南.docx)：启动、中文多轮对话、记忆授权、设备适配和迁移。
- [最终参数选择](models/release.json)：实际启用的三个当前状态头和回复适配层，未来预测关闭。
- [固定状态评估](reports/current_state_evaluation.json)、[回复评估](reports/dialogue_repair_evaluation.json)、[逐题审查](reports/dialogue_repair_manual_review.json)。
- [GPU 运行记录](reports/runtime_cuda.json)、[CPU 运行与量化差异](reports/runtime_cpu.json)、[真实 HTTP 测试](reports/http_smoke.json)。
- [数据来源及许可声明](THIRD_PARTY_NOTICES.md)。训练协议与日志位于 `runs/current_state_lora`、`runs/dialogue_sft`、`runs/dialogue_repair_v2`。

最终产物哈希清单位于 `deliverables/artifact_manifest.json`；项目根目录运行 `.venv_zh/Scripts/python.exe v4/scripts/build_manifest.py --verify` 可检查文件完整性。122 项自动测试通过，设备测试使用模拟控制器，没有操作真实硬件。
