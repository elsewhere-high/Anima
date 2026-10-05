# 中文居家社会世界模型 V2

本项目面向中国家庭机器人，提供中文状态识别、候选回应条件下的下一轮状态预测、个人边界与偏好记忆，以及可接入机器人控制器的 HTTP 接口。底座为 Qwen3.5-2B 文本主干，LoRA 与八个任务头共同训练。

这是有真实训练权重和测试记录的工程组件。预测范围是下一轮对话的情绪与对话行为；没有从摄像头直接理解画面，也没有经过真实机器人家庭试验或具体 BPU 编译验证。性能数字见 `reports/evaluation.json`，不能用底座排行榜代替本项目的测试。

本轮独立测试中，中文任务意图准确率为 87.2%，当前 13 类情绪宏 F1 为 19.5%，下一轮情绪与对话行为宏 F1 分别为 9.9% 和 7.8%。因此可以进行接口联调与受控任务验证，但情绪理解和未来状态预测仍属实验能力，不能依靠它们自主规划社会行为。

## 在这台电脑上启动

双击 `start_gpu.cmd`，等待控制台出现 `Application startup complete`。打开 http://127.0.0.1:8766/docs 可交互调用接口；http://127.0.0.1:8766/health 用于健康检查。CPU 版本使用 `start_cpu.cmd`。首次加载需要读取模型权重，应等到健康检查成功后再接入机器人。

已有环境位于项目上一级 `.venv_zh`，无需再次下载。GPU 和 CPU 服务使用同一个端口，每次只启动一个。关闭窗口或在服务终端按 Ctrl+C 停止。`--workers 1` 是有意设置：多个 worker 会复制模型并耗尽显存。

```powershell
# 在“模型”目录执行；需要先启动服务
.\.venv_zh\Scripts\python.exe v2/examples/robot_client.py
```

示例依次发送问候、拒绝打扰、边界保持、恢复对话和开灯请求，然后比较两个候选回应的下一轮预测。控制器是有回执的模拟器，输出明确包含 `simulated: true`。

## 最小接口调用

```python
import requests
base = "http://127.0.0.1:8766"
observation = {
    "user_id": "resident_01", "session_id": "living_room_01",
    "speech": "今天不太想说话，让我安静一会儿",
    "identity_verified": True, "memory_consent": True,
    "asr_confidence": 0.96
}
r = requests.post(base + "/v1/step",
    json={"observation": observation}, timeout=30)
r.raise_for_status()
decision = r.json()
print(decision["action"], decision["response"])
```

明确拒绝打扰时，策略优先保持安静。下一次用相同身份发送普通话语不会自动取消边界；可说“现在可以聊天了”，或由上游明确提供 `boundary: "open"`。对话与距离限制分别保存，恢复聊天不会自动取消先前的距离限制；保持距离也不妨碍普通对话。结构化 open 表示明确解除两项限制。引号、转述与否定有专门处理，但任意自然语言边界仍可能识别错误；上游已经确认的边界应通过结构化字段传递。

响应包含 `neural` 原始分类概率、`state` 社会状态、`overrides` 策略原因、`motion` 移动请求、`task` 设备任务和 `latency_ms`。温度校准只说明在验证分布上的置信度调整，不能把分数当成真实人的心理测量。`trust` 保持 `null`；熟悉程度可以由明确输入提供，或者以交互次数作可解释的粗略估计。

## 预测候选回应

```python
r = requests.post(base + "/v1/imagine", json={
    "speech": "今天工作不顺心，挺难过的",
    "history": [["对方", "今天过得怎么样？"]],
    "candidates": ["听起来你很难受，我可以听你说。", "这有什么好难过的。"]
}, timeout=30)
r.raise_for_status()
print(r.json())
```

