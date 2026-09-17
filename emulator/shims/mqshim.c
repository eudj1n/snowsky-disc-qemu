/* freestanding mipsel: interpose mq_open, log requested attr, force sane attr */
#define __NR_mq_open 4271
#define __NR_open    4005
#define __NR_write   4004
#define __NR_close   4006
static long sys4(long n,long a,long b,long c,long d){
  register long v0 asm("$2")=n,a0 asm("$4")=a,a1 asm("$5")=b,a2 asm("$6")=c,a3 asm("$7")=d;
  asm volatile("syscall":"+r"(v0),"+r"(a3):"r"(a0),"r"(a1),"r"(a2)
    :"memory","$8","$9","$10","$11","$12","$13","$14","$15","$24","$25","hi","lo");
  return a3?-v0:v0; }
static int slen(const char*s){int i=0;while(s[i])i++;return i;}
static void wn(char*b,int*pi,long v){ if(v<0){b[(*pi)++]='-';v=-v;} char t[16];int j=0;
  if(!v){b[(*pi)++]='0';return;} while(v){t[j++]='0'+v%10;v/=10;} while(j)b[(*pi)++]=t[--j];}
static void logline(const char*name,long oflag,long maxmsg,long msgsize,long rc){
  char b[160];int i=0;const char*p="[mqshim] name=";while(*p)b[i++]=*p++;
  int k=0;while(name[k]&&i<80)b[i++]=name[k++];
  const char*q=" oflag=";while(*q)b[i++]=*q++; wn(b,&i,oflag);
  const char*r=" maxmsg=";while(*r)b[i++]=*r++; wn(b,&i,maxmsg);
  const char*s=" msgsize=";while(*s)b[i++]=*s++; wn(b,&i,msgsize);
  const char*u=" rc=";while(*u)b[i++]=*u++; wn(b,&i,rc); b[i++]='\n';
  long fd=sys4(__NR_open,(long)"/mqshim.log",0x109,0644,0);
  if(fd>=0){sys4(__NR_write,fd,(long)b,i,0);sys4(__NR_close,fd,0,0,0);}}
/* sane attr: mq_flags, mq_maxmsg, mq_msgsize, mq_curmsgs, +4 reserved */
static long SANE[8]={0,16,4096,0,0,0,0,0};
int mq_open(const char*name,int oflag,int mode,void*attr){
  const char*n=name; if(n[0]=='/')n++;             /* replicate glibc slash strip */
  long mm=0,ms=0;
  if(attr){long*a=(long*)attr; mm=a[1]; ms=a[2];}
  long a3=(oflag&0x100/*O_CREAT*/)?(long)SANE:0;   /* force sane attr only when creating */
  long r=sys4(__NR_mq_open,(long)n,oflag,mode,a3);
  logline(n,oflag,mm,ms,r);
  if(r<0) return -1;                                /* glibc semantics: -1 on error */
  return (int)r;
}
