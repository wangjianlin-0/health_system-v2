"""可训练轻量CNN：MF-CNN与残差Conv1D公开结构思路的独立改编。

来源与差异见docs/cnn_trainable.md；不复制第三方源码/权重。
"""
import torch
from torch import nn


def waveform_channels(x,feature):
    derivative=torch.diff(x,dim=-1,prepend=x[:,:1])
    if feature=='raw':
        return x[:,None,:]
    if feature=='derivative':
        return derivative[:,None,:]
    if feature=='both':
        return torch.stack([x,derivative],dim=1)
    raise ValueError('未定义输入特征')


class MatchedCnn(nn.Module):
    """保留单Conv1D/BN/tanh/GMP及共享RR分支，卷积权重全部可训练。"""
    def __init__(self,feature='derivative',width=12):
        super().__init__();self.feature=feature
        inputs=2 if feature=='both' else 1
        self.wave=nn.Sequential(nn.ConstantPad1d((15,16),0),nn.Conv1d(inputs,width,32),nn.BatchNorm1d(width),nn.Tanh(),nn.AdaptiveMaxPool1d(1))
        self.rr=nn.Sequential(nn.Linear(1,32),nn.ReLU(),nn.Linear(32,16),nn.ReLU(),nn.Linear(16,8),nn.ReLU())
        self.head=nn.Linear(width+24,4)

    def forward(self,x,rr):
        wave=self.wave(waveform_channels(x,self.feature)).flatten(1)
        rhythm=self.rr(rr[:,:,None]).flatten(1)
        return self.head(torch.cat([wave,rhythm],dim=1))


class ResidualBlock(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.body=nn.Sequential(nn.Conv1d(width,width,5,padding=2,bias=False),nn.BatchNorm1d(width),nn.ReLU(),
                                nn.Conv1d(width,width,5,padding=2,bias=False),nn.BatchNorm1d(width))
        self.activation=nn.ReLU();self.pool=nn.MaxPool1d(2)

    def forward(self,x):
        return self.pool(self.activation(x+self.body(x)))


class ResidualCnn(nn.Module):
    """参考心拍残差卷积结构，缩小为三块，增加仅历史RR分支。"""
    def __init__(self,feature='raw',width=16):
        super().__init__();self.feature=feature
        inputs=2 if feature=='both' else 1
        self.wave=nn.Sequential(nn.Conv1d(inputs,width,7,padding=3,bias=False),nn.BatchNorm1d(width),nn.ReLU(),
                                ResidualBlock(width),ResidualBlock(width),ResidualBlock(width))
        self.rr=nn.Sequential(nn.Linear(3,8),nn.ReLU())
        self.head=nn.Sequential(nn.Linear(width*8+8,32),nn.ReLU(),nn.Dropout(.1),nn.Linear(32,4))

    def forward(self,x,rr):
        wave=self.wave(waveform_channels(x,self.feature)).flatten(1)
        return self.head(torch.cat([wave,self.rr(rr)],dim=1))


def create_model(config):
    cls={'mf':MatchedCnn,'residual':ResidualCnn}[config['family']]
    model=cls(feature=config['feature'],width=config['width'])
    model.input_samples=config.get('input_samples',64)
    if config['family']=='residual' and model.input_samples!=64:
        model.wave.add_module('context_pool',nn.AdaptiveMaxPool1d(8))
    return model


def budget(model):
    """只统计Conv/Linear的推理MAC，不冒充综合资源或含预处理的总耗时。"""
    macs=[];hooks=[]
    def count(module,inputs,output):
        if isinstance(module,nn.Conv1d):
            macs.append(output.numel()*module.in_channels*module.kernel_size[0]//module.groups)
        else:
            macs.append(output.numel()*module.in_features)
    for m in model.modules():
        if isinstance(m,(nn.Conv1d,nn.Linear)):
            hooks.append(m.register_forward_hook(count))
    training=model.training;model.eval()
    with torch.no_grad():
        model(torch.zeros(1,getattr(model,'input_samples',64)),torch.zeros(1,3))
    for h in hooks:
        h.remove()
    model.train(training)
    return {'trainable_parameters':sum(p.numel() for p in model.parameters()),'conv_linear_macs_per_beat':sum(macs),
            'scope':'FP32算术预算；不含重采样、归一化、BN、激活、池化、传输；不是7020实测/综合资源'}
