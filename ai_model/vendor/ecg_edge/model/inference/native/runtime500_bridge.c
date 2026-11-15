
/* 派生WFDB4.3.1 GQRS及冻结research26 Python；保留MIT许可
 * Copyright (c) 2016 MIT Laboratory for Computational Physiology.
 * 原许可src/third_party/wfdb_license.txt；不更改判决规则。 */
#include "runtime.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#define CAP 4096
#define NPEAK 64
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef struct {double b[5],z1,z2;} Biquad;
typedef struct {int time,type;int64_t amp;} Peak;
struct EcgRuntime {
 int n,t,smt,error,first,filtered_first,lastpos,has_shape,last_width;
 int64_t sm[1024],qf[1024],v1,pthr,qthr,pthmin,qthmin;
 int rrmean,rrdev,rtmean,annot,last_peak,last_qrs,current,previous_peak;
 int16_t raw[CAP],core[CAP];double variation[CAP],filtered[CAP],smooth[CAP];
 Biquad low,quality,hp,lp;double previous_low;int has_low;
 Peak peaks[NPEAK];
 double shape_slope,shape_amp,templates[8][57];int nt,learned,eh,ne;
 double energies[8],amplitudes[8];
 int gn,active,last_gradient,widths[8],nw,wh,gh,gu,bh,bu;
 double gwindow[37],bwindow[271],gsum,bsum;
 EcgRuntimeEvent secondary[32],pending[32];unsigned sh,su,ph,pu;
 int last_final;
};
static int compare(const void*a,const void*b){double x=*(const double*)a,y=*(const double*)b;return (x>y)-(x<y);}
static double med(double *a,int n,int upper){if(n<=0)return 0;qsort(a,(size_t)n,sizeof(double),compare);return upper||n%2?a[n/2]:(a[n/2-1]+a[n/2])/2.;}
static double median_int(const int *a,int n){double tmp[512];for(int i=0;i<n;++i)tmp[i]=a[i];return med(tmp,n,0);}
static double median_double(const double *a,int n){double tmp[512];memcpy(tmp,a,(size_t)n*sizeof(double));return med(tmp,n,0);}
static Biquad coeff(int high,double f){double w=2.*3.14159265358979323846*f/360.,c=cos(w),alpha=sin(w)/(2.*sqrt(.5)),a=1.+alpha;Biquad b={{0},0,0};
 b.b[0]=(high?(1.+c):(1.-c))/2./a;b.b[1]=(high?-(1.+c):(1.-c))/a;b.b[2]=b.b[0];b.b[3]=-2.*c/a;b.b[4]=(1.-alpha)/a;return b;}
static double tick(Biquad*b,double x){double y=b->b[0]*x+b->z1;b->z1=b->b[1]*x-b->b[3]*y+b->z2;b->z2=b->b[2]*x-b->b[4]*y;return y;}
static int raw(EcgRuntime*s,int n){if(n<0)return s->first;if(n>s->n||n<=s->n-CAP){s->error=1;return 0;}return s->raw[n%CAP];}
static int core(EcgRuntime*s,int n){(void)raw(s,n);return n<0?s->filtered_first:s->core[n%CAP];}
static double f_at(EcgRuntime*s,int n,double *buffer){if(n<0||n>s->n||n<=s->n-CAP){s->error=1;return 0.;}return buffer[n%CAP];}
static double baseline(EcgRuntime*s,int start,int end,int exclude_a,int exclude_b,int upper){double a[512];int n=0;
 for(int i=MAX(0,start);i<=MIN(s->n,end);++i)if(i<exclude_a||i>exclude_b)a[n++]=raw(s,i);
 return n?med(a,n,upper):raw(s,MAX(0,start));}
static double aligned(double v[57],double templates[8][57],int nt){double best=0.,ca[58]={0};for(int i=0;i<57;++i)ca[i+1]=ca[i]+v[i]*v[i];
 for(int k=0;k<nt;++k){double ct[58]={0};for(int i=0;i<57;++i)ct[i+1]=ct[i]+templates[k][i]*templates[k][i];
  for(int shift=-10;shift<=10;++shift){int al=MAX(0,shift),ah=MIN(57,57+shift),tl=MAX(0,-shift),th=MIN(57,57-shift);double corr=0.;
   for(int i=al;i<ah;++i)corr+=v[i]*templates[k][i-shift];
   double den=(ca[ah]-ca[al])*(ct[th]-ct[tl]);double score=corr/sqrt(MAX(1e-24,den));if(score>best)best=score;
  }}return best;}
