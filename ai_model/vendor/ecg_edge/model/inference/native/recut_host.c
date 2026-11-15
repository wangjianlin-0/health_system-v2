/* 模型侧主机重切参考；原检测器、板端pipeline及公共合同原字节保持。 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "classification.h"
#include "window500.h"
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
int main(void){
#ifdef _WIN32
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
    if(sizeof(EcgClassRequest)!=552)return 9;
    uint32_t count,n;
    if(fread(&count,4,1,stdin)!=1||fread(&n,4,1,stdin)!=1||count>1800000||n>30000)return 2;
    int16_t *input=malloc((size_t)count*2);if(!input)return 3;
    if(fread(input,2,count,stdin)!=count)return 4;
    uint32_t *history=calloc(n+1,4);if(!history)return 3;uint32_t used=0,last=0;
    for(uint32_t i=0;i<n;i++){
        uint32_t q[2];if(fread(q,4,2,stdin)!=2)return 5;
        uint32_t pos=q[0],ready=q[1];if(ready>=count||pos>ready||(i&&pos<=last))return 6;
        EcgClassRequest out;memset(&out,0,sizeof(out));
        out.generation=1;out.beat_id=i+1;out.position=pos;out.ready_at=ready;out.sampling_hz=500;out.rr_samples=i?pos-last:0;last=pos;
        float basic[3]={0};
        if(out.rr_samples){
            double local=0,global=0;uint32_t past=used<400?used:400,ln=past<80?past:80;
            for(uint32_t j=0;j<past;j++){global+=history[used-1-j];if(j<ln)local+=history[used-1-j];}
            local=ln?local/ln:out.rr_samples;global=past?global/past:out.rr_samples;
            double values[3]={out.rr_samples/local,out.rr_samples/global,local/global};
            for(int j=0;j<3;j++){if(values[j]<0)values[j]=0;if(values[j]>4)values[j]=4;basic[j]=(float)values[j]/4.f;}
            history[used++]=out.rr_samples;
        }
        if(pos<178||pos+266>=count||pos+266>ready||ready-(pos-178)>=4096){out.input_status=ECG_CLASS_WINDOW_INCOMPLETE;}
        else{
            double sampled[129],values[128],sum=0,variance=0;
            for(int m=0;m<129;m++){
                double v=0;int t=m*125+1250;
                for(int k=0;k<445;k++){int h=t-k*36;if(h>=0&&h<=2500)v+=((double)input[pos-178+(uint32_t)k]/4096.)*ecg_window500_fir[h];}
                sampled[m]=v;
            }
            for(int m=0;m<128;m++){values[m]=sampled[m]+(sampled[m+1]-sampled[m])*(8./125.);sum+=values[m];}
            double mean=sum/128.;for(int m=0;m<128;m++){values[m]-=mean;variance+=values[m]*values[m];}
            double std=sqrt(variance/128.);if(std<.05)std=.05;
            for(int m=0;m<128;m++)out.waveform[m]=(float)(values[m]/std);
            if(!out.rr_samples)out.input_status=ECG_CLASS_MISSING_RR;
            else memcpy(out.rr,basic,12);
        }
        if(fwrite(&out,sizeof(out),1,stdout)!=1)return 7;
    }
    free(history);free(input);fprintf(stderr,"samples=%u events=%u host_recut_only=1\n",count,n);
    return ferror(stdin)||ferror(stdout)?8:0;
}
