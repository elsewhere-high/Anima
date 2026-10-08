export const SOCIAL_SIGNALS=[
  ['agreement','赞同','立场','Alignment with a position, proposal, or understanding.'],
  ['disagreement','反对','立场','Actively rejecting or challenging a position or proposal.'],
  ['skepticism','怀疑','立场','Questioning the credibility of a claim, seeking justification.'],
  ['confidence','表达自信','认知','Firm, assured delivery: clear conviction, steady purposeful expression. Not factual correctness.'],
  ['hesitation','犹豫','认知','Observable withholding or difficulty getting a response out: searching for wording, false starts, disrupted commitment.'],
  ['frustration','挫败','情绪','Irritation or mounting tension about something blocked, unsuccessful, or unsatisfactory.'],
  ['interest','兴趣','投入','Positive curiosity or active desire to explore the particular topic.'],
  ['uncertainty','不确定','认知','Doubt about one’s knowledge, judgment, or decision. Distinct from merely searching for a word.'],
  ['confusion','困惑','认知','Difficulty understanding what is being discussed.'],
  ['stress','压力','情绪','Visible or audible strain under perceived demands or pressure.']
].map(([code,label,family,definition])=>({code,label,family,definition}));

export const LOCAL_SIGNALS = [
  ...['愉悦','低落','惊讶','害怕','厌恶','生气','轻蔑'].map(x=>({label:x+'表情',family:'情绪'})),
  ...['愉悦','低落','惊讶','害怕','厌恶','生气'].map(x=>({label:x+'语调',family:'情绪'}))
];
export const DISPLAY_SIGNALS=[...SOCIAL_SIGNALS,...LOCAL_SIGNALS];
