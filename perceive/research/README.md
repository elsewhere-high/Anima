# 交接入口（2026-10-08）

先读[仓库根 README](../../README.md)。本文件后半段保留旧轮次研究记录，状态和参数按当时版本理解；旧的“正在运行”“未开通”“未部署”等句子不是当前结论。

最新记录：第32轮五案例各三遍，快速请求 P50 922ms / P95 1805ms，2条格式异常后恢复；空白、静音、无画面各两场控制没有缺失模态归因。第33轮实际页面20秒通过，无异常，完整录制20.022秒；6个新人物检查完成，社会状态准确性未标注。

旧600秒实验最后因快速模型额度不足而未通过完整多模态验收。之后已修正当前状态时间边界、转写确认前缀、真实显示计时、上传转写、模型选择和标签目录；最终候选还没有新的600秒完整通过记录。原电脑4827旧进程未升级，最新磁盘代码须新启动验证。

源码快照和模型/媒体不随本次交接提交；保留公开素材的文字及事件证据。少量历史绝对路径替换为 `<original-anima-workspace>` 或 `<original-user-home>`；这一隐私清理不修改时间与模型输出。`iterations/31-continuous` 和 `33-product-integration` 汇总引用的实际页面分段记录已一并保留。

---

# 当前进展（2026-10-08）

充值后，图文模型与千问实时语音均已恢复。当前在候选服务 4831 验证，正式服务 4827 及用户原有标签页和录制保留。

当前候选使用千问实时语音做字幕，本机 OpenFace / EmotiEffLib、emotion2vec、言语结构模型做声音与画面观察；Flash 提供快速初判，Max 复核。模型均通过真实请求验证，不把调用大模型等同于独立准确率。没有自训练、调用 Interhuman API 或购买资源。

已完成 600.0245 秒实际页面录制与分段日志保存：30 个黑屏静音检查点没有标签；本地表情、声音、言语模型耗时中位数约 162 / 291 / 178ms；快速请求 P50 / P95 为 970 / 1813ms，快速标签实际显示 P50 / P95 为 1253 / 1824ms。完整转写在约 2 秒音频提交后，返回 P50 / P95 为 569 / 660ms；这不包括采集音频的等待时间，也不是开口到首字时间。

本次长测仍有问题：4 条快速输出格式无效后恢复；最后一次请求被拒绝，随后图像请求确认 `insufficient_quota`。短文本探针仍成功，说明不能只用短文本“OK”判断真实感知接口可用。此轮完整多模态验收为 false。未修改“免费额度用完即停”。已验证未带日期的 `qwen3.7-flash` 与 `qwen3.8-max` 仍可处理图像，正在用这两个已测模型继续。

第 32 轮修正当前状态的时间边界：超过 2 秒的复核结果保留记录，不重新显示为当前标签；转写草稿只将确认部分送入语义判断；草稿没有精确音频结束时间时明确标记，排除其“伪低延迟”统计。以上修正正在做五案例重复与无输入对照，尚未升级正式服务。笔记本显示高度也已收紧，让字幕和操作区保持在一屏内。

硬件排查发现 FunASR 构造模型时会覆盖原线程设置。现已在加载后重新应用并回报实际线程数（1），不再把设置值当成运行值。过去标作 3 线程的实测仍保留原始结果，但线程配置不是可靠控制变量。之前的本地转写长测与完整云端长测分开保存，不能混为一个成功实验。

用户不要求标签逐项复现 Interhuman。以真实流式输入、当前状态响应、稳定性、细粒度变化和空白/静音/无画面对照验证；一般准确率没有独立人工真值，不宣称整体能力已等同 Interhuman。官网五案例是开发参考，不是留出集。每个结果均按实际到达时间记录，不用结束后回填冒充实时。

定时任务已删除。沿用用户授权在当前聊天持续完成目标。详细进度见 `iteration-status.json`；本轮证据在 `iterations/26-free-models` 至 `iterations/32-current-evidence`。

---

## 验收调整（2026-10-08）

用户明确说明：不要求案例标签与 Interhuman 完全一致。参考覆盖率与时间重合只保留为诊断记录，不再作为完成门槛。之后主要验证真实流式输入、标签到达与显示延迟、短时变化、稳定性、证据来源、空白/静音/无画面控制和连续运行。一般准确率仍需独立标注，不作未经验证的宣称。定时任务已按用户要求删除，当前聊天持续执行。

