/* Test-only wrapper around the original Spike/SoftFloat estimate helpers. */
#include <stdio.h>
#include <inttypes.h>
#include "vector_estimate_helpers.c"
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    FILE *in=fopen(argv[1],"r"),*out=fopen(argv[2],"w");if(!in||!out)return 3;
    unsigned width,sqrt_est,rm,count=0;uint64_t value;
    while(fscanf(in,"%u %u %u %"SCNx64,&width,&sqrt_est,&rm,&value)==4) {
        int e=width==16?5:width==32?8:11,s=width-e-1;
        uint64_t frac_mask=(UINT64_C(1)<<s)-1,exp_mask=(UINT64_C(1)<<e)-1;
        uint64_t frac=value&frac_mask,exp=(value>>s)&exp_mask,sign=value>>(width-1);
        uint64_t inf=exp_mask<<s,nan=inf|(UINT64_C(1)<<(s-1)),result=0;unsigned flags=0;
        if(exp==exp_mask && frac) { result=nan;flags=(frac>>(s-1))?0:16; }
        else if(sqrt_est && sign && (exp||frac)) { result=nan;flags=16; }
        else if(!exp && !frac) { result=(sign<<(width-1))|inf;flags=8; }
        else if(exp==exp_mask)result=sqrt_est?0:sign<<(width-1);
        else if(sqrt_est)result=rsqrte7(value,e,s,!exp);
        else { bool abnormal=false;result=recip7(value,e,s,rm,!exp,&abnormal);flags=abnormal?5:0; }
        if(width!=64)result&=(UINT64_C(1)<<width)-1;
        fprintf(out,"%u %u %u %016"PRIx64" %016"PRIx64" %02x\n",width,sqrt_est,rm,value,result,flags);count++;
    }
    fclose(in);fclose(out);printf("PASS Spike estimate reference vectors=%u\n",count);return 0;
}