/* 返回接受与否；拒绝时恢复与Python各层一致的有限状态。 */
static int annotation(EcgRuntime*s,int center,int *position){
 int previous=s->lastpos,previous_width=s->last_width,oldest=MAX(0,s->n-CAP+1);double prev_slope=s->shape_slope,prev_amp=s->shape_amp;
 if(oldest>0&&center-54<oldest)return 0;
 int lo=MAX(0,center-54),hi=MIN(s->n,center+54);if(lo>hi)return 0;
 double base=baseline(s,lo,hi,1,0,1);lo=MAX(0,center-36);hi=MIN(s->n,center+36);
 double maximum=0.;for(int i=lo;i<=hi;++i)maximum=MAX(maximum,fabs(raw(s,i)-base));
 int extrema[100],ne=0;for(int i=MAX(1,lo);i<=hi;++i)if(i<s->n&&fabs(raw(s,i)-base)>=maximum*.8&&((raw(s,i)>=raw(s,i-1)&&raw(s,i)>=raw(s,i+1))||(raw(s,i)<=raw(s,i-1)&&raw(s,i)<=raw(s,i+1))))extrema[ne++]=i;
 int near=lo,strong=lo;
 if(ne){near=strong=extrema[0];for(int k=1;k<ne;++k){int i=extrema[k];if(abs(i-center)<abs(near-center)||(abs(i-center)==abs(near-center)&&fabs(raw(s,i)-base)>fabs(raw(s,near)-base)))near=i;
  if(fabs(raw(s,i)-base)>fabs(raw(s,strong)-base))strong=i;}}
 int change=0;if(ne&&near!=strong){double v=raw(s,near)-base,w=raw(s,strong)-base;if(v*w>0&&abs(near-strong)<=28){double floor=1e30;int sign=v>0?1:-1;for(int i=MIN(near,strong);i<=MAX(near,strong);++i)floor=MIN(floor,sign*(raw(s,i)-base));change=floor>=.5*MIN(fabs(v),fabs(w));}}
 int pos=lo;double fraction=change?1.:.8;ne=0;
 for(int i=MAX(1,lo);i<=hi;++i)if(i<s->n&&fabs(raw(s,i)-base)>=maximum*fraction&&((raw(s,i)>=raw(s,i-1)&&raw(s,i)>=raw(s,i+1))||(raw(s,i)<=raw(s,i-1)&&raw(s,i)<=raw(s,i+1))))extrema[ne++]=i;
 if(ne){pos=extrema[0];for(int k=1;k<ne;++k){int i=extrema[k];if(abs(i-center)<abs(pos-center)||(abs(i-center)==abs(pos-center)&&fabs(raw(s,i)-base)>fabs(raw(s,pos)-base)))pos=i;}}
 else for(int i=lo+1;i<=hi;++i)if(fabs(raw(s,i)-base)>fabs(raw(s,pos)-base))pos=i;
 int a=MAX(0,pos-28),b=MIN(s->n,pos+28),c=MAX(0,pos-86),d=MIN(s->n,pos+86);double inside=0.,outside=0.;
 for(int i=a;i<=b;++i)inside+=s->variation[i%CAP];for(int i=c;i<a;++i)outside+=s->variation[i%CAP];for(int i=b+1;i<=d;++i)outside+=s->variation[i%CAP];
 if((inside/(b-a+1))/(outside/MAX(1,d-c-b+a)+1e-12)<1.0)return 0;
 if(previous>=0&&pos-previous<86)return 0;
 /* ShapeDetector：中心外侧取上中位数，空侧带时回退整个邻域。 */
 double values[512];int count=0;for(int i=MAX(0,pos-54);i<MAX(MAX(0,pos-54),pos-28);++i)values[count++]=raw(s,i);
 for(int i=MIN(MIN(s->n,pos+54)+1,pos+29);i<=MIN(s->n,pos+54);++i)values[count++]=raw(s,i);
 if(!count)for(int i=MAX(0,pos-54);i<=MIN(s->n,pos+54);++i)values[count++]=raw(s,i);
 double shape_base=med(values,count,1),positive=-1e30,negative=-1e30,slope=0.;
 for(int i=a;i<=b;++i){positive=MAX(positive,raw(s,i)-shape_base);negative=MAX(negative,shape_base-raw(s,i));slope=MAX(slope,s->variation[i%CAP]);}
 double amp=MAX(MAX(positive,negative),1.),biphasic=MAX(0.,MIN(positive,negative))/amp;
 if(previous>=0&&s->has_shape&&pos-previous<144&&slope/amp<.5*prev_slope/MAX(1.,prev_amp)&&biphasic<.25&&amp<.75*prev_amp)return 0;
 /* 候选模板层：与Python顺序相同，均值/范数和对齐相关。 */
 double vector[57],mean=0.,norm=0.,correlations[8],unshifted=0.;
 for(int j=0;j<57;++j){vector[j]=raw(s,MAX(0,pos-28+j));mean+=vector[j];}mean/=57.;
 for(int j=0;j<57;++j){vector[j]-=mean;norm+=vector[j]*vector[j];}norm=sqrt(norm);
 for(int j=0;j<57;++j)vector[j]/=MAX(1.,norm);
 for(int k=0;k<s->nt;++k){double dot=0.;for(int j=0;j<57;++j)dot+=vector[j]*s->templates[k][j];correlations[k]=dot;if(!k||dot>unshifted)unshifted=dot;}
 double similarity=aligned(vector,s->templates,s->nt);
 double cb=baseline(s,pos-54,pos+54,a,b,0);positive=negative=-1e30;
 for(int i=a;i<=b;++i){positive=MAX(positive,raw(s,i)-cb);negative=MAX(negative,cb-raw(s,i));}
 double rawamp=MAX(MAX(positive,negative),1.);biphasic=MAX(0.,MIN(positive,negative))/rawamp;
 double v=raw(s,pos)-cb,half=fabs(v)/2.;int sign=v>=0?1:-1,left=pos,right=pos;
 while(left>MAX(0,pos-54)&&sign*(raw(s,left-1)-cb)>=half)--left;
 while(right<MIN(s->n,pos+54)&&sign*(raw(s,right+1)-cb)>=half)++right;
 int width=right-left+1;
 int suspect=previous>=0&&previous_width>=0&&pos-previous<144&&width>previous_width/.5&&rawamp<.75*prev_amp&&biphasic<.25;
 if(suspect&&similarity<.8)return 0;
 int64_t energy=s->qf[(unsigned)center&1023];double em=s->ne==8?median_double(s->energies,8):0.;
 inside/=b-a+1;outside/=MAX(1,d-c-b+a);
 int low=s->ne==8&&energy<.5*em&&inside<2.*outside;
 /* 复核相邻±1点，不声称定位误差上界；仍使用原2倍能量门槛及独立佐证。 */
 int corroborated=0;for(unsigned kk=0;kk<s->su;++kk){EcgRuntimeEvent *e=&s->secondary[(s->sh+kk)%32];if(abs((int)e->position-pos)<=10){corroborated=1;break;}}
 if(low&&corroborated&&width>.5*previous_width){for(int shift=-1;shift<=1;shift+=2){int aa=MAX(0,pos+shift-28),bb=MIN(s->n,pos+shift+28),cc=MAX(0,pos+shift-86),dd=MIN(s->n,pos+shift+86);double ii=0.,oo=0.;
  for(int j=aa;j<=bb;++j)ii+=s->variation[j%CAP];for(int j=cc;j<aa;++j)oo+=s->variation[j%CAP];for(int j=bb+1;j<=dd;++j)oo+=s->variation[j%CAP];
  if(ii/(bb-aa+1)>=2.*oo/MAX(1,dd-cc-bb+aa)){low=0;break;}}}
 if(s->nt&&low&&similarity<.8)return 0;
 int high=s->ne<8||(inside>=2.*outside&&energy>=.5*em);
 if(high){if(unshifted>=.9){int k=0;for(int j=1;j<s->nt;++j)if(correlations[j]>correlations[k])k=j;double sum=0.;for(int j=0;j<57;++j){s->templates[k][j]=.875*s->templates[k][j]+.125*vector[j];sum+=s->templates[k][j]*s->templates[k][j];}sum=sqrt(sum);for(int j=0;j<57;++j)s->templates[k][j]/=MAX(1e-12,sum);}
 else if(similarity<.9&&s->nt<8){memcpy(s->templates[s->nt++],vector,sizeof(vector));}}
 s->last_width=width;s->lastpos=pos;s->has_shape=1;s->shape_slope=slope;s->shape_amp=amp;
 s->energies[s->eh]=energy;s->amplitudes[s->eh]=amp;s->eh=(s->eh+1)%8;if(s->ne<8)++s->ne;*position=pos;return 1;
}
static int peaktype(EcgRuntime*s,int p,int depth){Peak*x=&s->peaks[p];if(x->type)return x->type;if(depth>=64){s->error=2;return 2;}int t0=MAX(0,x->time-86),t1=x->time+86,pp=(p+63)%64;
 for(int k=0;k<64&&t0<s->peaks[pp].time&&s->peaks[pp].time<s->peaks[(pp+1)%64].time;++k){if(!s->peaks[pp].amp)break;if(x->amp<s->peaks[pp].amp&&peaktype(s,pp,depth+1)==1){x->type=2;return 2;}pp=(pp+63)%64;}
 pp=(p+1)%64;for(int k=0;k<64&&s->peaks[pp].time<t1&&s->peaks[pp].time>s->peaks[(pp+63)%64].time;++k){if(!s->peaks[pp].amp)break;if(x->amp<s->peaks[pp].amp&&peaktype(s,pp,depth+1)==1){x->type=2;return 2;}pp=(pp+1)%64;}x->type=1;return 1;}
