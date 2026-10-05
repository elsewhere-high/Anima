"""Static report figures from actual evaluation and training logs."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'deliverables';OUT.mkdir(exist_ok=True)
font=Path('C:/Windows/Fonts/msyh.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams['axes.unicode_minus']=False
state=json.loads((ROOT/'reports/current_state_evaluation.json').read_text(encoding='utf-8'))
if state.get('metrics'):
    keys=[('cped_state','emotion'),('cped_state','dialog_act'),('cped_state','sentiment'),('chinese_medd','emotion')]
    names=['CPED\n情绪13类','CPED\n对话行为19类','CPED\n正负情感3类','中文MEDD\n六类真值']
    fig,axes=plt.subplots(1,2,figsize=(9.5,3.7),layout='constrained')
    for ax,key,title in zip(axes,['accuracy','macro_f1'],['固定测试准确率','固定测试宏 F1（全输出类别）']):
        x=np.arange(4);old=[100*state['metrics'][s][k]['original'][key] for s,k in keys];new=[100*state['metrics'][s][k]['trained'][key] for s,k in keys]
        a=ax.bar(x-.18,old,.34,color='#9CA3AF',label='原版');b=ax.bar(x+.18,new,.34,color='#275D86',label='V4 候选')
        ax.bar_label(a,fmt='%.1f',fontsize=9,padding=2);ax.bar_label(b,fmt='%.1f',fontsize=9,padding=2)
        ax.set(xticks=x,xticklabels=names,ylim=(0,100),ylabel='%',title=title);ax.tick_params(axis='x',labelsize=9);ax.legend(frameon=False,fontsize=9)
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.savefig(OUT/'fixed_test.png',dpi=220);plt.close(fig)
events=[json.loads(line) for line in (ROOT/'runs/current_state_lora/events.jsonl').read_text().splitlines()]
train=[e for e in events if e['type']=='train'];val=[e for e in events if e['type'] in ['initial_validation','validation']]
fig,axes=plt.subplots(1,2,figsize=(11,3.4),layout='constrained')
axes[0].plot([e['step'] for e in train],[e['loss'] for e in train],color='#275D86');axes[0].set(title='当前状态训练损失',xlabel='优化步骤',ylabel='加权损失',ylim=(0,None))
for key,name,color in [('emotion','CPED 情绪','#275D86'),('dialog_act','CPED 对话行为','#217C6F')]:
    axes[1].plot([e['step'] for e in val],[100*e['metrics']['cped_state'][key]['macro_f1'] for e in val],marker='o',ms=3,label=name,color=color)
axes[1].set(title='状态验证宏 F1',xlabel='优化步骤',ylabel='%',ylim=(0,100));axes[1].legend(frameon=False,fontsize=8)
for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2)
fig.savefig(OUT/'training_curves.png',dpi=220);plt.close(fig)
if (ROOT/'runs/dialogue_repair_v2/selection.json').exists():
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    for ax,run,title in zip(axes,['dialogue_sft','dialogue_repair_v2'],['第一阶段：回复微调','第二阶段：上下文与信息边界修复']):
        events=[json.loads(line) for line in (ROOT/'runs'/run/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        val=[e for e in events if e['type'] in ['initial_validation','validation']]
        selection=json.loads((ROOT/'runs'/run/'selection.json').read_text(encoding='utf-8'))
        for source,name,color in [('opens2s_zh','OpenS2S','#275D86'),('oasst2_zh','OASST2','#217C6F'),('grounded_authored','自编场景','#AA6635')]:
            rows=[e for e in val if source in e['metrics']]
            if rows:ax.plot([e.get('epoch',0) for e in rows],[e['metrics'][source]['token_nll'] for e in rows],marker='o',ms=4,label=name,color=color)
        if selection['selected']:ax.axvline(selection['selected']['epoch'],color='#9CA3AF',ls='--',label='选中轮次')
        ax.set(title=title,xlabel='完成轮数（0为训练前）',ylabel='验证 token NLL（越低越好）',ylim=(0,3.5))
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,fontsize=8)
    fig.savefig(OUT/'dialogue_training_curves.png',dpi=220);plt.close(fig)
print('Saved actual-evidence figures')
