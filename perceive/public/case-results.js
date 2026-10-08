export default {
  "createdAt": "2026-10-07T13:33:57.832Z",
  "scope": "真实模型对公开案例的离线分析，不是人工真值，不代表实时提前识别",
  "results": [
    {
      "id": "yann-lecun-wef",
      "duration": 6.869375,
      "status": 200,
      "transcript": "Um, so what are the limitations of current AI systems? There are four things that are essential to intelligent behavior that they really don't do very well.",
      "segments": [
        {
          "start": 0,
          "end": 6.869375,
          "text": "Um, so what are the limitations of current AI systems? There are four things that are essential to intelligent behavior that they really don't do very well."
        }
      ],
      "observations": [
        {
          "id": "o1",
          "modality": "语意",
          "text": "So what are the limitations of current AI systems? There are four things that are essential to intelligent behavior that they really don't do very well.",
          "start": 0.48,
          "end": 6.72,
          "source": "model_observation"
        },
        {
          "id": "o2",
          "modality": "画面",
          "text": "演讲者站立，面向观众，使用手势辅助表达",
          "start": 0,
          "end": 6.869375,
          "source": "model_observation"
        }
      ],
      "signals": [
        {
          "label": "专注",
          "family": "投入",
          "start": 0.48,
          "end": 6.72,
          "target": "讲解当前AI系统的局限性",
          "anchor": "So what are the limitati",
          "evidence": "持续进行主题陈述并配合手势",
          "refs": [
            "o1",
            "o2"
          ],
          "observations": [
            {
              "id": "o1",
              "modality": "语意",
              "text": "So what are the limitations of current AI systems? There are four things that are essential to intelligent behavior that they really don't do very well.",
              "start": 0.48,
              "end": 6.72,
              "source": "model_observation"
            },
            {
              "id": "o2",
              "modality": "画面",
              "text": "演讲者站立，面向观众，使用手势辅助表达",
              "start": 0,
              "end": 6.869375,
              "source": "model_observation"
            }
          ],
          "modalities": [
            "语意",
            "画面"
          ],
          "scope": "current_self",
          "basis": "combined",
          "confidence": 0.85,
          "tentative": false,
          "source": "fusion"
        }
      ],
      "behaviors": [
        {
          "start": 0.48,
          "end": 2.4,
          "label": "提问",
          "target": "当前AI系统的局限性是什么",
          "refs": [
            "o1"
          ]
        },
        {
          "start": 2.4,
          "end": 6.72,
          "label": "解释",
          "target": "当前AI系统在四个关键方面的不足",
          "refs": [
            "o1"
          ]
        }
      ],
      "consistency": [],
      "scene": "男子在论坛上演讲，讨论AI系统的局限性",
      "unknown": "缺少听众反应或后续内容以判断更复杂的互动状态",
      "unknownFamilies": [
        "情绪",
        "认知",
        "立场"
      ],
      "rejected": [
        {
          "label": "确信",
          "reason": "声音说明缺少对应声音依据"
        }
      ],
      "quality": {
        "audio": true,
        "video": true,
        "face": "absent",
        "faceSamples": 5,
        "clipping": false,
        "dark": false,
        "speech": null,
        "quiet": false
      },
      "partial": false,
      "speakerBound": true,
      "source": "model",
      "model": "qwen3.8-omni-flash",
      "latencyMs": 5184
    },
    {
      "id": "steve-jobs-interview",
      "duration": 12.538,
      "status": 200,
      "transcript": "competition that will attract the best people unfortunately the side effect of pushing out a lot of 46 year old teachers that lost their spirit you know 15 years ago and shouldn't be teaching right now",
      "segments": [
        {
          "start": 0,
          "end": 12.538,
          "text": "competition that will attract the best people unfortunately the side effect of pushing out a lot of 46 year old teachers that lost their spirit you know 15 years ago and shouldn't be teaching right now"
        }
      ],
      "observations": [
        {
          "id": "o1",
          "modality": "语意",
          "text": "unfortunately the side effect of pushing out a lot of 46 year old teachers that lost their spirit you know 15 years ago and shouldn't be teaching right now",
          "start": 2.5,
          "end": 11,
          "source": "model_observation"
        },
        {
          "id": "o2",
          "modality": "画面",
          "text": "说话时伴随手势，头部有轻微晃动",
          "start": 0,
          "end": 12.538,
          "source": "model_observation"
        }
      ],
      "signals": [
        {
          "label": "确信",
          "family": "认知",
          "start": 9,
          "end": 11,
          "target": "失去热情的教师不应继续任教",
          "anchor": "shouldn't be teaching ri",
          "evidence": "使用明确的否定情态动词表达坚定判断",
          "refs": [
            "o1"
          ],
          "observations": [
            {
              "id": "o1",
              "modality": "语意",
              "text": "unfortunately the side effect of pushing out a lot of 46 year old teachers that lost their spirit you know 15 years ago and shouldn't be teaching right now",
              "start": 2.5,
              "end": 11,
              "source": "model_observation"
            }
          ],
          "modalities": [
            "语意"
          ],
          "scope": "current_self",
          "basis": "explicit",
          "confidence": 0.85,
          "tentative": false,
          "source": "fusion"
        },
        {
          "label": "不满",
          "family": "情绪",
          "start": 2.5,
          "end": 11,
          "target": "部分失去热情却仍在任教的年长教师",
          "anchor": "lost their spirit... sho",
          "evidence": "对特定群体表达了负面评价和排斥态度",
          "refs": [
            "o1"
          ],
          "observations": [
            {
              "id": "o1",
              "modality": "语意",
              "text": "unfortunately the side effect of pushing out a lot of 46 year old teachers that lost their spirit you know 15 years ago and shouldn't be teaching right now",
              "start": 2.5,
              "end": 11,
              "source": "model_observation"
            }
          ],
          "modalities": [
            "语意"
          ],
          "scope": "current_self",
          "basis": "explicit",
          "confidence": 0.75,
          "tentative": false,
          "source": "fusion"
        }
      ],
      "behaviors": [],
      "consistency": [],
      "scene": "男子在带有NeXT标志的背景前讲话并做手势",
      "unknown": "缺少更多上下文以确认其整体情绪基调",
      "unknownFamilies": [
        "投入",
        "立场"
      ],
      "rejected": [],
      "quality": {
        "audio": true,
        "video": true,
        "face": "unavailable",
        "faceSamples": 2,
        "clipping": false,
        "dark": false,
        "speech": null,
        "quiet": false
      },
      "partial": false,
      "speakerBound": true,
      "source": "model",
      "model": "qwen3.8-omni-flash",
      "latencyMs": 5309
    },
    {
      "id": "elon-musk-wef",
      "duration": 4.013,
      "status": 200,
      "transcript": "Uh yeah, I mean I would say like I you know I did.",
      "segments": [
        {
          "start": 0,
          "end": 4.013,
          "text": "Uh yeah, I mean I would say like I you know I did."
        }
      ],
      "observations": [
        {
          "id": "o1",
          "modality": "语意",
          "text": "Uh yeah, I mean I would say like I you know I did.",
          "start": 0.64,
          "end": 3.8,
          "source": "model_observation"
        },
        {
          "id": "o2",
          "modality": "画面",
          "text": "说话期间多次闭眼，眉间收紧动作系数从0.14升至0.34后回落至0.28。",
          "start": 0.15,
          "end": 3.35,
          "source": "model_observation"
        }
      ],
      "signals": [],
      "behaviors": [
        {
          "start": 0.64,
          "end": 3.8,
          "label": "组织表达",
          "target": "回应前序问题",
          "refs": [
            "o1"
          ]
        }
      ],
      "consistency": [],
      "scene": "世界经济论坛现场发言",
      "unknown": "缺少明确上下文以判断具体立场或情绪指向",
      "unknownFamilies": [
        "情绪",
        "认知",
        "投入",
        "立场"
      ],
      "rejected": [],
      "quality": {
        "audio": true,
        "video": true,
        "face": "single",
        "faceSamples": 5,
        "clipping": false,
        "dark": false,
        "speech": null,
        "quiet": false
      },
      "partial": false,
      "speakerBound": true,
      "source": "model",
      "model": "qwen3.8-omni-flash",
      "latencyMs": 3642
    },
    {
      "id": "pep-guardiola-press",
      "duration": 4.999,
      "status": 200,
      "transcript": "switch of plays with four we could not control it Um but apart of that",
      "segments": [
        {
          "start": 0,
          "end": 4.999,
          "text": "switch of plays with four we could not control it Um but apart of that"
        }
      ],
      "observations": [
        {
          "id": "o1",
          "modality": "语意",
          "text": "switch of plays with four we could not control it... but apart of that",
          "start": 0,
          "end": 4.9,
          "source": "model_observation"
        },
        {
          "id": "o2",
          "modality": "声音",
          "text": "说话过程中出现停顿和填充词 'Um'",
          "start": 2.5,
          "end": 3.5,
          "source": "model_observation"
        }
      ],
      "signals": [],
      "behaviors": [
        {
          "start": 2.5,
          "end": 3.5,
          "label": "组织表达",
          "target": "关于比赛控制的陈述",
          "refs": [
            "o2"
          ]
        }
      ],
      "consistency": [],
      "scene": "男子在新闻发布会讲台前发言",
      "unknown": "缺少明确的情绪或认知状态线索，仅有组织表达的停顿",
      "unknownFamilies": [
        "情绪",
        "认知",
        "投入",
        "立场"
      ],
      "rejected": [],
      "quality": {
        "audio": true,
        "video": true,
        "face": "single",
        "faceSamples": 7,
        "clipping": false,
        "dark": false,
        "speech": null,
        "quiet": false
      },
      "partial": false,
      "speakerBound": true,
      "source": "model",
      "model": "qwen3.8-omni-flash",
      "latencyMs": 3379
    },
    {
      "id": "mark-zuckerberg-interview",
      "duration": 5.12,
      "status": 200,
      "transcript": "around the world and make progress in a way that um that that meets people's needs.",
      "segments": [
        {
          "start": 0,
          "end": 5.12,
          "text": "around the world and make progress in a way that um that that meets people's needs."
        }
      ],
      "observations": [
        {
          "id": "o1",
          "modality": "语意",
          "text": "around the world and make progress in a way that um that that meets people's needs.",
          "start": 0,
          "end": 4.5,
          "source": "model_observation"
        },
        {
          "id": "o2",
          "modality": "画面",
          "text": "说话时视线向下偏移，随后短暂闭眼并伴随轻微点头动作。",
          "start": 2.5,
          "end": 4.5,
          "source": "model_observation"
        }
      ],
      "signals": [],
      "behaviors": [
        {
          "start": 1.5,
          "end": 3.5,
          "label": "组织表达",
          "target": "关于满足人们需求的进展方式",
          "refs": [
            "o1"
          ]
        }
      ],
      "consistency": [],
      "scene": "男子面对镜头讲话，背景有另一人侧影",
      "unknown": "缺少明确的情绪线索（如愉悦、紧张等），无法判断其内心情感状态；仅有轻微的肢体和语音停顿表现。",
      "unknownFamilies": [
        "情绪",
        "认知",
        "投入",
        "立场"
      ],
      "rejected": [
        {
          "label": "组织表达",
          "reason": "缺少有效时间或可追溯依据"
        }
      ],
      "quality": {
        "audio": true,
        "video": true,
        "face": "single",
        "faceSamples": 7,
        "clipping": false,
        "dark": false,
        "speech": null,
        "quiet": false
      },
      "partial": false,
      "speakerBound": true,
      "source": "model",
      "model": "qwen3.8-omni-flash",
      "latencyMs": 4481
    }
  ],
  "phase": "完成",
  "passed": true
};
