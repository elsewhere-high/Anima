importScripts('/vendor/vision/vision_bundle.js');
let model,detector;
const cues=(categories)=>{
  const scores=Object.fromEntries(categories.map(c=>[c.categoryName,c.score]));
  const avg=(...keys)=>keys.reduce((a,k)=>a+(scores[k]||0),0)/keys.length;
  return [
    {name:'嘴角上扬',coefficient:avg('mouthSmileLeft','mouthSmileRight')},
    {name:'眉间收紧',coefficient:avg('browDownLeft','browDownRight')},
    {name:'抬眉',coefficient:avg('browInnerUp')},
    {name:'抿嘴',coefficient:avg('mouthPressLeft','mouthPressRight')},
    {name:'闭眼',coefficient:avg('eyeBlinkLeft','eyeBlinkRight')},
    {name:'张嘴',coefficient:avg('jawOpen')}
  ].map(c=>({...c,coefficient:Math.round(c.coefficient*1000)/1000}));
};
self.onmessage=async({data})=>{
  try {
    if(data.type==='init'){
      const files=await Vision.FilesetResolver.forVisionTasks('/vendor/vision/wasm');
      model=await Vision.FaceLandmarker.createFromOptions(files,{baseOptions:{modelAssetPath:'/models/face_landmarker.task',delegate:'CPU'},runningMode:'IMAGE',numFaces:2,outputFaceBlendshapes:true});
      // A face can remain visible when landmark fitting fails during a turn.
      // Optional research path: check presence on this same frame, with the
      // bundled detector and its default threshold. Never carry a lost face
      // forward in time or fabricate blendshape measurements.
      if(data.presenceDetection)detector=await Vision.FaceDetector.createFromOptions(files,{baseOptions:{modelAssetPath:'/models/face_detector.tflite',delegate:'CPU'},runningMode:'IMAGE'});
      self.postMessage({type:'ready'});return;
    }
    if(data.type==='frame'){
      if(!model)throw new Error('面部模型尚未就绪');
      const result=model.detect(data.image);
      const landmarkFaces=result.faceLandmarks.length,detectedFaces=detector?.detect(data.image).detections.length;
      const faces=Math.min(2,Math.max(landmarkFaces,detectedFaces||0));
      self.postMessage({type:'result',t:data.t,faces,landmarkFaces,detectedFaces,cues:faces===1&&landmarkFaces===1?cues(result.faceBlendshapes[0]?.categories||[]):[]});
    }
  }catch(error){self.postMessage({type:'error',message:'面部线索暂不可用，将继续使用原始声音和画面。',detail:String(error.message||error)});}
  finally{data.image?.close();}
};
