# V4 模型与数据来源

本目录沿用 [V2 来源说明](../v2/THIRD_PARTY_NOTICES.md) 中的 Qwen3.5-2B、CPED、MASSIVE zh-CN 与 CrossWOZ。各原始许可随现有本地文件保留。V4 继续训练 CPED 当前情绪／对话行为；原有任务理解与控制策略使用 V2 参数。

## 新增数据

| 来源 | 上游声明许可 | 本次使用 |
|---|---|---|
| [CASIA-LM/OpenS2S_Datasets](https://huggingface.co/datasets/CASIA-LM/OpenS2S_Datasets) | Apache-2.0 | 合成中文语音对话的文本部分；不下载音频，不用隐藏推理；仅成人、中性语音条件，进一步筛选情绪支持回复 |
| [OpenAssistant/oasst2](https://huggingface.co/datasets/OpenAssistant/oasst2) | Apache-2.0 | 重建中文父子对话；训练仅采用项目逐条审查的 16 条，验证／测试保持事先固定的原样 |
| [Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset](https://huggingface.co/datasets/Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset) | MIT | 六种可明确映射的情绪；关切和疑问语调不冒充恐惧标签；剔除重复文本并固定分组 |

项目新编居家训练对话明确标注为 `home_authored`。合成数据、电影／电视剧话语、作者自述的人工审查均不等于本项目采集的真实家庭标注。

第一轮对话审查后新增的上下文与信息边界训练目标标为 `grounded_authored`，由项目编写，不是从真实用户采集。正式修复划分见 `data/dialogue_repair_v2/manifest.json` 与 `split_audit.json`；这些模板场景不能作为真实家庭泛化能力的证明。

固定版本、原始文件名、SHA-256 和来源卡保存在 `data/source_manifest.json` 及 `data/raw/*/README.md`。训练实际文件与变换见 `data/state/manifest.json`、`data/dialogue/manifest.json`，逐条训练取舍见 `reports/dialogue_training_curation.json`。

OpenS2S 方法参考 [作者项目](https://github.com/CASIA-LM/OpenS2S) 和 [论文](https://arxiv.org/abs/2507.05177)。本项目只借用其公开文本进行监督微调，不宣称复现语音到语音、多模态或论文成绩。

`sharegpt_gpt4` 下载后仅作质量抽查，没有进入本次训练；原始来源声明与检查记录仍保留。SoulChat、ESConv、COIG-CQIA 和需要额外访问条件的 Infinity-Instruct 没有用于本次训练。

这些是上游公开声明与本项目的可复核使用记录，不是对全部原始内容权属的独立认定。
