"""Research-only inference adapter for the released Nano-EmoX checkpoint.

The upstream training runner imports unrelated CUDA/video/training packages.
Load only its model modules. No parameters are trained and no remote Python
model code is loaded. Results are not wired into Anima's live labels.
"""
from pathlib import Path
import ast
import contextlib
import importlib
import sys
import types

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT/'vendor/nano-emox'
WEIGHTS = ROOT/'models/nano-emox'


def import_model():
    for name, path in [('nano_emox',VENDOR),('nano_emox.models',VENDOR/'models'),('nano_emox.common',VENDOR/'common')]:
        if name not in sys.modules:
            package = types.ModuleType(name)
            package.__path__ = [str(path)]
            package.__file__ = str(path/'__init__.py')
            sys.modules[name] = package
    from nano_emox.common.registry import registry
    for name, path in [('library_root',VENDOR),('repo_root',VENDOR.parent),('cache_root',WEIGHTS/'cache')]:
        registry.register_path(name,str(path))
    # ImageBind is an unused alternative encoder. Omitting its import avoids
    # installing CUDA-oriented video training packages on this Mac.
    module_name = 'nano_emox.models.encoder'
    if module_name not in sys.modules:
        path = VENDOR/'models/encoder.py'
        tree = ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
        tree.body = [node for node in tree.body if not (isinstance(node,ast.ImportFrom) and (node.module or '').startswith('nano_emox.models.ImageBind'))]
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = 'nano_emox.models'
        sys.modules[module_name] = module
        exec(compile(tree,str(path),'exec'),module.__dict__)
    sys.modules['nano_emox.models'].BaseModel = importlib.import_module('nano_emox.models.base_model').BaseModel
    return importlib.import_module('nano_emox.models.nano_emox').NanoEmoX


