"""Coarse CPED sentiment, explicitly derived from the 13-way emotion distribution."""
GROUPS={'negative':['anger','negative-other','depress','worried','astonished','sadness','fear','disgust'],'neutral':['neutral'],'positive':['relaxed','positive-other','happy','grateful']}
ZH={'negative':'负向','neutral':'中性','positive':'正向','unknown':'未知'}
def coarse_affect(emotion):
    distribution=emotion.get('distribution',{})
    if not distribution:return {'label':'unknown','label_zh':'未知','confidence':0.,'distribution':{},'source':'not_evaluated'}
    p={k:sum(distribution.get(e,0.) for e in labels) for k,labels in GROUPS.items()}
    label=max(p,key=p.get)
    return {'label':label,'label_zh':ZH[label],'confidence':p[label],'distribution':p,'source':'derived_cped_emotion_groups_not_independent_head'}