## 当前状态（2026-10-08，第22轮）

仍未达到 Interhuman 验收标准。原用户服务4827保持运行；研究候选4831未作为完成版发布。

- 原音视频快速通道第17轮三次重复：23/30参考项在播放中出现，11/30及时出现；这只是官网演示参考一致性，不是独立准确率。
- 当前密钥对 Omni 音视频模型返回 AccessDenied.Unpurchased；qwen3.8-flash 图文接口可用。没有更改模型开通或计费权限。
- 已实现本地 SenseVoice 转写、本地声音情绪/言语卡顿分析与图文融合替代。第21轮8/10播放中出现、2/10及时；第22轮7/10和1/10，未采纳。
- 第22轮快速路径有4次格式异常，不能把其缺测当作正常识别能力。实际完整保存记录在 iterations/22-local-sparse；之前被关闭页面的尝试没有完整结果，不计分。
- 研究测试现按完成案例自动保存到 research/autosaved，保留当时看到的标签和真实到达时间。76项程序检查通过，不等于模型识别达标。
- 下一轮先修复明确的格式/失败恢复问题，再看重复稳定性与新人物负例。10分钟连续验收及独立准确率仍未完成。

# Anima 科研验收工具

## Interhuman 五案例实测与优化方案（2026-10-07 晚）

完整报告见 [interhuman-audit.html](interhuman-audit.html)，可在本机 `/interhuman-audit.html` 查看；计算逻辑为 `summarize-interhuman.py`，指标、来源和代码哈希见 `interhuman-audit-summary.json`。

- 官网默认 Inter-2 的五个案例是网页打包的带时间事件，不是本次实测 Interhuman API。参考快照见 `interhuman-reference-events.json`，不能把它当作独立人工真值或 API 时延。
- 当前模型对同五片段分别实时跑三遍，无参考答案输入：`interhuman-live-comparison.json`。15 个会话无调用错误，77 个完整综合结果中 42 个在输入停止后到达；综合请求 P50/P95 为3573/5543ms。这个统计不是首标签延迟，部分标签先于完整结果流式出现。
- 主测试复用生产推理与状态显示筛选，未开 VAD 说话边界辅助；另外各跑一次开启 Silero v6 的敏感性检查：`interhuman-vad-comparison.json`。开启后关键社会信号仍明显漏检。显示采样100ms，略有利于本应用，主界面250ms更新。
- 即使宽松把“确信”映射 confidence、“不满”映射 frustration，播放期间仅对上3/30个“片段＋参考标签”项；包含停止后的结果为10/30。未扣多报、未检验时间重合，所以只是宽松覆盖，不是准确率。
- 完整片段各离线补测一次：`interhuman-offline-comparison.json`。仍有明显缺失；Steve 片段超过离线声音专家8秒限制，综合模型收到原声但声音专用模型未参与，不能与实时协议混称。
- 结论：尚未达到官网案例的展示水平。五例只覆盖四种参考信号，不能证明其余六类与投入程度已对齐。报告中的优化和门槛是待实施方案，不是当前功能。

这次只增加评估工具和报告，没有调整生产模型、标签定义或用户已有录制。后续改动依次比较：标签定义/引用契约、简短事件输出、逐字与韵律证据、替代原生实时底座；不训练、不调用 Interhuman API。

## 本轮选型结论（2026-10-07）

先看任务是否匹配，再核对论文、具体权重、评测协议和本机真实输出；知名度与比赛名次只作辅助。没有任何一项公开结果能直接证明它胜过 Interhuman，也没有找到其可复现的同协议对照。

