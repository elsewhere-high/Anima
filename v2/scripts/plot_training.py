from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parents[1]
font=Path('C:/Windows/Fonts/msyh.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams['axes.unicode_minus']=False
events=[json.loads(line) for line in (ROOT/'reports/train_events.jsonl').read_text().splitlines()]
train=[r for r in events if r['type']=='train'];steps=np.array([r['step'] for r in train]);loss=np.array([r['loss'] for r in train]);memory=np.array([r['peak_vram_mib']/1024 for r in train])
fig,axes=plt.subplots(1,2,figsize=(10.4,3.25),layout='constrained')
axes[0].plot(steps,loss,color='#203864',lw=1.6);axes[0].set(xlabel='优化步骤',ylabel='加权多任务损失',title='每 50 步的平均训练损失',ylim=(0,max(loss)*1.12))
axes[1].plot(steps,memory,color='#16766A',lw=1.7);axes[1].axhline(8,color='#A54842',ls='--',lw=1,label='8 GiB 显存容量');axes[1].set(xlabel='优化步骤',ylabel='PyTorch 峰值分配显存 GiB',title='本机训练显存',ylim=(0,8.8));axes[1].legend(loc='lower right',frameon=False,fontsize=8)
for ax in axes:
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#D9D9D9',lw=.6);ax.set_axisbelow(True)
    for r in events:
        if r['type']=='validation' and r['epoch']==1:ax.axvline(r['step'],color='#999999',ls=':',lw=1)
fig.savefig(ROOT/'reports/training_curves.png',dpi=200,bbox_inches='tight');plt.close(fig)
print('Training figure saved')
