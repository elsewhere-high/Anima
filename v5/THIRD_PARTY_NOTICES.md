# V5 新增组件与研究来源

V4 对话/文字情绪权重及其训练数据说明继续适用，见 `../v4/THIRD_PARTY_NOTICES.md`。本次没有把摄像头图片作为新增训练集。

| 组件 | 来源与固定版本 | 许可/用途说明 |
|---|---|---|
| YuNet 2023mar ONNX | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)，commit `47534e27c9851bb1128ccc0102f1145e27f23f98` | 该模型目录 MIT；使用适配 OpenCV 4.x 的模型，2026 动态形状导出针对 OpenCV 5.x，不因文件较新而盲目替换 |
| SFace 2021dec ONNX | [OpenCV Zoo SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)，同一 commit | 该目录 Apache-2.0；用于自愿登记成员模板匹配，不用于搜索互联网上的陌生人身份 |
| EmotiEffNet-B0 8-class VGAF ONNX | [EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib)，commit `520a051c64cd191521e5934655314e769a319684` | 仓库代码 Apache-2.0；上游模型涉及 AffectNet/VGGFace2 等训练来源，代码许可不等于已经完成全部模型/训练数据商业权利审查。本次未下载这些原始人脸训练数据 |
| BGE-small-zh-v1.5 | [BAAI 模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)，revision `7999e1d3359715c523056ef9478215996d62a620` | MIT；小型中文检索模型，CPU 运行，不声称它是所有场景最强或最新的 embedding 模型 |
| 公开样例图片 | [scikit-image astronaut 文档](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut)，图片取自其 v0.19.3 | NASA 公开领域样例。只用于临时工程测试，不是中国家庭表情验证集。测试登记临时模板在临时目录中删除，不保留到服务数据库 |

模型下载 URL、大小、SHA-256 见 `models/vision/manifest.json` 与 `models/bge-small-zh-v1.5/manifest.json`；上游许可与预处理参考代码在 `reports/upstream/`。未执行上游 pickle 权重，视觉加载 ONNX，BGE 加载 safetensors。

研究借鉴：

- [Savchenko, ICML 2023：Facial Expression Recognition with Adaptive Frame Rate](https://proceedings.mlr.press/v202/savchenko23a.html)：选用其项目的轻量视觉模型；本实现采用简单同脸短时平滑，**没有复现论文的统计自适应帧率算法**。
- [SFace 原论文](https://arxiv.org/abs/2205.12010)：使用 OpenCV 的五关键点对齐和人脸特征匹配。
- [LongMemEval, ICLR 2025](https://arxiv.org/abs/2410.10813) 及 [官方代码](https://github.com/xiaowu0162/LongMemEval)：将跨会话提取、事实更新、时间与拒答作为验收方向；**未运行官方完整 LongMemEval，不报告其 benchmark 分数**。
- [BAAI BGE / FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)：中文语义检索，与关键词、时间和重要性合用。相似度只是排序信号，不是事实真实性分数。

本实现新增的 .py/.html 文件为项目代码；第三方运行库及其许可遵循各自发行包。最终产品对外分发前仍需负责人确认模型与数据使用权，特别是人脸表情模型的训练来源。
# 语音专项新增来源（2026-10-05）

- [Silero VAD](https://github.com/snakers4/silero-vad)：MIT，固定 revision `1e261b036686cd0017d500ee96acd1c4ba572a9d`，原始 LICENSE 与参考实现保存在 `models/vad`；哈希记录见 `reports/speech_20261005/asset_downloads.json`。
- [AISHELL-3](https://www.openslr.org/93/)：官方声明 Apache-2.0；本次从 AISHELL 官方 Hugging Face 镜像下载子集，用于独立训练/诊断。
- [THCHS-30](https://www.openslr.org/18/)：官方声明 Apache-2.0；使用 resource.tgz 的 car/cafe 背景噪声，来源与哈希见 `reports/speech_20261005/noise_downloads.json`。
- [CanCLID/zoengjyutgaai](https://huggingface.co/datasets/CanCLID/zoengjyutgaai)：发布方标记 CC0；本次仅使用一个粤语评书数据文件的子集，属于单说话人数据。
- [SenseVoiceSmall 训练权重](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)：固定 revision `3847d57b6bdf2dd8875cb1508d2af43d80a16bf7`；遵循模型卡链接的 FunASR MODEL_LICENSE（原文保存于 `models/sensevoice_train`）。不要用 FunASR 代码许可替代模型许可。
- OpenCC Python reimplementation 0.1.7：仅用于繁简归一化诊断，安装在 `tools/speech_eval`，保留发行包许可。
- KeSpeech、SeniorTalk、CDSD、WenetSpeech-Yue 的受限数据未用于本次训练。详细范围见 `reports/speech_20261005/README.md`。

# V5.1 新增来源（2026-10-01）

下面各工件均记录在 `models/social/manifest.json`，含固定 revision 或版本化下载地址、大小及 SHA256。不能用代码许可证代替检查点/训练数据许可证。

- [EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib)：使用 revision `520a051c64cd191521e5934655314e769a319684` 的 `enet_b0_8_va_mtl.onnx`。代码 Apache-2.0；保留上游关于 VGGFace2/AffectNet 等训练来源的说明。导出的 `emotieff_va_features.onnx` 仅增加原倒数层输出，没有训练或更改权重。商业发行仍不能仅凭仓库代码许可推定所有训练数据权利。
- [SenseVoiceSmall](https://github.com/QwenAudio/SenseVoice)：FunAudioLLM/QwenAudio；采用 [sherpa-onnx 固定转换](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17) 的 INT8 ONNX，revision 见清单。代码许可与 [FunASR 模型许可](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) 分开保留；转换仓库 LICENSE 引用 FunASR。测试的 zh/en WAV 来自同一公开仓库，只用于回放。
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)：Apache-2.0，采用 1.13.8 CPU Python/runtime 包。
- [MediaPipe](https://github.com/google-ai-edge/mediapipe)：Apache-2.0 代码；采用官方 PoseLandmarker Lite float16 v1 和 FaceLandmarker float16 v1 任务工件，下载地址和校验和见清单。模型卡：[姿态](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)、[人脸](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)。人脸 blendshape 不是 FACS AU。
- [emotion2vec+ base](https://huggingface.co/emotion2vec/emotion2vec_plus_base)：revision `b318240bfe67db81a8c572ecb37ce9c3759b81c9`，模型卡引用 FunASR 模型许可；本次仅在 `reports/upgrade_20261001/` 独立研究测试，不进入正式 runtime。采用 FunASR 官方 Emotion2vec 实现，提取 768D 特征，测试 FP32/动态 INT8；未修改其训练权重。
- [Py-FEAT Detectorv2 模型卡](https://huggingface.co/py-feat/face_multitask_v2) 明确研究/非商业用途；[LibreFace LICENSE](https://github.com/ihp-lab/LibreFace/blob/main/LICENSE.rst) 对商业使用要求另行许可。本次没有下载、打包或运行这两套权重，不能称其已经在本机性能测试中落败。
- [MERTools/MER2026](https://github.com/zeroQiaoba/MERTools)、[AffectGPT](https://github.com/zeroQiaoba/AffectGPT)、[Emotion-LLaMA](https://github.com/ZebangCheng/Emotion-LLaMA)、[RTMPose](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose) 仅作官方资料参考，未纳入运行依赖/大型模型权重，未用其受限数据训练。

官方原文快照和抓取结果在 `reports/upgrade_20261001/upstream/`；部分重试遇到网络超时，原先成功保存的文件仍保留。许可摘要不是法律意见或商业授权证书。