class NanoEmox:
    def __init__(self, device='mps'):
        import torch
        import yaml
        from transformers import BertConfig
        cls = import_model()
        from nano_emox import config
        from nano_emox.models.blip2 import Blip2Base
        from nano_emox.models import faceXencoder
        # FaceX includes the complete backbone and fusion weights. Avoid first
        # downloading ImageNet weights that the released checkpoint overwrites.
        # Reject any missing frozen parameter, rather than silently running it
        # randomly as upstream strict=False otherwise permits.
        original_swin = faceXencoder.swin_b
        original_face_load = faceXencoder.FaceXFormerEncoderOnly.load_state_dict
        face_report = {}
        faceXencoder.swin_b = lambda **kwargs: original_swin(weights=None)
        def checked_face_load(module, state, **kwargs):
            loaded = original_face_load(module, state, **kwargs)
            missing = [name for name,_ in module.named_parameters() if name in loaded.missing_keys]
            face_report.update(missingParameters=missing, extraUnusedHeadTensors=len(loaded.unexpected_keys), loadedTensors=len(state))
            if missing:raise RuntimeError('Incomplete frozen FaceX checkpoint: '+str(missing))
            return loaded
        faceXencoder.FaceXFormerEncoderOnly.load_state_dict = checked_face_load
        config.PATH_TO_LLM['Qwen25'] = str(WEIGHTS/'qwen')
        config.PATH_TO_VISUAL['CLIP_VIT_LARGE'] = str(WEIGHTS/'clip')
        config.PATH_TO_AUDIO['HUBERT_LARGE'] = str(WEIGHTS/'hubert')
        config.PATH_TO_FACIAL['FaceXFormer'] = str(WEIGHTS/'face/ckpts/model.pt')
        cfg = yaml.safe_load((VENDOR/'configs/phase3.yaml').read_text(encoding='utf-8-sig'))['model']
        cfg['ckpt'] = cfg['ckpt_2'] = None
        original = BertConfig.from_pretrained
        BertConfig.from_pretrained = classmethod(lambda _cls,path,*args,**kwargs:original(str(WEIGHTS/'bert') if path=='bert-base-uncased' else path,*args,**kwargs))
        try:
            model = cls.from_config(cfg)
        finally:
            BertConfig.from_pretrained = original
            faceXencoder.swin_b = original_swin
            faceXencoder.FaceXFormerEncoderOnly.load_state_dict = original_face_load
        checkpoint = torch.load(WEIGHTS/'adapters/checkpoint_000060_loss_0.285.pth',map_location='cpu',weights_only=True,mmap=True)
        state = checkpoint['model']
        loaded = model.load_state_dict(state,strict=False)
        # Frozen base encoders/LLM are legitimately absent. Every learned
        # parameter must be present; never run a partially random adapter.
        missing_learned = [name for name,p in model.named_parameters() if p.requires_grad and name in loaded.missing_keys]
        self.load_report = {'unexpected':loaded.unexpected_keys,'missingLearned':missing_learned,'missingFrozenCount':len(loaded.missing_keys),'loadedTensors':len(state),'faceCheckpoint':face_report}
        if missing_learned or loaded.unexpected_keys:
            raise RuntimeError('Checkpoint mismatch: '+str(self.load_report))
        del checkpoint,state
        for p in model.parameters():p.requires_grad_(False)
        # Upstream has a CUDA autocast helper. Keep the original float32
        # perception modules and float16 LLM, explicitly converting only their
        # boundary embeddings on Metal.
        Blip2Base.maybe_autocast = lambda self,dtype=torch.float16:contextlib.nullcontext()
        self.model = model.to(device)
        # Upstream overrides train() on the frozen face module; explicitly
        # disable its stochastic depth and dropout recursively for inference.
        self.model.eval()
        for module in self.model.modules():module.training=False
        self.device = device
        self.config = config
        self.tokenizer = model.llama_tokenizer

    def infer(self, frames, pcm, transcript='',max_tokens=96):
        import numpy as np
        import torch
        from PIL import Image
        m = self.model
        started = __import__('time').perf_counter()
        # Eight causal samples from the supplied prefix, matching training's
        # frame count. Never read frames or sound beyond this caller's prefix.
        selected = [frames[int(i)] for i in np.linspace(0,len(frames)-1,8)]
        raw = torch.from_numpy(np.stack([np.array(Image.fromarray(f).resize((224,224))) for f in selected])).permute(3,0,1,2).unsqueeze(0)
        wave = np.asarray(pcm,dtype=np.float32)
        if len(wave)<32000:wave=np.pad(wave,(0,32000-len(wave)))
        chunks = np.stack([wave[int(i):int(i)+32000] for i in np.linspace(0,len(wave)-32000,8)])
        with torch.inference_mode():
            # Feature extractors accept CPU arrays; tensors for learned modules
            # move to Metal after normalization, retaining upstream operations.
            visual = m.visual_encoder
            pixels = visual.processor(images=[Image.fromarray(f) for f in selected],return_tensors='pt')['pixel_values'].to(self.device)
            out = visual.model.vision_model(pixel_values=pixels,output_hidden_states=True)
            v,v_multi = visual.feature_select(out,1,8)
            acoustic = m.acoustic_encoder
            values = acoustic.feature_extractor(list(chunks),sampling_rate=16000,return_tensors='pt').input_values.to(self.device)
            out = acoustic.model(values,output_hidden_states=True).hidden_states
            a = torch.stack(out[-4:]).mean(0).mean(1).unsqueeze(0)
            a_multi = acoustic.feature_select(out,1,8)
            m.video_multi_scale_features,m.audio_multi_scale_features = v_multi,a_multi
            def query(value,positions,tokens,qformer,project):
                value = value + positions(torch.arange(value.shape[1],device=self.device)).unsqueeze(0)
                hidden = qformer.bert(query_embeds=tokens.expand(1,-1,-1),encoder_hidden_states=value,encoder_attention_mask=torch.ones(value.shape[:-1],dtype=torch.long,device=self.device),return_dict=True).last_hidden_state
                return project(hidden)
            frame = query(v,m.video_frame_position_embedding,m.video_query_tokens,m.video_Qformer,m.video_proj)
            audio = query(a,m.audio_position_embedding,m.audio_query_tokens,m.audio_Qformer,m.audio_llama_proj)
            # Follow the training forward() face path (four face tokens). The
            # upstream generic inference Chat class still assumes 32 CLIP face
            # tokens, which is incompatible with this released architecture.
            face = m.facial_encoder(raw.permute(0,2,1,3,4).to(self.device,dtype=torch.float32))
            _,multi = m.encode_multi_multiscale()
            prompt = '###Human: The audio and video merged info is: <Multi><MultiHere></Multi>. The audio content is as follows: <Audio><AudioHere></Audio>. Meanwhile, We uniformly extract facial informations from video: <Video><FaceHere></Video>. Meanwhile, we uniformly sample raw frames from the video: <Video><FrameHere></Video>. '+f'The subtitle of this video is: <Subtitle>{transcript}</Subtitle>. Now, please answer my question based on all the provided information. [Recogn_OV] Please recognize all possible emotional states of the character. ###Assistant: '
            slots = {'<MultiHere>':multi,'<AudioHere>':audio,'<FaceHere>':face,'<FrameHere>':frame}
            for name,value in slots.items():prompt=prompt.replace(name,name*value.shape[1])
            ids = self.tokenizer(prompt,return_tensors='pt',add_special_tokens=False).input_ids.to(self.device)
            # Training's collater prepends BOS even for Qwen's custom template.
            ids = torch.cat([torch.tensor([[self.tokenizer.bos_token_id]],device=self.device),ids],dim=1)
            masked=ids.clone()
            for name in slots:masked[ids==self.tokenizer.convert_tokens_to_ids(name)]=0
            embeds=m.llama_model.get_input_embeddings()(masked)
            for name,value in slots.items():
                indices=ids[0]==self.tokenizer.convert_tokens_to_ids(name)
                assert int(indices.sum())==value.shape[1]
                embeds[0,indices]=value[0].to(embeds.dtype)
            from hashlib import sha256
            features={name:sha256(value.float().cpu().numpy().tobytes()).hexdigest() for name,value in {'video':v,'audio':a,'face':face,'multi':multi,'embeds':embeds}.items()}
            if self.device=='mps':torch.mps.synchronize()
            encoded=__import__('time').perf_counter()
            result=m.llama_model.generate(inputs_embeds=embeds,attention_mask=torch.ones(ids.shape,dtype=torch.long,device=self.device),do_sample=False,max_new_tokens=max_tokens,pad_token_id=self.tokenizer.eos_token_id)
            if self.device=='mps':torch.mps.synchronize()
        finished=__import__('time').perf_counter()
        return {'text':self.tokenizer.decode(result[0],skip_special_tokens=True).split('###')[0].strip(),'encodeMs':round((encoded-started)*1000),'decodeMs':round((finished-encoded)*1000),'totalMs':round((finished-started)*1000),'tokens':len(result[0]),'featureHashes':features}
