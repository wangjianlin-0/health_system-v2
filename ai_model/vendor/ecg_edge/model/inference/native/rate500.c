#include "rate500.h"
#include "coefficients.h"
#include <math.h>
#include <string.h>
void ecg_rate500_init(EcgRate500*s){memset(s,0,sizeof(*s));}
int64_t ecg_rate500_source(uint32_t i){int64_t n=((int64_t)i-20)*25;return n<0?-((-n+9)/18):(n+9)/18;}
int ecg_rate500_push(EcgRate500*s,int16_t x,uint32_t seq,int16_t*out,uint32_t*index){
 if(!s||!out||!index||s->closed||seq!=s->next_source||seq>=2500000U)return -1;
 s->history[seq%64]=x;++s->next_source;uint64_t t=(uint64_t)s->next_internal*25;
 if(t>(uint64_t)seq*18)return 0;
 double v=0.;for(unsigned k=(unsigned)(t%18);k<1001;k+=18){if((uint64_t)k>t)continue;uint64_t p=(t-k)/18;
  if(p>seq||seq-p>=64)return -1;v+=ecg_rate500_fir[k]*s->history[p%64];}
 double rounded=copysign(floor(fabs(v)+.5),v);if(rounded>32767){rounded=32767;++s->clipped;}if(rounded< -32768){rounded=-32768;++s->clipped;}
 *out=(int16_t)rounded;*index=s->next_internal++;return 1;
}