static int missing(EcgRuntime*s,int r,int p){if(r<0)return -1;int best=-1,err=s->peaks[p].time-s->peaks[r].time,q=(r+1)%64;
 for(int k=0;k<64&&s->peaks[q].time<s->peaks[p].time;++k){if(peaktype(s,q,0)==1){int e=abs(s->peaks[q].time-s->peaks[r].time-s->rrmean);if(e<err){err=e;best=q;}}q=(q+1)%64;}return best;}
static int64_t smooth(EcgRuntime*s,int t){while(t>s->smt){int n=++s->smt;if(n>6)s->sm[(unsigned)n&1023]=s->sm[(unsigned)(n-1)&1023]+core(s,n+6)+core(s,n+5)-core(s,n-6)-core(s,n-7);
 else {int64_t v=core(s,n);for(int j=1;j<6;++j){v+=core(s,n+j)+core(s,n-j);s->sm[(unsigned)n&1023]=v*2+core(s,n+j+1)+core(s,n-j-1);}}}return s->sm[(unsigned)t&1023];}
static void qfilter(EcgRuntime*s){int t=s->t;int64_t dv2=smooth(s,t+24)-s->sm[(unsigned)(t-24)&1023];int64_t dv1=s->sm[(unsigned)(t+6)&1023]-s->sm[(unsigned)(t-6)&1023];
 int64_t dv=dv1*2-(s->sm[(unsigned)(t+12)&1023]-s->sm[(unsigned)(t-12)&1023]);dv=dv*2+dv1-(s->sm[(unsigned)(t+18)&1023]-s->sm[(unsigned)(t-18)&1023]);dv=dv*2+dv2;s->v1+=dv;
 int64_t v0=(int64_t)((double)s->v1/2304.);s->qf[(unsigned)t&1023]=v0*v0;}
