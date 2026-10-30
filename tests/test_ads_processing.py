import numpy as np
import pytest
from signal_processing.python.ecg_preprocessing import _ads_raw_to_mv, parse_csv, process

def test_encoding_endpoints():
    assert _ads_raw_to_mv(0) == pytest.approx(-2420/6)
    assert _ads_raw_to_mv(8388608) == 0
    assert _ads_raw_to_mv(16777215) == pytest.approx((8388607)*2420/(6*8388608))
    for value in [-1,16777216,1.5,float('nan')]:
        with pytest.raises(ValueError): _ads_raw_to_mv(value)

def test_unknown_scale_and_missing_samples():
    with pytest.raises(ValueError): parse_csv('ecg_filtered\n100\n',500)
    with pytest.raises(ValueError): parse_csv('timestamp(s),ecg_raw\n0,8388608\n0.004,8388608',500)

def test_filter_preserves_model_input_and_attenuates_mains():
    t=np.arange(10000)/500
    values=20+np.sin(2*np.pi*5*t)+.5*np.sin(2*np.pi*50*t)
    r=process({'samples':values.tolist(),'sample_rate_hz':500,'unit':'mV'})
    assert r['waveform']==values.tolist()
    y=np.array(r['waveform_processed_mV'])[1000:-1000]
    tt=t[1000:-1000]
    amplitude=lambda hz: abs(2*np.mean(y*np.exp(-2j*np.pi*hz*tt)))
    assert .9<amplitude(5)<1.1
    assert amplitude(50)<.01
    assert abs(np.mean(y))<.01
