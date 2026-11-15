/* ECG-CLASS-1：已准备float32张量的PS候选管理层；未接AXI/新QRS/板卡。 */
#ifndef ECG_CLASSIFICATION_H
#define ECG_CLASSIFICATION_H
#include <stdint.h>
#define ECG_CLASS_CAPACITY 4
enum { ECG_CLASS_OK=0, ECG_CLASS_NO_MODEL=1, ECG_CLASS_MISSING_RR=2,
       ECG_CLASS_INVALID_INPUT=3, ECG_CLASS_WINDOW_INCOMPLETE=4,
       ECG_CLASS_TIMEOUT=5, ECG_CLASS_BACKEND_ERROR=6, ECG_CLASS_CANCELLED=7 };
enum { ECG_CLASS_ACCEPTED=0, ECG_CLASS_BUSY=1, ECG_CLASS_BAD=-1 };
typedef struct {
    uint32_t generation, beat_id, position, rr_samples, sampling_hz, ready_at, input_status;
    float waveform[128], rr[3];
} EcgClassRequest;
typedef struct {
    EcgClassRequest request;
    uint32_t status, valid;
    int32_t class_id;
} EcgClassResult;
typedef struct { EcgClassRequest request; uint64_t deadline; } EcgClassSlot;
typedef struct {
    uint32_t generation, last_id, head, used, active;
    uint64_t now, timeout_ms;
    uint8_t model_sha256[32];
    EcgClassSlot queue[ECG_CLASS_CAPACITY], flight;
} EcgClassState;
int ecg_class_init(EcgClassState *,uint32_t,const uint8_t[32],uint64_t);
int ecg_class_submit(EcgClassState *,const EcgClassRequest *,uint64_t);
int ecg_class_take(EcgClassState *,EcgClassRequest *,uint64_t);
int ecg_class_cancel(EcgClassState *,EcgClassResult *,uint64_t);
int ecg_class_expire(EcgClassState *,EcgClassResult *,uint64_t);
int ecg_class_complete(EcgClassState *,uint32_t,uint32_t,uint32_t,int32_t,EcgClassResult *,uint64_t);
/* 仅RR训练参数变换，不是波形重采样，也不替代完整QRS移植。 */
int ecg_class_normalize_rr(const float[3],const float[3],const float[3],float[3]);
#endif