static void primary_step(EcgRuntime*s){qfilter(s);int t=s->t;int64_t q0=s->qf[(unsigned)t&1023],q1=s->qf[(unsigned)(t-1)&1023],q2=s->qf[(unsigned)(t-2)&1023];
 int fresh=q1>s->pthr&&q2<q1&&q1>=q0&&t>24;
 if(fresh){s->current=(s->current+1)%64;s->peaks[s->current]=(Peak){t-1,0,q1};s->peaks[(s->current+1)%64].amp=0;s->last_peak=t-1;}
 if(fresh||t%18==0){int p=(s->current+1)%64;for(int drain=0;drain<64&&s->peaks[p].time<t-118;++drain){
 if(s->peaks[p].time>=s->annot+86&&peaktype(s,p,0)==1){if(s->peaks[p].amp>s->qthr){int rr=s->peaks[p].time-s->annot,q=missing(s,s->previous_peak,p);
 if(rr>1.66*s->rrmean&&q>=0){p=q;rr=s->peaks[p].time-s->annot;}
 int pos;if(!annotation(s,s->peaks[p].time,&pos)){s->peaks[p].type=2;p=(p+1)%64;continue;}
 if(s->pu==32){s->error=3;return;}unsigned at=(s->ph+s->pu++)%32;s->pending[at]=(EcgRuntimeEvent){(uint32_t)(s->n+5),(uint32_t)pos,0};
 int rrd=abs(rr-s->rrmean);s->rrdev+=(rrd-s->rrdev)>>3;rrd=MIN(rrd,7);s->rrmean+=rr>s->rrmean?rrd:-rrd;
 if(s->peaks[p].amp>s->qthr*4)++s->qthr;else if(s->peaks[p].amp<s->qthr)--s->qthr;if(s->qthr>s->pthr*20)s->qthr=s->pthr*20;
 s->last_qrs=s->peaks[p].time;s->annot=s->peaks[p].time;int tw=-1,rtdmin=s->rtmean;q=(p+1)%64;
 for(int k=0;k<64&&s->peaks[q].time>s->annot;++k){int rt=s->peaks[q].time-s->annot-12;if(rt<90){q=(q+1)%64;continue;}if(rt>118)break;int d=abs(rt-s->rtmean);if(d<rtdmin){tw=q;rtdmin=d;}q=(q+1)%64;}
 if(tw>=0){int rt=s->peaks[tw].time-12-s->annot;s->rtmean+=(rt-s->rtmean)>>4;if(s->rtmean>118)s->rtmean=118;else if(s->rtmean<90)s->rtmean=86;}s->previous_peak=p;
 }else if(t-s->last_qrs>864&&s->qthr>s->qthmin)s->qthr-=s->qthr>>4;}p=(p+1)%64;}}
 else if(t-s->last_peak>864&&s->pthr>s->pthmin)s->pthr-=s->pthr>>4;++s->t;}
