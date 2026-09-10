#include <mqueue.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include <unistd.h>
int main(){
  struct mq_attr a; memset(&a,0,sizeof a); a.mq_maxmsg=32; a.mq_msgsize=8192;
  mqd_t q=mq_open("/ui",O_CREAT|O_RDONLY,0600,&a);
  if(q==(mqd_t)-1){ fprintf(stderr,"open ui failed errno=%d\n",errno); return 1;}
  char buf[8200]; unsigned prio; int n=0;
  for(int i=0;i<400;i++){
    struct timespec ts; clock_gettime(CLOCK_REALTIME,&ts); ts.tv_sec+=1;
    ssize_t r=mq_timedreceive(q,buf,sizeof buf,&prio,&ts);
    if(r<0){ if(errno==ETIMEDOUT) continue; continue; }
    n++;
    fprintf(stderr,"MSG#%d len=%zd | ascii=", n, r);
    for(ssize_t k=0;k<r && k<56;k++){ char c=buf[k]; fputc((c>=32&&c<127)?c:'.', stderr);}
    fprintf(stderr," | hex=");
    for(ssize_t k=0;k<r && k<56;k++) fprintf(stderr,"%02x",(unsigned char)buf[k]);
    fprintf(stderr,"\n");
  }
  fprintf(stderr,"total=%d\n",n);
  return 0;
}
