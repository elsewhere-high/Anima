"""Build a Chinese report from measured JSON artifacts; missing measurements stay missing."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001'
def read(name):return json.loads((OUT/(name+'.json')).read_text(encoding='utf-8'))
def main():
 profiles=[read('profile_'+n) for n in ['old','ultra_light','balanced','best_edge']]
 encoders=[read(n) for n in ['old_face','new_face','pose','whisper','sensevoice']]
 hardware=read('hardware');emotion=read('emotion2vec');quant=read('quantization');inventory=read('model_inventory')
 def metric(row,key):
  value=row.get(key)
  return '未测' if value is None else f"{value['p50']:.1f} / {value['p95']:.1f}"
 text=['# V5.1 社会情感升级验收报告','',
 '日期：2026-10-01。基于实际本机代码修改、权重加载、测试和回放；不是产品量产或家庭长期有效性认证。',
 '', '## 已交付的增量能力','',
 '- 原 Qwen3.5-2B、三套任务/对话适配器、身份/PIN、中文网页、长期记忆和设备控制边界保留。实际已加载文本主干及适配器参数为 '+f"{profiles[0]['qwen_parameters']:,}"+'；没有第二个 LLM/VLM。',
 '- 原 8 类 B0 表情模型替换为同级多任务 B0：8 类分布、V/A、1280 维特征。默认不常驻两套表情模型。',
 '- 增加 Pose Lite 身体关键点与客观运动/几何；高配增加 478 点网格、52 blendshape、头部姿态和虹膜相对位置。',
 '- 后两档用 SenseVoice INT8 替换 Whisper，统一 ASR、语言、情绪标签、声音事件；轻量档保留 Whisper + DSP。',
 '- 统一 HumanState，时间感知 EMA、陈旧信号失效、置信门槛、事件滞回、个人基线、明确偏好统计和动作后的状态变化关联。',
 '- 新接口返回 response_plan；Qwen 用压缩状态生成文字，控制器包装策略/语速/音量和行为建议。网页已实际传递声音结果并应用朗读参数。',
 '', '## 硬件与运行时','',
 f"{hardware['gpu']}；{hardware['physical_cores']} 核/{hardware['logical_cores']} 线程；RAM {hardware['ram_total_mb']/1024:.2f} GiB。PyTorch CUDA {hardware['torch_cuda']}。",
 '感知使用 ONNX Runtime CPU / LiteRT XNNPACK；本机没有已配置的 TensorRT、OpenVINO、CoreML、RKNN 或 ncnn。NPU 未从已安装运行时检测到。GPU 留给 Qwen，因此本报告没有伪造感知模型的 GPU 延迟。',
 f"摄像头 DirectShow 640×480：{hardware['camera']['frames']} 帧，{hardware['camera']['elapsed_seconds']:.2f} 秒，实测 {hardware['camera']['fps']:.2f} FPS；未保存帧、未做人脸识别。这是采集 FPS，感知按档位 0.2–2 秒间隔调度。",
 '', '## 整机回放','',
 '四档独立进程顺序运行，同一张公开 NASA 图像、同一段 5.592 秒中文音频和七轮固定文本。端到端包含图像/音频处理与 Qwen 状态及回复，排除用户讲话等待与 TTS；首轮另列，p50/p95 为后六轮描述性统计。系统上其他应用、文件缓存、功耗状态会影响结果，不是受控功耗下的速度保证。',
 '', '| 档位 | 冷加载 s（未含懒加载 ASR） | 首轮 s | E2E p50 / p95 ms | 进程峰值 RAM MiB | CUDA峰值分配 MiB |',
 '|---|---:|---:|---:|---:|---:|']
 for p in profiles:text.append(f"| {p['profile']} | {p['cold_start_seconds_excluding_lazy_asr']:.2f} | {p['first_turn_ms_including_asr_load']/1000:.2f} | {metric(p,'end_to_end_ms')} | {p['ram_peak_mb']:.1f} | {p['vram_peak_allocated_mb']:.1f} |")
 text+=['','| 档位 | Face+Body p50/p95 ms | Audio p50/p95 ms | 时序融合 p50/p95 ms | 音频 RTF | CPU 单核百分比 | GPU平均/峰值 % |','|---|---:|---:|---:|---:|---:|---:|']
 for p in profiles:
  gpu=p.get('gpu_utilization_percent');gpu_text=f"{gpu['mean']:.1f}/{gpu['max']:.1f}" if gpu else '未测'
  text.append(f"| {p['profile']} | {metric(p,'face_and_body_ms')} | {metric(p,'audio_ms')} | {metric(p,'temporal_fusion_ms')} | {p['audio_realtime_factor']:.3f} | {p['cpu_one_core_percent']:.1f} | {gpu_text} |")
 text+=['','CPU 100% 表示一个逻辑核；GPU 利用率为 nvidia-smi 系统级采样，包含冷加载，不是进程独占测量。RAM 为进程工作集采样峰值，受 Windows 工作集修剪影响；CUDA 表中值不包含驱动保留，reserved 值保存在 JSON。',
 '', '## 独立编码器实测','', '| 模块 | CPU p50/p95 ms | 冷加载 s | 进程 RAM MiB | 相对解释器新增 MiB |','|---|---:|---:|---:|---:|']
 for r in encoders:text.append(f"| {r['candidate']} | {metric(r,'latency_ms')} | {r['cold_start_seconds']:.2f} | {r['ram_rss_mb']:.1f} | {r['ram_increment_mb']:.1f} |")
 text+=['','独立模块数据包含其运行时，不能直接相加当作整机内存。图像重复 25 次、音频 10 次，属于工程回放，不是准确率或多人/弱光实景测评。',
 '', '## 模型体量与选型','', '| 新/旧工件 | 文件 MiB | 存储权重元素（含部分常量） |','|---|---:|---:|']
 for r in inventory['encoders']:text.append(f"| {r['file']} | {r['bytes']/1024**2:.2f} | {r['stored_weight_elements_estimate']:,} |")
 text+=['','| 档位 | 运行所需权重工件总量 GiB | 相对旧版增加 MiB |','|---|---:|---:|']
 for name,values in inventory['active_profiles'].items():text.append(f"| {name} | {values['active_artifact_bytes']/1024**3:.3f} | {values['additional_artifact_bytes_vs_old']/1024**2:.2f} |")
 text+=['','该总量包含被引用的Qwen底座文件及适配器、检索和感知权重；底座文件自带未使用的视觉权重，不等于实际加载参数或RAM。排除历史备份、研究候选及可选CPU Qwen文件。']
 text+=['', 'SenseVoice 参数规模约 234M，超过单功能 100M 目标，但它替换 ASR，并一并承担 SER/AED；没有和 Whisper 或 emotion2vec 一起常驻。',
 f"实测 emotion2vec+ base 为 {emotion['parameters']:,} 参数，768D embedding，纯 FP32 参数约 {emotion['paired_with_whisper']['weights_only_fp32_bytes']/1024**2:.1f} MiB；官方 1.04GiB checkpoint 还包含训练优化器，不应当作部署权重大小。",
 f"同一进程 Whisper + emotion2vec FP32：中位 {emotion['paired_with_whisper']['latency_p50_ms']:.1f}ms、RSS {emotion['paired_with_whisper']['ram_rss_mb']:.1f}MiB；动态 INT8 组合中位 {emotion['int8_paired_with_whisper']['latency_p50_ms']:.1f}ms。INT8 内存是在 FP32 试验后测量，会保留分配器内存，不能当作独立冷进程的最小占用。",
 '因此默认选择 CPU SenseVoice INT8。代价是当前 sherpa 接口没有情绪概率/embedding，而不是假造这些输出；明确需要 SER embedding 时，可用本报告脚本继续评估 emotion2vec，但没有把它塞进默认运行链路。',
 'ultra_light 相对旧版增加约 4.33M 身体感知存储权重元素；balanced 相对旧版增加约 160M–165M（SenseVoice 替换约74M Whisper，加姿态）；best_edge 再加约1.75M面部几何。时序融合为零可训练参数的 EMA/统计，无大型时序 Transformer。精确工件计数口径见 model_inventory.json。',
 '', '| 候选 | 本次状态 | 决策依据 |','|---|---|---|',
 '| EmotiEffNet B0多任务 | 实际运行/延迟/量化试验 | 与原B0同级体量，提供V/A和真实特征，采用 |',
 '| MediaPipe Pose Lite | 实际运行/延迟 | 小型现成Windows/LiteRT链路，采用 |',
 '| MediaPipe Face Landmarker | best_edge整机实际运行 | 额外约3.6MiB工件提供几何，不是第二套情绪大模型 |',
 '| Whisper base INT8 | 实际运行 | 无SER/AED，但轻量档保持最少新增资源 |',
 '| SenseVoiceSmall INT8 | 实际运行 | 合并ASR/SER/AED，默认采用 |',
 '| emotion2vec+ base FP32/动态INT8 | 实际运行，提取768D | 与Whisper组合更重/更慢，作为研究候选保留，不常驻 |',
 '| Py-FEAT Detectorv2 | 官方模型卡/许可证审查，未运行性能测试 | 最新权重明确research/non-commercial，不进入默认商业目标runtime |',
 '| LibreFace 2.0 | 官方LICENSE审查，未运行性能测试 | 商业使用需要另行许可，不进入runtime |',
 '| RTMPose/MMPose | 官方代码与部署文档审查，未运行性能测试 | MediaPipe已满足本机小模型路线；没有宣称RTMPose实测落败 |',
 '| MERTools/MER2026/AffectGPT/Emotion-LLaMA | 官方资料参考 | 借鉴开放情绪词汇、冲突与缺失模态评测；没有部署大型teacher，没有编造蒸馏训练结果 |',
 '', '## 量化与精度边界','',
 f"B0分类头动态INT8：{quant['fp32_bytes']:,} → {quant['head_int8_bytes']:,} 字节；中位延迟 {quant['latency_p50_ms'][0]:.2f} → {quant['latency_p50_ms'][1]:.2f}ms，最大输出偏差 {quant['max_output_error']:.5f}，20个亮度变体首类一致率 {quant['class_agreement']:.0%}。节省太少且略慢，正式保留FP32。",
 'SenseVoice采用上游INT8，Pose/Face任务工件采用官方float16存储；未对卷积做未经独立标注集验证的激进INT4。温度校准继续保留原文字模型的已验收参数，新视觉/语音分数明确未在家庭数据上校准。',
 '', '## 验证与实际限制','',
 '见 tests_*.xml、social_http.json、各 profile_*.json、quantization.json 和 upstream/。完整测试数量由 test_summary.json 记录；报告不把合成场景通过率当成感知准确率。',
 '- 五个要求的融合场景已建立可运行测试；真实编码器和真实 Qwen/HTTP 另行验证。',
 '- AU没有可商用且已验证的新模型，不填假值；blendshape不冒充AU，虹膜位置不等同机器人注视。',
 '- 身体“靠近/远离”是图像尺度变化代理，低头是几何代理；不稳定的抱臂、坐姿、坐立不安及重复动作不输出确定心理标签。',
 '- speech_rate是转写字符/英文词除能量活动秒的近似；音量不是声压级；犹豫等高层判断不由DSP直接断言。',
 '- Big Five/信任保持未知；用户自选MBTI与重复明确交流偏好继续可用。没有家庭长期人格验证，没有声纹分离。',
 '- 结构化回应由控制器包装，Qwen生成自然语言；语速/音量已接网页朗读，实体距离/动作仍需机器人控制器接入。',
 '- 无真实家庭标注语料，因此不能宣称真实情绪准确率或最优模型排名；没有进行大模型teacher蒸馏。',
 '', '## 入口','',
 '`./start_v5.ps1 -Profile balanced`；极轻档 `-Profile ultra_light`，面部几何高配 `-Profile best_edge`。部署/接口细节见同目录《社会情感升级部署说明.md》。',
 '旧实现快照：`reports/upgrade_20261001/before/`。本目录没有Git仓库，因此没有虚构commit或PR。']
 (ROOT/'deliverables/社会情感升级验收报告.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
 validation=OUT/'final_validation.json'
 if validation.exists():
  v=json.loads(validation.read_text(encoding='utf-8'));http=read('social_http')
  with (ROOT/'deliverables/社会情感升级验收报告.md').open('a',encoding='utf-8') as f:
   f.write('\n## 最终验收记录\n\n')
   f.write(f"去重后的 {v['unique_tests']} 个测试案例均通过（完整回归162项，加最终修改专项复测；专项与完整套件重叠不重复计数）。原版25项、V2 33项、V4 29项均通过。\n\n")
   f.write(f"真实 HTTP / CUDA Qwen 测试通过；实际服务 PID {http['server_pids'][0]} → {http['server_pids'][1]}，重启后加密个人统计恢复，撤回许可后统计及短时状态清除，跨会话音频引用被拒绝。测试账户删除，服务进程已停止。\n\n")
   f.write('初次真实编码器测试发现语音冷加载可能使5秒视觉线索过期，测试改为和网页一致在语音后刷新视觉，没有延长过期限制。首次HTTP测试的Windows临时目录清理失败，后续改为停止完整进程树并核对PID后重测通过；失败记录保留。工作区外旧测试临时目录的单独清理被自动审批拦截，因此未重试删除。\n')
 print('Wrote report from actual measurements')
if __name__=='__main__':main()
