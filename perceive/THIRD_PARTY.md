# 当前配置补充（2026-10-08）

最新默认链路为云端转写 + 本机面部/声音/言语结构模型 + Flash/Max 图文融合。Flash/Max 不接收原始声音；下方“综合模型收到原声”的内容属于早期实现。

- Romana 言语结构：[作者仓库](https://github.com/amritkromana/disfluency_detection_from_audio)，任务权重与 SHA-256 见 `research/romana-disfluency-evidence.json`；约94.4M参数，英语电话语音训练。`integrations/setup-speech.py` 单独准备，不随 Git 分发权重。
- SenseVoice：[官方仓库](https://github.com/FunAudioLLM/SenseVoice)。仅显式启用的本地转写备选，默认不运行。
- CREMA-D：[官方数据仓库](https://github.com/CheyneyComputerScience/CREMA-D)。六段中性材料的选择规则、原始投票和媒体 SHA-256 在 `research/cremad/neutral-selection.json`。仅用于有限的新人物检查，不是十个社会信号的人工真值。
- Qwen Flash / Max：[Flash文档](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[Max文档](https://help.aliyun.com/zh/model-studio/qwen3-8-max)。云端服务，不属于已本机部署的开放权重。
- 研究媒体由准备脚本从原来源取得，未在源码仓库重新分发。第三方代码、模型、数据仍各自遵守其原有说明。

---

# 素材与依赖

## 参考画面

五个视频和封面来自 [Interhuman 官网 demo](https://www.interhuman.ai/)，供本次本地科研原型对照使用：Yann LeCun、Steve Jobs、Elon Musk、Pep Guardiola、Mark Zuckerberg。

视频地址形式：`https://www.interhuman.ai/videos/v3demo/<id>.mp4`；封面地址形式：`https://www.interhuman.ai/images/v3demo/reel-posters/<id>.jpg`。完整地址、下载大小和 SHA-256 在 `asset-manifest.json`。素材归原权利人；首页使用 Anima 调用千问产生的原文转写与离线分析，不代表 Interhuman 的识别结果或人工真值。字幕显示节奏为窗口内估算，非人工逐词对齐。

## 实际运行的开源组件

| 组件 | 固定版本 | 上游 |
| --- | --- | --- |
| MediaPipe Tasks Vision | 1.0.1 | [Google MediaPipe](https://github.com/google-ai-edge/mediapipe)，Apache-2.0 |
| VAD Web | 0.0.31，Silero v6 | [ricky0123/vad](https://github.com/ricky0123/vad)，ISC；[Silero VAD](https://github.com/snakers4/silero-vad)，MIT |
| ONNX Runtime Web | 1.22.0 | [Microsoft ONNX Runtime](https://github.com/microsoft/onnxruntime)，MIT |
| ws | 8.22.0 | [websockets/ws](https://github.com/websockets/ws)，MIT |
| undici | 8.11.2 | [Node.js undici](https://github.com/nodejs/undici)，MIT |
| OpenFace 3.0 | openface-test 0.1.26，权重固定校验 | [CMU-MultiComp-Lab/OpenFace-3.0](https://github.com/CMU-MultiComp-Lab/OpenFace-3.0) |
| EmotiEffLib / HSEmotion | enet_b2_8 ONNX，权重固定校验 | [sb-ai-lab/EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib) |
| emotion2vec-plus-large | FunASR 1.2.7，权重固定版本 | [emotion2vec 官方模型卡](https://huggingface.co/emotion2vec/emotion2vec_plus_large) |
| 本机推理运行库 | torch 2.8.0、ONNX Runtime 1.22.1 | Python 完整版本见 `integrations/requirements.lock` |

依赖由官方 npm 包复制至 `public/vendor`。Google 的 Face Landmarker 模型从官方模型存储下载，地址记录于素材清单。仓库与分发包各自的许可证和模型说明仍适用。

## 接口依据

- [千问 WebSocket 接入概览](https://platform.qianwenai.com/docs/api-reference/realtime-api/websocket-overview)：统一官方实时地址和鉴权。
- [千问实时客户端事件](https://platform.qianwenai.com/docs/api-reference/real-time-multimodal/client-events)、[服务端事件](https://platform.qianwenai.com/docs/api-reference/real-time-multimodal/server-events)：持续音视频输入、手动触发与文本输出。
- [旧百炼 Qwen-Omni-Realtime](https://help.aliyun.com/zh/model-studio/realtime)：业务空间地址兼容方式。
- [Qwen-Omni](https://help.aliyun.com/zh/model-studio/qwen-omni)：回看模型的音视频输入与流式文本返回。
- 旧 Gemini 适配保留为历史实现和错误处理测试，当前产品入口使用千问。
- [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js)：面部点位与 blendshape 的含义和浏览器运行方式。
- [VAD Web 浏览器文档](https://docs.vad.ricky0123.com/user-guide/browser/)：语音开始、结束和原始音频帧回调。

核对日期：2026-10-07。千问是云端接口；上表专用模型在本机执行。权重地址、固定版本和 SHA-256 见 `integrations/models.lock.json`，安装器会校验下载内容。各上游代码、权重和训练数据分别适用其原许可证及说明。本项目当前为本地科研原型。

## 2026-10-07 早期 V2 记录

V2 将连续转写与状态判断拆开：实时 WS 只提交声音供 ASR；状态服务独立给 Qwen3.8 Omni 发送最近5秒原声、帧、面部动作序列与本地声音测量。参考[手动提交不会自动产生模型回复](https://help.aliyun.com/zh/model-studio/client-events)的官方事件定义。所有推理仍在本次授权的阿里云接口，本地测量不直接映射到心理类别。

本地声音测量与动作描述借鉴已有 Anima 的 `v5/social_v5/audio_features.py`、`expression_actions.py` 的边界与算法思路；这里使用适合持续 PCM 的 JavaScript 实现，未加载原项目的个人历史基线。

后续专用模型版本将综合窗口改为3秒、画面改为2 fps，并行运行本机表情、动作和声音模型，再将结果连同原声与画面交给融合判断。早期 V2 的5秒配置已不再使用。
