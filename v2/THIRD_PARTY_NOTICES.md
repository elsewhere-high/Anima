# Third-party model and data notices

This delivery adapts the following third-party resources. Their original license
files are retained at the paths below. These notices do not grant rights beyond
the rights provided by the original licensors.

## Qwen3.5-2B

- Creator: Qwen team / Alibaba.
- Source: https://huggingface.co/Qwen/Qwen3.5-2B
- Revision: `15852e8c16360a2fea060d615a32b45270f8a8fc`.
- License: Apache License 2.0, retained in `models/qwen35_2B/LICENSE`.
- Modifications: only the text backbone is used; trained LoRA adapters and eight
  classification/transition heads are separate; the CPU export merges the
  adapters and quantizes linear operators. No original vision performance claim
  carries over to this text-only component.

## CPED

- Creators: Yirong Chen, Weiquan Fan, Xiaofen Xing, Jianxin Pang, Minlie Huang,
  Wenjing Han, Qianfeng Tie, Xiangmin Xu.
- Work: CPED: A Large-Scale Chinese Personalized and Emotional Dialogue Dataset
  for Conversational AI (2022), https://arxiv.org/abs/2205.14727.
- Source: https://github.com/scutcyr/CPED
- Repository revision: `1e4b81c28a123f22387e06664f37e5dc9322380f`.
- Repository license: Apache License 2.0, retained in `data/raw/cped/LICENSE`.
- Modifications: official split subsets, fixed sampling, dialogue context
  formatting, relative speaker placeholders, turn-state and next-turn labels,
  exact-input deduplication and observational transition tables. Demographic and
  personality annotations are excluded from model input and supervision.
- The original material comes from television dialogue; underlying third-party
  television rights have not been independently cleared by this project.

## MASSIVE zh-CN

- Copyright Amazon.com Inc. or its affiliates.
- Source: https://huggingface.co/datasets/AmazonScience/massive
- License: Creative Commons Attribution 4.0 International,
  https://creativecommons.org/licenses/by/4.0/.
- Full original license retained in `data/raw/massive/LICENSE`.
- Parquet revision: `ed58ac423a2f4121720918bf5301577edce4ffd3`.
- Modifications: use of the zh-CN locale, exact-input duplicate removal, prompt
  formatting, and selection of intent annotations. Task-to-robot mappings are
  this project's engineering policy, not original MASSIVE human-robot labels.

## CrossWOZ

- Creators: Qi Zhu, Kaili Huang, Zheng Zhang, Xiaoyan Zhu, Minlie Huang.
- Work: CrossWOZ: A Large-Scale Chinese Cross-Domain Task-Oriented Dialogue
  Dataset, Transactions of the Association for Computational Linguistics, 2020.
- Source: https://github.com/thu-coai/CrossWOZ
- Revision: `df82c9fdff91b9b130f2d6b89110d3870ba6260e`.
- License: Apache License 2.0, retained in `data/raw/crosswoz/LICENSE`.
- Modifications: deterministic official-split subsampling and current-user
  domain extraction from dialog acts. Future goals are not model input.

EmotionTalk, SocialDial and COLD are research references only and are not part of
the training data. The project does not imply endorsement by the original
authors. Detailed source URLs, byte counts and hashes are in
`data/provenance.json`. Software dependencies retain their respective licenses;
the installed version inventory is in `requirements.lock.txt`.
