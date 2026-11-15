/* 独立500Hz源输入适配；QRS仍为冻结360Hz版本。系数/时轴见README。 */
#ifndef ECG_RATE500_H
#define ECG_RATE500_H
#include <stdint.h>
typedef struct {int16_t history[64];uint32_t next_source,next_internal,clipped;int closed;} EcgRate500;
void ecg_rate500_init(EcgRate500*);
/* 顺序从0开始；有输出返回1、无输出0、序号/结束错误-1，不补尾部。 */
int ecg_rate500_push(EcgRate500*,int16_t,uint32_t,int16_t*,uint32_t*);
/* 映射到500Hz源时轴；负值属于滤波启动区，不制造源事件。 */
int64_t ecg_rate500_source(uint32_t internal);
#endif