static void secondary_confirm(EcgRuntime*s,int start,int end){int width=end-start;double minimum=s->nw?.4*median_int(s->widths,s->nw):360*.032;if(width<minimum||width>180)return;
 double base=baseline(s,start-54,end+54,start,end,0);int pos=-1;for(int i=MAX(1,start);i<=MIN(end,s->n-1);++i)if((raw(s,i)>=raw(s,i-1)&&raw(s,i)>=raw(s,i+1))||(raw(s,i)<=raw(s,i-1)&&raw(s,i)<=raw(s,i+1))){
 if(pos<0||fabs(raw(s,i)-base)>fabs(raw(s,pos)-base)||(fabs(raw(s,i)-base)==fabs(raw(s,pos)-base)&&fabs(i-(start+end)/2.)<fabs(pos-(start+end)/2.)))pos=i;}
 if(pos<0||(s->last_gradient>=0&&pos-s->last_gradient<86))return;
 if(s->su==32){s->sh=(s->sh+1)%32;--s->su;}
 unsigned at=(s->sh+s->su++)%32;s->secondary[at]=(EcgRuntimeEvent){(uint32_t)s->n,(uint32_t)pos,s->last_gradient<0?0:(uint32_t)(pos-s->last_gradient)};s->last_gradient=pos;s->widths[s->wh]=width;s->wh=(s->wh+1)%8;if(s->nw<8)++s->nw;
}
static void secondary_push(EcgRuntime*s,int sample){int n=s->n;if(n==0){s->hp.z1=-s->hp.b[0]*sample;s->hp.z2=s->hp.b[2]*sample;}s->filtered[n%CAP]=tick(&s->lp,tick(&s->hp,sample));if(!n)return;
 double grad=fabs((f_at(s,n,s->filtered)-f_at(s,MAX(0,n-2),s->filtered))/2.);
 double old=0.;if(s->gu==37)old=s->gwindow[s->gh];
 s->gwindow[(s->gh+s->gu)%37]=grad;s->gsum+=grad;
 if(s->gu==37){s->gsum-=old;s->gh=(s->gh+1)%37;}else ++s->gu;
 if(s->gu<37)return;
 int smooth_at=n-19;double smooth_value=s->gsum/37.;s->smooth[smooth_at%CAP]=smooth_value;
 old=0.;if(s->bu==271)old=s->bwindow[s->bh];
 s->bwindow[(s->bh+s->bu)%271]=smooth_value;s->bsum+=smooth_value;
 if(s->bu==271){s->bsum-=old;s->bh=(s->bh+1)%271;}else ++s->bu;
 if(s->bu<271)return;
 int c=smooth_at-135;double threshold=1.5*MAX(0.,s->bsum/271.);
 int on=f_at(s,c,s->smooth)>MAX(1e-9,threshold);
 if(s->active==-1){if(!on)s->active=-2;return;}
 if(on&&s->active==-2)s->active=c;
 else if(!on&&s->active>=0){int start=s->active;s->active=-2;secondary_confirm(s,start,c);return;}
 if(s->active>=0&&c-s->active>360)s->active=-1;
}
size_t ecg_runtime_size(void){return sizeof(EcgRuntime);}
void ecg_runtime_init(EcgRuntime*s){memset(s,0,sizeof(*s));s->n=-1;s->t=-24;s->lastpos=s->last_width=s->last_gradient=s->last_final=-1;s->previous_peak=-1;s->active=-2;
 s->pthr=47255;s->qthr=94510;s->pthmin=11813;s->qthmin=15750;s->rrmean=288;s->rrdev=72;s->rtmean=94;
 s->low=s->quality=s->lp=coeff(0,40);s->hp=coeff(1,.5);s->gu=18;s->bu=135;}
