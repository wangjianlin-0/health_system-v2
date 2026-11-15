"""只读核研究交接包的文件和合成数值；不训练、不读取心电数据。"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np

def probability(x,model):
    raw=np.repeat(model['baseline'],len(x),axis=0);ids=np.arange(len(x))
    for stage in range(64):
        for label in range(3):
            nodes=model[f'tree_{stage}_{label}'];assert not nodes['is_categorical'].any();at=np.zeros(len(x),np.int64)
            for _ in range(int(model['max_depth'])+1):
                active=nodes['is_leaf'][at]==0
                if not active.any():break
                old=at[active];at[active]=np.where(x[ids[active],nodes['feature_idx'][old]]<=nodes['num_threshold'][old],nodes['left'][old],nodes['right'][old])
            assert nodes['is_leaf'][at].all();raw[:,label]+=nodes['value'][at]
    raw-=raw.max(1,keepdims=True);np.exp(raw,out=raw);return raw/raw.sum(1,keepdims=True)
