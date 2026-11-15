#include "classification.h"
#include <math.h>
#include <string.h>

static int clock_ok(EcgClassState *s,uint64_t now) {
    if(now<s->now)return 0;
    s->now=now;return 1;
}
static void result(EcgClassResult *out,const EcgClassRequest *req,uint32_t status,int32_t cls) {
    out->request=*req;out->status=status;out->valid=status==ECG_CLASS_OK;
    out->class_id=out->valid?cls:-1;
}
int ecg_class_init(EcgClassState *s,uint32_t generation,const uint8_t model[32],uint64_t timeout) {
    if(!s||!model||!generation||!timeout)return ECG_CLASS_BAD;
    memset(s,0,sizeof(*s));s->generation=generation;s->timeout_ms=timeout;
    memcpy(s->model_sha256,model,32);return ECG_CLASS_ACCEPTED;
}
int ecg_class_submit(EcgClassState *s,const EcgClassRequest *r,uint64_t now) {
    if(!s||!r||!clock_ok(s,now))return ECG_CLASS_BAD;
    if(r->generation!=s->generation||!r->beat_id||r->beat_id<=s->last_id||
       r->position>r->ready_at||(r->sampling_hz!=360&&r->sampling_hz!=500)||
       r->input_status>ECG_CLASS_CANCELLED||UINT64_MAX-now<s->timeout_ms)return ECG_CLASS_BAD;
    if(r->input_status==ECG_CLASS_OK) {
        if(!r->rr_samples)return ECG_CLASS_BAD;
        for(unsigned i=0;i<128;++i)if(!isfinite(r->waveform[i]))return ECG_CLASS_BAD;
        for(unsigned i=0;i<3;++i)if(!isfinite(r->rr[i])||fabsf(r->rr[i])>5.f)return ECG_CLASS_BAD;
    }
    if(s->used+s->active>=ECG_CLASS_CAPACITY)return ECG_CLASS_BUSY;
    unsigned at=(s->head+s->used)%ECG_CLASS_CAPACITY;
    s->queue[at].request=*r;s->queue[at].deadline=now+s->timeout_ms;
    ++s->used;s->last_id=r->beat_id;return ECG_CLASS_ACCEPTED;
}
int ecg_class_take(EcgClassState *s,EcgClassRequest *out,uint64_t now) {
    if(!s||!out||!clock_ok(s,now))return ECG_CLASS_BAD;
    if(s->active||!s->used||now>=s->queue[s->head].deadline)return 0;
    s->flight=s->queue[s->head];s->head=(s->head+1)%ECG_CLASS_CAPACITY;--s->used;
    s->active=1;*out=s->flight.request;return 1;
}
int ecg_class_expire(EcgClassState *s,EcgClassResult *out,uint64_t now) {
    if(!s||!out||!clock_ok(s,now))return ECG_CLASS_BAD;
    EcgClassSlot *slot=s->active?&s->flight:(s->used?&s->queue[s->head]:0);
    if(!slot||now<slot->deadline)return 0;
    result(out,&slot->request,ECG_CLASS_TIMEOUT,-1);
    if(s->active)s->active=0;
    else{s->head=(s->head+1)%ECG_CLASS_CAPACITY;--s->used;}
    return 1;
}
int ecg_class_complete(EcgClassState *s,uint32_t generation,uint32_t beat,uint32_t status,int32_t cls,EcgClassResult *out,uint64_t now) {
    if(!s||!out||!clock_ok(s,now)||!s->active||generation!=s->generation||
       beat!=s->flight.request.beat_id||status>ECG_CLASS_CANCELLED||
       (status==ECG_CLASS_OK&&(cls<0||cls>3))||
       (status!=ECG_CLASS_OK&&cls!=-1))return ECG_CLASS_BAD;
    if(s->flight.request.input_status!=ECG_CLASS_OK && status==ECG_CLASS_OK)return ECG_CLASS_BAD;
    if(now>=s->flight.deadline)result(out,&s->flight.request,ECG_CLASS_TIMEOUT,-1);
    else result(out,&s->flight.request,status,cls);
    s->active=0;return 1;
}
int ecg_class_normalize_rr(const float input[3],const float mean[3],const float std[3],float out[3]) {
    float values[3];
    if(!input||!mean||!std||!out)return ECG_CLASS_BAD;
    for(unsigned i=0;i<3;++i) {
        if(!isfinite(input[i])||!isfinite(mean[i])||!isfinite(std[i])||std[i]<.01f)return ECG_CLASS_BAD;
        values[i]=(input[i]-mean[i])/std[i];
        if(values[i]>5.f)values[i]=5.f;
        if(values[i]<-5.f)values[i]=-5.f;
    }
    memcpy(out,values,sizeof(values));return ECG_CLASS_ACCEPTED;
}

int ecg_class_cancel(EcgClassState *s,EcgClassResult *out,uint64_t now) {
    if(!s||!out||!clock_ok(s,now))return ECG_CLASS_BAD;
    EcgClassSlot *slot=s->active?&s->flight:(s->used?&s->queue[s->head]:0);
    if(!slot)return 0;
    result(out,&slot->request,ECG_CLASS_CANCELLED,-1);
    if(s->active)s->active=0;
    else{s->head=(s->head+1)%ECG_CLASS_CAPACITY;--s->used;}
    return 1;
}
