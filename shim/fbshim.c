/* freestanding shim: fb ioctls (360x360x32) + EVIOCGNAME=x2000_key; passthrough via raw syscall */
#define __NR_ioctl 4054
#define __NR_open  4005
#define __NR_write 4004
#define __NR_close 4006
static long sys3(long n,long a,long b,long c){
  register long v0 asm("$2")=n,a0 asm("$4")=a,a1 asm("$5")=b,a2 asm("$6")=c; register long a3 asm("$7");
  asm volatile("syscall":"+r"(v0),"=r"(a3):"r"(a0),"r"(a1),"r"(a2)
    :"memory","$8","$9","$10","$11","$12","$13","$14","$15","$24","$25","hi","lo");
  return a3?-v0:v0; }
static void logmsg(const char*s){int i=0;while(s[i])i++;
  long fd=sys3(__NR_open,(long)"/fbshim.log",0x109/*O_WRONLY|O_CREAT|O_APPEND (MIPS)*/,0644);
  if(fd>=0){sys3(__NR_write,fd,(long)s,i);sys3(__NR_close,fd,0,0);}}
static void wr32(unsigned char*p,int off,unsigned int v){p[off]=v;p[off+1]=v>>8;p[off+2]=v>>16;p[off+3]=v>>24;}
#define W 360
#define H 360
#define VY 1080
#define BPP 32
int ioctl(int fd,unsigned long req,void*arg){
  unsigned nr=req&0xff,type=(req>>8)&0xff,dir=(req>>29)&7;
  if(type==0x45&&nr==0x06&&dir==2&&arg){ const char n[]="x2000_key";int i=0;for(;i<10;i++)((char*)arg)[i]=n[i];return 9;}
  if(req==0x4600&&arg){ /* FBIOGET_VSCREENINFO */
    unsigned char*p=arg; int i;for(i=0;i<160;i++)p[i]=0;
    wr32(p,0,W); wr32(p,4,H); wr32(p,8,W); wr32(p,12,VY); wr32(p,24,BPP);
    wr32(p,32,16);wr32(p,36,8); wr32(p,44,8);wr32(p,48,8); wr32(p,56,0);wr32(p,60,8); wr32(p,68,24);wr32(p,72,8);
    logmsg("[fbshim] GET_VSCREENINFO 360x360x32\n"); return 0; }
  if(req==0x4602&&arg){ /* FBIOGET_FSCREENINFO */
    unsigned char*p=arg; int i;for(i=0;i<80;i++)p[i]=0;
    const char id[]="ingenicfb"; for(i=0;i<9;i++)p[i]=id[i];
    wr32(p,20,W*VY*(BPP/8)); wr32(p,32,2); wr32(p,44,W*(BPP/8));
    logmsg("[fbshim] GET_FSCREENINFO smem/line ok\n"); return 0; }
  if(req==0x4606&&arg){ /* FBIOPAN_DISPLAY: записать yoffset в /fbpan */
    unsigned char*p=arg; unsigned char yo[4]={p[16],p[17],p[18],p[19]};
    long fd=sys3(__NR_open,(long)"/fbpan",0x241/*O_WRONLY|O_CREAT|O_TRUNC (MIPS)*/,0644);
    if(fd>=0){sys3(__NR_write,fd,(long)yo,4);sys3(__NR_close,fd,0,0);} return 0; }
  if((req&0xff00)==0x4600){ return 0; } /* прочие fb ioctl */
  return sys3(__NR_ioctl,fd,req,(long)arg);
}
