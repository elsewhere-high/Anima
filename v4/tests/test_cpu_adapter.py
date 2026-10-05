import torch
from social_v4.cpu_model import RoutedLinear

def test_dynamic_quantized_base_with_switchable_lora():
    torch.manual_seed(7)
    base=torch.nn.Linear(7,9).eval();base.qconfig=torch.ao.quantization.default_dynamic_qconfig
    quantized=torch.ao.nn.quantized.dynamic.Linear.from_float(base)
    routed=RoutedLinear(quantized)
    a=torch.randn(2,7);b=torch.randn(9,2);c=torch.randn(2,7);d=torch.randn(9,2)
    routed.add('default',a,b,2.);routed.add('dialogue',c,d,3.)
    x=torch.randn(3,4,7)
    routed.active='base';torch.testing.assert_close(routed(x),quantized(x))
    routed.active='default';torch.testing.assert_close(routed(x),quantized(x)+(x@a.T)@b.T*2.)
    routed.active='dialogue';torch.testing.assert_close(routed(x),quantized(x)+(x@c.T)@d.T*3.)
    routed.active='default';torch.testing.assert_close(routed(x),quantized(x)+(x@a.T)@b.T*2.)


def test_quantized_qwen_recurrence_attention_and_cache_run_on_cpu():
    from transformers import Qwen3_5TextConfig,Qwen3_5TextModel
    from social_v4.cpu_model import RoutedBackbone
    from social_world_zh.quantized import replace_linears,FloatOutputEmbedding
    cfg=Qwen3_5TextConfig(vocab_size=128,hidden_size=64,intermediate_size=128,num_hidden_layers=2,num_attention_heads=4,num_key_value_heads=2,head_dim=16,linear_num_key_heads=2,linear_num_value_heads=2,linear_key_head_dim=16,linear_value_head_dim=16,layer_types=['linear_attention','full_attention'])
    cfg._attn_implementation='sdpa'
    model=Qwen3_5TextModel(cfg).eval();model.requires_grad_(False)
    replace_linears(model,True);model.embed_tokens.weight.data=model.embed_tokens.weight.data.bfloat16();model.embed_tokens.__class__=FloatOutputEmbedding
    wrapper=RoutedBackbone(model)
    with torch.inference_mode():
        first=wrapper(input_ids=torch.tensor([[1,2,3]]),use_cache=True)
        second=wrapper(input_ids=torch.tensor([[4]]),past_key_values=first.past_key_values,use_cache=True)
        assert second.last_hidden_state.shape==(1,1,64)
        scores=torch.nn.functional.linear(second.last_hidden_state[:,-1].bfloat16(),wrapper.get_input_embeddings().weight)
        assert scores.shape==(1,128) and torch.isfinite(scores).all()