| 候选 | 可核实的依据 | 本轮决定与限制 |
| --- | --- | --- |
| EmotiEffLib / HSEmotion | [官方模型表](https://github.com/sb-ai-lab/EmotiEffLib)列出本次使用的 `enet_b2_8` 在 AffectNet 8 类验证集准确率63.03%；[ICML 2023论文](https://proceedings.mlr.press/v202/savchenko23a.html)；[ABAW 2025官方榜单](https://affective-behavior-analysis-in-the-wild.github.io/8th/)中团队获表情识别与犹豫识别赛道第一 | 已部署预训练 ONNX，负责可见表情分类。团队获奖整套方案不等于此单模型，更不等于它已具备犹豫识别能力。 |
| OpenFace 3.0 | [CMU官方仓库](https://github.com/CMU-MultiComp-Lab/OpenFace-3.0)；[论文表III](https://arxiv.org/html/2506.02891v1)中 MTL 的 DISFA/BP4D 动作单元 F1为60/62，表情准确率56%；其他版本指标不同 | 已部署，主要用其8个动作单元，保留原表情分数供对照。它并非所有任务最强；发布权重与论文最佳行不能直接画等号。 |
| emotion2vec | [Findings of ACL 2024论文](https://aclanthology.org/2024.findings-acl.931/)研究语音情绪表征；原模型在 IEMOCAP 五折 WA 为71.79%，需遵守其下游训练协议 | 已部署[plus-large官方9类分类权重](https://huggingface.co/emotion2vec/emotion2vec_plus_large)。原论文结果不属于此权重的零样本分数，不拿来冒充本项目准确率。 |
| AffectGPT | [ICML 2025论文](https://proceedings.mlr.press/v267/lian25a.html)；[MER-UniBench](https://arxiv.org/html/2501.16566v2)九数据集平均分74.77，情感专用任务更匹配 | 保留为复杂情感判断的重点对照。74.77是不同指标的平均分，不是统一准确率；论文最优配置含专门人脸与音频编码。官方推理依赖 CUDA，真实模型尚未部署。 |
| MiniCPM-o 4.5 | [官方项目与部署说明](https://github.com/OpenBMB/MiniCPM-o)：9B、原生音视频、流式能力；官方提供 Mac 推理路径 | 已实现可选 vLLM 服务适配并验证请求格式，未运行真实权重。一般多模态成绩不能证明细粒度情绪准确率。 |

没有把尚未核实发布权重、输入模态不匹配或只靠项目简介的候选纳入当前运行栈。没有自训练，也没有接 Interhuman API。

### 这台电脑能做什么

只读硬件检查显示 M5 MacBook Air、16 GiB 统一内存。1 TB 是存储容量。当前三个专用模型已在 CPU 上真实运行，Python 使用3个计算线程；没有占用外部 GPU。模型、依赖与隔离环境约3.4 GB。

MiniCPM-o 官方 Mac 文档对半双工语音列出16 GB，对完整音视频流建议 M4 Max / 24 GB 以上；当前16 GB Air低于后者推荐配置。这不是断言量化版绝对不能运行，但不能据此承诺它与浏览器、三个专用模型同时运行仍足够快。AffectGPT 官方样例直接使用 CUDA。它们的真实部署与同输入效果对比仍待可用运行环境，当前主判断模型保持千问。

### 本轮真实测试与已知问题

- `specialist-results.json`：5段现有公开素材，71次面部、31次声音推理。面部整条路径 P50/P95 为244.6/252.5 ms；声音为143.9/172.7 ms。这是单次计算耗时，不包括证据积累、取帧和网络。
- `public-baseline.json` 与 `public-specialist-fusion-final.json`：同5段素材的前3秒，基线和当前完整系统各5次真实云调用；具体标签、引用与耗时均保留。不能把输出标签多或少当作准确率。
- `live-specialists-final-qa.json`：22秒连续输入，129次字幕更新、44次面部和21次声音模型返回、12次综合判断；输入结束前发生11次标签出现事件（不是11种不同情绪），无异常通知。此轮面部/声音计算 P50 为264.5/159 ms，综合请求 P50 为4339.5 ms、最大5552 ms。公开短片循环只供联调，不替代自然长时实验。
- `openface-voice-first-results.json`、`live-specialists-qa.json`、`public-specialist-fusion.json` 保留更早的 OpenFace + emotion2vec 版本，不能与最终版本混称。
- **模型分歧真实存在**：OpenFace 与 EmotiEffLib 对同一人脸会给出不同分类；EmotiEffLib 在这71帧上没有达到当前0.65阈值的结果。声音模型也有较多中性和未知输出。这既不能证明它们错，也不能证明保守输出就更准；需要标注验证。
- 表情的0.65/0.85阈值、语调0.65阈值以及连续帧要求都是未校准的开发规则。面部分类与声音分类分别显示“表情”和“语调”，不直接宣称内心状态。相同标签仍可能误判。
- 细微变化的真实召回、准确率提升、复杂判断延迟、说话人绑定和长期稳定性尚未达到验收结论。**没有证据宣称已经媲美 Interhuman。**

汇总可直接查看 `verification-summary.json`。首次未知/中性分类曾触发空历史访问错误，已修复并加入回归检查；修复前诊断记录保留在 `live-specialists-diagnostic-qa.json`。44项自动检查通过，但不用于计算模型准确率。首页5段案例目前保留上一轮的离线分析；本轮专用模型用于自己的实时实验及新的分析请求。

### 可选主模型服务接口

默认无需改配置。以后有 MiniCPM-o vLLM 服务时，设置 `ANIMA_FUSION_BASE_URL`（以 `/v1` 结尾）、`ANIMA_FUSION_MODEL` 与独立的 `ANIMA_FUSION_API_KEY` 后重启。适配器按[官方 vLLM 说明](https://github.com/OpenSQZ/MiniCPM-V-CookBook/blob/main/deployment/vllm/minicpm-o4_5_vllm.md)传入原始 WAV、图片和流式请求。千问密钥不会被转发给该服务，千问仍承担转写。

接口与凭证隔离测试已通过；这不代表远端模型已部署或其准确率已经验证。真实评测仍使用下方工具和独立人工标注。

## 原有边界检查

`boundary-inputs.json` 是8条人工编写的文字边界检查，**不是**多模态情绪真值或留出数据集。`boundary-comparison.json` 的两套结果都通过所列检查，不能用来宣称超过基线。

## 同输入调用

启动主应用并设置密钥后运行：

```sh
node research/run.mjs research/boundary-inputs.json full research/boundary-full.json
node research/run.mjs research/boundary-inputs.json baseline research/boundary-baseline.json
```

输入清单为 `{ "samples": [{ "id": "clip-001", "inputFile": "clip-001.input.json" }] }`；也可直接提供 `input` 对象。

单段输入：`start` 为本次会话绝对时间，`duration` 最多30秒，`audio` 为WAV/MP3的base64与mimeType，`frames` 是相对时间t和JPEG base64，`face` 是相对时间与动作系数。`transcript` 可供仅文字消融；`context` 的原话必须带start/end，限定过去45秒。前端采集已经使用该结构。

模式：`full` 包含可用专用模型、本地测量、融合约束与状态定义；当前 `baseline` 使用同一个千问底座、同样音画和合理的20标签结构化提示；`text / audio / video` 切断其他模态。若启用外部主模型，基线仍是千问，报告必须注明底座已经不同。云调用有实际费用，脚本逐个样本运行，不自动扩大数据集。上传回看入口的声音专用模型目前只处理8秒以内的16 kHz WAV；更长或其他格式仍可交给综合模型，不能算作已运行声音专用分析。

浏览器 `/ablation-qa.html` 可以直接从已安装的公开案例生成同一段输入并调用完整系统、基线、仅声音、仅画面。它只验证集成；观察结果不充当人工真值。

## 人工标注与评分

清单每个样本必须包含：

```json
{
  "id": "clip-001",
  "person": "anonymous-person-01",
  "split": "heldout",
  "annotations": [
    {"annotator":"rater-a","observations":[],"states":[],"uncertain":true},
    {"annotator":"rater-b","observations":[],"states":[],"uncertain":true}
  ],
  "consensus": [{"label":"反对","evidenceAvailableAt":3.2}],
  "unknown": false
}
```

这只是格式例子，不是已收集的样本。标注应分开记录可观察动作、当前状态推断、本人自述与可核对事实；分歧经仲裁后填写 consensus，不确定保留空数组和原因。`evidenceAvailableAt` 必须由只看当前已到达内容的标注者确定，不能用未来语句倒推。

同一个人不能同时出现于development和heldout。建议按修订方案准备约20人、200～400短片段并加入连续录制，至少两名独立标注者。调参后不能再称开发样本为留出样本。

```sh
node research/score.mjs manifest.json full.json baseline.json result.json
```

输出各标签精确率/召回率/F1、负例误报、覆盖/未知/失败率、请求时延P50/P95；若提供实际发现与证据可用时间，则报告发现延迟。对照按人分组bootstrap，报告标签集合完全一致率差值及区间。缺测返回null，不伪造0或100%。异常调用算失败，不能通过全部拒答获得有效覆盖率。

“引用可追溯率”只检查结构上有引用，不能等同于证据正确率；后者须人工审阅原始音画。尚需人工补充变化定位、说话人绑定、长时稳定性与真实失败案例评审。
