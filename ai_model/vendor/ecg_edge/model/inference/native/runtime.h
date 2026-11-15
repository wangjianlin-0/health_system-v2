/* 冻结研究26/360Hz的C移植候选。来源/许可见README；不是新调参算法。 */
#ifndef ECG_RUNTIME_H
#define ECG_RUNTIME_H
#include <stdint.h>
#include <stddef.h>
typedef struct EcgRuntime EcgRuntime;
typedef struct {uint32_t emitted,position,rr;} EcgRuntimeEvent;
size_t ecg_runtime_size(void);
void ecg_runtime_init(EcgRuntime *);
/* 连续4096单位/mV int16；最多32个事件，错误为负，不补尾部。 */
int ecg_runtime_push(EcgRuntime *,int16_t,EcgRuntimeEvent out[32]);
int ecg_runtime_pending(const EcgRuntime *);
#endif