int ecg_runtime_pending(const EcgRuntime*s){return (int)s->pu;}
int ecg_runtime_push(EcgRuntime*s,int16_t sample,EcgRuntimeEvent out[32]){
 if(s->error)return -s->error;++s->n;int n=s->n;if(!n)s->first=sample;s->raw[n%CAP]=sample;
 double filtered=tick(&s->low,sample);int y=(int)copysign(floor(fabs(filtered)+.5),filtered);y=MIN(32767,MAX(-32768,y));s->core[n%CAP]=(int16_t)y;if(!n)s->filtered_first=y;
 double quality=tick(&s->quality,sample);s->variation[n%CAP]=s->has_low?fabs(quality-s->previous_low):0.;s->previous_low=quality;s->has_low=1;
 secondary_push(s,sample);
 while(s->t+61<=s->n&&!s->error)primary_step(s);
 int count=0;while(s->pu&&s->pending[s->ph].emitted<=(unsigned)n){EcgRuntimeEvent e=s->pending[s->ph];s->ph=(s->ph+1)%32;--s->pu;
 while(s->su&&(int)e.emitted-(int)s->secondary[s->sh].emitted>1440){s->sh=(s->sh+1)%32;--s->su;}
 int alternate=-1;for(unsigned k=0;k<s->su;++k){int p=(int)s->secondary[(s->sh+k)%32].position,dist=abs(p-(int)e.position);if(dist>0&&dist<=10&&(alternate<0||dist<abs(alternate-(int)e.position)))alternate=p;}
 if(alternate>=0){int lo=MIN((int)e.position,alternate),hi=MAX((int)e.position,alternate);double flank[128];int nf=0;for(int i=MAX(0,lo-54);i<MAX(0,lo-28);++i)flank[nf++]=raw(s,i);for(int i=hi+29;i<=MIN((int)e.emitted,hi+54);++i)flank[nf++]=raw(s,i);
 double base=nf?med(flank,nf,0):raw(s,(int)e.position),a=raw(s,(int)e.position)-base,b=raw(s,alternate)-base;
 if(a*b<0&&fabs(b/a)>=.8&&fabs(b/a)<=1.25&&(s->last_final<0||alternate>s->last_final))e.position=(uint32_t)alternate;}
 e.rr=s->last_final<0?0:e.position-(uint32_t)s->last_final;s->last_final=(int)e.position;out[count++]=e;}
 return s->error?-s->error:count;
}
