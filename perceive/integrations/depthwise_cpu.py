"""Equivalent depthwise convolution for short CPU speech sequences.

PyTorch's grouped Conv1d path on this Mac spends most ASR time launching tiny
per-channel convolutions. This vectorized contraction uses the same weights.
Enable only for depthwise, zero-padding Conv1d; no architecture or training change.
"""
import types
import torch
import torch.nn.functional as F

def forward(module,x):
    kernel=module.weight.shape[-1];dilation=module.dilation[0];stride=module.stride[0]
    if module.padding[0]:x=F.pad(x,(module.padding[0],module.padding[0]))
    windows=x.unfold(-1,dilation*(kernel-1)+1,stride)[...,::dilation]
    output=torch.einsum('bctk,ck->bct',windows,module.weight[:,0])
    if module.bias is not None:output=output+module.bias[None,:,None]
    return output

def install(model):
    changed=0
    for module in model.modules():
        if isinstance(module,torch.nn.Conv1d) and module.groups==module.in_channels==module.out_channels and module.padding_mode=='zeros':
            module.forward=types.MethodType(forward,module);changed+=1
    return changed