每个候选回应得到 `next_emotion`、`next_act` 的分布。模型结合神经预测头与从 CPED 训练对话统计出的条件转移表；转移表以当前用户和候选回应的预测状态为条件，混合权重只在验证集选择。没有在推理时使用真实未来标签。`negative_probability` 是若干负向情绪类别概率的和，并非风险评估或因果伤害概率。这个接口只提供咨询性预测，默认不会用它覆盖用户拒绝、控制器限制或人工授权。预测步长固定为 1，不能把递归调用解释为经过验证的长期社会模拟。

## 接入机器人感知和控制器

ASR 文本放入 `speech`；低于 0.65 的 `asr_confidence` 会请求澄清，已确认边界和紧急事件优先。`person_present` 参与静默规则，`gaze` 回传为注意方向；`distance`、`pose`、`movement` 是预留感知字段，本次没有训练其与情绪的联合预测。实际距离约束由控制器传感器检查。`emergency_verified` 只能由上游已验证的紧急事件提供，普通负面情绪不会自动拨打电话。

`user_id` 是调用网关已核验的身份键；不能把分类器输出当身份验证。默认用户匿名，不保存长期记忆。只有 `identity_verified`、`memory_consent` 都为真且身份不是 anonymous，才把偏好和边界写入 SQLite。短期历史最多四轮，空闲五分钟过期；不同 user_id 和 session_id 隔离。长期记忆保存明确偏好和用户主动提供的 `memory_note`，不会偷偷把完整对话写入数据库。

移动需 `motion_authorized: true`；它应是对当前已确认移动请求的授权，不能当成常开的总开关。即使模型请求 APPROACH 或 FOLLOW，下游仍须完成导航避障、速度限制和有效期检查。`social_world_zh/adapter.py` 将允许的结果变成带 UUID、时间戳与 1 秒有效期的控制器请求；重复和过期请求在模拟器中会被拒绝。真实机器人用自己的 SDK 替换模拟器的 `submit`，并回传真实执行结果。当前服务不直接连接电机。

设备任务需要先确认 `target_device` 和 `confirmed_task_intent`，再设置 `task_execution_authorized: true`。例如确认客厅灯设备 ID 后，`iot_hue_lighton` 可映射成 `turn_on`。未在动作适配器白名单中的播放、联系他人、邮件等意图不会自动执行；返回意图后应交给上游的专用技能处理。识别到“关灯”不代表灯已关闭。

已确认且在白名单内的结构化设备意图优先于神经分类结果，原始预测仍在 `neural` 保留，覆盖原因记入 `overrides`。这些确认字段应由可信上游针对当前请求提供，不能直接照抄模型猜测作为授权。明示边界、语音低置信度和拒绝表达仍优先处理。示例客户端另演示一次明确确认的客厅灯请求，模拟器应返回 acknowledged；这不代表真实灯具已经执行。

## 记忆和提醒

明确偏好可用 `preferred_distance`、`preferred_style`、`relationship_level`、`known_topics` 传入。普通检索返回最多五条用户提供的相关记忆；它是轻量字面检索，不是额外的向量模型。偏好主要参与策略和输出样式，不宣称神经网络已学会长期关系推理。

设定持久提醒需已经同意记忆，并显式提供 `reminder_after_seconds` 与 `reminder_text`。服务不会猜测含糊的中文日期。控制器轮询 `GET /v1/users/{user_id}/reminders`，实际展示后调用 `POST /v1/users/{user_id}/reminders/{reminder_id}/ack`；未确认前会继续返回，以避免丢失。

`DELETE /v1/users/{user_id}` 清除该用户的长期记忆、提醒和进程内历史。SQLite 默认位于 `data/runtime.sqlite`。生产网关应限制每个身份可访问的用户键；本服务的 Bearer token 是机器人网关级鉴权，不是多租户用户鉴权系统。

## 复杂问题与联网兜底

默认快速接口使用有限动作和中文短回复模板。调用时设置 `local_reasoning: true`，可在 GPU 后端遇到 CLOUD_REASON 时使用同一底座的冻结生成能力作本地短回答。该路径比分类慢，生成文字没有动作执行权限，不属于本次社会预测头的训练成果。CPU 量化后端以模板和转交为主。

