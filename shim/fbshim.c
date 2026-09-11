/* freestanding shim: fb ioctls (360x360x32) + EVIOCGNAME=x2000_key; passthrough via raw syscall */
#define __NR_ioctl 4054
#define __NR_open  4005
#define __NR_write 4004
#define __NR_close 4006
#define __NR_read 4003
#define __NR_readlink 4085
#define __NR_nanosleep 4166
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
static int eq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int device_is(int fd,const char*name){
  char path[32]="/proc/self/fd/",digits[12],target[128];int n=0,i=14;
  if(fd<0)return 0;
  do{digits[n++]='0'+fd%10;fd/=10;}while(fd);
  while(n)path[i++]=digits[--n];path[i]=0;
  long len=sys3(__NR_readlink,(long)path,(long)target,127);
  if(len<0)return 0;target[len]=0;return eq(target,name);
}
/* Real evdev blocks while idle; our append-only event0 file returns EOF instead.
   echo_loop_key retries immediately, burning one CPU core. Pace only empty key
   reads, never queued events, touch reads, audio or unrelated files. __read is
   the guest libc's exported alias: keep errno/cancellation semantics intact. */
extern long __read(int,void*,unsigned long);
long read(int fd,void*data,unsigned long count){
  long result=__read(fd,data,count);
  if(result==0&&count&&device_is(fd,"/dev/input/event0")){
    long delay[2]={0,5000000}; /* at most one 5 ms polling interval for a new key */
    sys3(__NR_nanosleep,(long)delay,0,0);
  }
  return result;
}
/* Observe stock framebuffer copies instead of guessing which of two changed buffers
   is newer. Delegate to the guest libc (no build-host glibc dependency). */
extern void *mmap64(void*,unsigned long,int,int,int,long long);
extern void *memmove(void*,const void*,unsigned long);
static unsigned long fb_base,fb_size;
static int fb_live=-1;
/* BusyBox poweroff/reboot import libc reboot. Never pass a guest request to the
   shared kernel: publish it for the viewer's rootfs-scoped process supervisor. */
int reboot(int command){
  (void)command;
  const char request='1';
  long fd=sys3(__NR_open,(long)"/emu/power-request",1,0);
  if(fd>=0){sys3(__NR_write,fd,(long)&request,1);sys3(__NR_close,fd,0,0);}
  logmsg("[fbshim] reboot blocked; guest shutdown requested\n");
  return 0;
}
void *mmap(void*addr,unsigned long len,int prot,int flags,int fd,long offset){
  void*p=mmap64(addr,len,prot,flags,fd,(long long)offset);
  if(p!=(void*)-1&&device_is(fd,"/dev/fb0")){fb_base=(unsigned long)p;fb_size=len;fb_live=-1;}
  return p;
}
void *memcpy(void*dest,const void*src,unsigned long len){
  void*p=memmove(dest,src,len);
  unsigned long address=(unsigned long)dest;
  if(fb_base&&len&&address>=fb_base&&address-fb_base<fb_size){
    int index=(address-fb_base)/(W*H*4);
    if(index<2&&index!=fb_live){
      unsigned char value=index;
      long fd=sys3(__NR_open,(long)"/emu/fb-live",1,0);
      if(fd>=0){sys3(__NR_write,fd,(long)&value,1);sys3(__NR_close,fd,0,0);fb_live=index;}
    }
  }
  return p;
}
int ioctl(int fd,unsigned long req,void*arg){
  /* Only the two real volume GPIOs: active-low state maintained by the viewer.
     Unknown pins and requests retain their real failure semantics. */
  if(req==0x2000477a&&arg&&device_is(fd,"/dev/gpio")){
    int idx=eq(arg,"pb13")?0:eq(arg,"pb14")?1:-1;
    if(idx>=0){
      char levels[2]={'1','1'};
      long f=sys3(__NR_open,(long)"/emu/volume-buttons",0,0);
      if(f>=0){sys3(__NR_read,f,(long)levels,2);sys3(__NR_close,f,0,0);}
      return levels[idx]=='0'?0:1;
    }
  }
  if((req==0x2000ef03||req==0x2000ef04)&&device_is(fd,"/dev/cst816t"))return 0;
  if((req==0x2000ef01||req==0x2000ef02)&&device_is(fd,"/dev/lcd_st77916"))return 0;
  /* Mirror the firmware's DAC attenuation writes for Web Audio. PCM capture remains
     bit-exact pre-DAC data. CS43131: 0..254 = -0.5 dB/step, 255 = mute. */
  if((req==0x80014d2d||req==0x80014d2f)&&arg&&
     (device_is(fd,"/dev/cs43131")||device_is(fd,"/dev/cs43131b")||
      device_is(fd,"/dev/cs43131c")||device_is(fd,"/dev/cs43131d"))){
    const char*path=req==0x80014d2d?"/emu/dac-left":"/emu/dac-right";
    long f=sys3(__NR_open,(long)path,1,0);
    if(f>=0){sys3(__NR_write,f,(long)arg,1);sys3(__NR_close,f,0,0);}
    return 0;
  }
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
    unsigned char*p=arg; unsigned char yo[4]={p[20],p[21],p[22],p[23]};
    long fd=sys3(__NR_open,(long)"/fbpan",0x241/*O_WRONLY|O_CREAT|O_TRUNC (MIPS)*/,0644);
    if(fd>=0){sys3(__NR_write,fd,(long)yo,4);sys3(__NR_close,fd,0,0);} return 0; }
  if((req&0xff00)==0x4600){ return 0; } /* прочие fb ioctl */
  return sys3(__NR_ioctl,fd,req,(long)arg);
}
