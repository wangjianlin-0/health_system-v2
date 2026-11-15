#include "pipeline.h"
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
int main(void){
#ifdef _WIN32
_setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
if(sizeof(EcgClassRequest)!=552)return 8;
EcgPipeline*s=calloc(1,ecg_pipeline_size());if(!s)return 2;
float z[3]={0},o[3]={1,1,1};if(ecg_pipeline_init(s,1,z,o))return 3;
uint32_t seq=0;int16_t sample;EcgClassRequest out[32];
while(fread(&sample,2,1,stdin)==1){int n=ecg_pipeline_push(s,sample,seq++,out);if(n<0){fprintf(stderr,"push_error=%d sample=%u\n",n,seq);free(s);return 4;}if(fwrite(out,sizeof(*out),n,stdout)!=(size_t)n)return 5;}
int n=ecg_pipeline_finish(s,out);if(n<0)return 6;fwrite(out,sizeof(*out),n,stdout);fprintf(stderr,"samples=%u state_bytes=%zu\n",seq,ecg_pipeline_size());free(s);return ferror(stdin)||ferror(stdout)?7:0;}
