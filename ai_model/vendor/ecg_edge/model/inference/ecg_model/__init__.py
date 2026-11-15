"""500Hz单导联心电的研究用离线整段推理；不包含训练。"""
import os
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_key]='4'

from .pipeline import infer_mv, infer_codes

__all__=['infer_mv','infer_codes']
