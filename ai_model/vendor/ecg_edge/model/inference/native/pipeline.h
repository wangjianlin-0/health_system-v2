#ifndef ECG_PIPELINE_H
#define ECG_PIPELINE_H
#include "classification.h"
#include "runtime.h"
typedef struct EcgPipeline EcgPipeline;
size_t ecg_pipeline_size(void);
/* 同一权重的RR参数；均为float32，模型切换必须新会话重新init。 */
int ecg_pipeline_init(EcgPipeline *,uint32_t,const float[3],const float[3]);
int ecg_pipeline_push(EcgPipeline *,int16_t,uint32_t,EcgClassRequest out[32]);
/* 停流时不补样：将尚未形成完整窗的拍以WINDOW_INCOMPLETE输出。 */
int ecg_pipeline_finish(EcgPipeline *,EcgClassRequest out[32]);
uint32_t ecg_pipeline_events(const EcgPipeline *);
#endif
