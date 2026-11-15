/* 500Hz源波形切拍；检测内部360Hz，事件/RR/窗口始终回到500Hz源时轴。 */
#include "pipeline.h"
#include "rate500.h"
#include "window500.h"
#include <math.h>
#include <string.h>
typedef struct {uint32_t id,pos,rr;float basic[3];} Pending500;
struct EcgPipeline {EcgRate500 rate;uint32_t generation,index,events,head,used,rrhead,rrused,closed,last,has_last;int16_t raw[4096];uint32_t history[401];float mean[3],std[3];Pending500 pending[32];};
static size_t offset500(void){return (sizeof(EcgPipeline)+7U)&~(size_t)7U;}
static EcgRuntime* detector500(EcgPipeline*s){return (EcgRuntime*)((unsigned char*)s+offset500());}
size_t ecg_pipeline_size(void){return offset500()+ecg_runtime_size();}
uint32_t ecg_pipeline_events(const EcgPipeline*s){return s->events;}
int ecg_pipeline_init(EcgPipeline*s,uint32_t gen,const float mean[3],const float std[3]){float test[3],x[3]={0};if(!s||!gen||ecg_class_normalize_rr(x,mean,std,test))return -1;memset(s,0,ecg_pipeline_size());s->generation=gen;s->index=UINT32_MAX;memcpy(s->mean,mean,12);memcpy(s->std,std,12);ecg_rate500_init(&s->rate);ecg_runtime_init(detector500(s));return 0;}
static void request500(EcgPipeline*s,const Pending500*p,EcgClassRequest*r){memset(r,0,sizeof(*r));r->generation=s->generation;r->beat_id=p->id;r->position=p->pos;r->rr_samples=p->rr;r->sampling_hz=500;r->ready_at=s->index;}
static int window500(EcgPipeline*s,const Pending500*p,EcgClassRequest*r){request500(s,p,r);if(p->pos<178||p->pos+266>s->index||s->index-(p->pos-178)>=4096){r->input_status=ECG_CLASS_WINDOW_INCOMPLETE;return 0;}
 double sampled[129],values[128],sum=0,variance=0;
 for(int m=0;m<129;++m){double v=0;int t=m*125+1250;for(int k=0;k<445;++k){int h=t-k*36;if(h>=0&&h<=2500)v+=((double)s->raw[(p->pos-178+(uint32_t)k)%4096]/4096.)*ecg_window500_fir[h];}sampled[m]=v;}
 for(int m=0;m<128;++m){values[m]=sampled[m]+(sampled[m+1]-sampled[m])*(8./125.);sum+=values[m];}
 double mean=sum/128.;for(int m=0;m<128;++m){values[m]-=mean;variance+=values[m]*values[m];}double std=sqrt(variance/128.);if(std<.05)std=.05;for(int m=0;m<128;++m)r->waveform[m]=(float)(values[m]/std);
 if(!p->rr){r->input_status=ECG_CLASS_MISSING_RR;return 0;}return ecg_class_normalize_rr(p->basic,s->mean,s->std,r->rr);
}
int ecg_pipeline_push(EcgPipeline*s,int16_t x,uint32_t seq,EcgClassRequest out[32]){if(!s||!out||s->closed||seq!=s->index+1U||seq>=1800000U)return -1;s->index=seq;s->raw[seq%4096]=x;
 int16_t value;uint32_t internal;int ready=ecg_rate500_push(&s->rate,x,seq,&value,&internal);if(ready<0)return -2;
 if(ready){EcgRuntimeEvent events[32];int count=ecg_runtime_push(detector500(s),value,events);if(count<0)return -3;
 for(int i=0;i<count;++i){int64_t mapped=ecg_rate500_source(events[i].position);if(mapped<0)return -4;uint32_t pos=(uint32_t)mapped;if(pos>seq||(s->has_last&&pos<=s->last)||s->used==32)return -5;
 Pending500*p=&s->pending[(s->head+s->used++)%32];memset(p,0,sizeof(*p));p->id=++s->events;p->pos=pos;p->rr=s->has_last?pos-s->last:0;s->last=pos;s->has_last=1;
 if(p->rr){double local=0,global=0;unsigned past=s->rrused<400?s->rrused:400,ln=past<80?past:80;
 for(unsigned j=0;j<past;++j){unsigned at=(s->rrhead+s->rrused-1-j)%401;global+=s->history[at];if(j<ln)local+=s->history[at];}
 local=ln?local/ln:p->rr;global=past?global/past:p->rr;double v[3]={p->rr/local,p->rr/global,local/global};for(int j=0;j<3;++j){if(v[j]<0)v[j]=0;if(v[j]>4)v[j]=4;p->basic[j]=(float)v[j]/4.f;}
 if(s->rrused==401){s->rrhead=(s->rrhead+1)%401;--s->rrused;}s->history[(s->rrhead+s->rrused++)%401]=p->rr;
 }}}
 int n=0;while(s->used){Pending500*p=&s->pending[s->head];if(p->pos>=178&&p->pos+266>s->index)break;if(window500(s,p,&out[n++]))return -6;s->head=(s->head+1)%32;--s->used;}return n;
}
int ecg_pipeline_finish(EcgPipeline*s,EcgClassRequest out[32]){if(!s||!out||s->closed)return -1;int n=0;while(s->used){request500(s,&s->pending[s->head],&out[n]);out[n++].input_status=ECG_CLASS_WINDOW_INCOMPLETE;s->head=(s->head+1)%32;--s->used;}s->closed=1;s->rate.closed=1;return n;}