如已有推理服务，可设置 `SOCIAL_CLOUD_URL` 为完整 chat completions URL、`SOCIAL_CLOUD_PROTOCOL=chat_completions`，并提供 `SOCIAL_CLOUD_MODEL` 和 `SOCIAL_CLOUD_TOKEN`。调用还需 `cloud_consent: true`。代码只发送当前 speech，不发送用户身份、历史记忆或传感器数据。未配置、未同意和超时都返回明确状态，不伪装成已成功联网。本次没有创建付费账号或使用未知密钥；外部服务连通性不在本地模拟测试的证明范围内。

`.env.example` 是配置说明文件，不会被自动加载。PowerShell 用 `$env:SOCIAL_API_TOKEN='自定密钥'` 设置；客户端发送 `Authorization: Bearer 自定密钥`。需要局域网访问时，应先配置令牌和网关，再自行将监听地址改为受控地址。默认只监听本机。

## 训练复现

训练与下载入口位于 `scripts/`；原始数据来源、版本和 SHA256 见 `data/provenance.json`。固定划分清单见 `data/processed/manifest.json`。在项目上级目录运行：

```powershell
.\.venv_zh\Scripts\python.exe v2/scripts/build_data.py
.\.venv_zh\Scripts\python.exe v2/scripts/audit_data.py
.\.venv_zh\Scripts\python.exe v2/scripts/train.py --epochs 2 --batch 8
.\.venv_zh\Scripts\python.exe v2/scripts/evaluate.py
.\.venv_zh\Scripts\python.exe v2/scripts/export_cpu.py
.\.venv_zh\Scripts\python.exe -m pytest v2/tests -q
```

重训会覆盖 V2 的 best、last 和相关报告，应先复制已有交付权重。`--resume` 只从上一个完整 epoch 的 last 恢复；不是每个优化步骤都保存，异常中断可能需要重跑当前轮。最佳模型仅依验证集选取，测试集不参与检查点选择。原始多模态底座和训练集在本机已经下载完成。

Linux x86 的代码入口相同。准备 Python 3.12 venv，先安装适配驱动的 Torch，再按 `requirements.txt` 安装依赖；完整实际版本见 `requirements.lock.txt`。将工作目录设为 v2 后，运行 `SOCIAL_DEVICE=cuda python -m uvicorn social_world_zh.server:app --host 127.0.0.1 --port 8766 --workers 1`。Linux、ARM 和具体机器人板卡需要各自实机验证；本次实测平台为 Windows RTX 4060 笔记本。

## 排错与交付文件

CUDA 不可用时先执行 `nvidia-smi`，检查训练环境的 Torch 是否带 CUDA。显存不够时关闭重复服务和其他 GPU 模型，再降低训练批量；不要通过增加 worker 解决速度问题。CPU 速度、量化格式和实测结果见 `reports/cpu_export.json`、`reports/runtime_cpu.json`，GPU 结果见 `reports/runtime_cuda.json`。

`models/qwen35_2B` 是底座；`models/social_zh/best/adapter` 和 `heads.pt` 是训练产物，单独的 LoRA 文件不能脱离底座运行。`models/social_zh/transition_prior.npz` 与 `transition_config.json` 是条件转移表与验证集拟合参数；`reports/calibration.json` 是任务头温度参数。`models/social_zh/cpu_int8.pt` 是 CPU 专用导出。Qwen3.5 的混合注意力含特定状态算子，这份 PyTorch 量化文件不能直接当成通用 ONNX、RKNN 或 BPU 编译文件。

负责人材料位于 `deliverables/`；训练配置、事件日志、校准、测试与数据审计位于 `reports/`。汇报中应把“本机组件链路验证通过”与“真实家庭机器人已验收”分开，后者仍需目标硬件和真实家庭试验。
