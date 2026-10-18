/* Freestanding ALSA interposer: capture the PCM mq_player writes, with no sound hardware.
 *
 * The device opens hw:%d,%d (a real ALSA card), which doesn't exist under qemu-user and can't be
 * redirected by asound.conf (hw: is kernel-direct). The LinuxKit VM has no snd modules either. So
 * we interpose libasound at the symbol level (preloaded via /etc/ld.so.preload, ahead of
 * libasound.so.2): snd_pcm_open returns a fake handle, every hw/sw-params call succeeds, and
 * snd_pcm_writei appends the raw PCM to /audio.pcm: a new recording in each process, emptied past
 * CAPTURE_MAX (capture.h). The negotiated format (channels, sample bytes, rate) is written to
 * /audio.fmt as three 32-bit LE ints so the host can wrap it into a WAV.
 *
 * Freestanding (-nostdlib, raw MIPS syscalls) for the same reason as fbshim: device glibc 2.29 !=
 * host toolchain glibc, so a normal .so won't load. Only the ~35 PCM symbols are interposed; the
 * snd_mixer_* calls fall through to real libasound (they fail harmlessly — volume is non-critical).
 */
#define __NR_open  4005
#define __NR_write 4004
#define __NR_close 4006
#define __NR_lseek 4019
#define O_WRONLY_CREAT_TRUNC  0x301   /* MIPS: O_WRONLY(1)|O_CREAT(0x100)|O_TRUNC(0x200) */
#ifndef ASNDSHIM_ROOT  /* tests run the shim outside a chroot and prefix its files */
#define ASNDSHIM_ROOT ""
#endif
#include "capture.h"

static long sys3(long n, long a, long b, long c){
  register long v0 asm("$2")=n, a0 asm("$4")=a, a1 asm("$5")=b, a2 asm("$6")=c;
  register long a3 asm("$7");
  asm volatile("syscall":"+r"(v0),"=r"(a3):"r"(a0),"r"(a1),"r"(a2)
    :"memory","$8","$9","$10","$11","$12","$13","$14","$15","$24","$25","hi","lo");
  return a3 ? -v0 : v0;
}

/* fake opaque handles handed back to the app (it never dereferences them — we interpose all uses) */
static char g_pcm[16], g_hwp[1024], g_swp[1024];
static int g_fd = -1;
static int g_ch = 2, g_sb = 4;      /* channels, sample bytes (default S32_LE stereo) */
static unsigned g_rate = 48000;

static void fmt_write(void){       /* overwrite /audio.fmt with ch, sb, rate (3x u32 LE) */
  long fd = sys3(__NR_open, (long)(ASNDSHIM_ROOT "/audio.fmt"), O_WRONLY_CREAT_TRUNC, 0644);
  if (fd >= 0){
    unsigned rec[3] = { (unsigned)g_ch, (unsigned)g_sb, g_rate };
    sys3(__NR_write, fd, (long)rec, sizeof rec);
    sys3(__NR_close, fd, 0, 0);
  }
}

/* ---- snd_pcm core ---- */
int snd_pcm_open(void **pcmp, const char *name, int stream, int mode){ (void)name;(void)stream;(void)mode; if(pcmp)*pcmp=(void*)g_pcm; return 0; }
int snd_pcm_close(void *p){ (void)p; return 0; }
int snd_pcm_prepare(void *p){ (void)p; return 0; }
int snd_pcm_start(void *p){ (void)p; return 0; }
int snd_pcm_drop(void *p){ (void)p; return 0; }
int snd_pcm_pause(void *p, int e){ (void)p;(void)e; return 0; }
int snd_pcm_resume(void *p){ (void)p; return 0; }
int snd_pcm_nonblock(void *p, int n){ (void)p;(void)n; return 0; }
const char *snd_pcm_name(void *p){ (void)p; return "cap"; }
const char *snd_strerror(int e){ (void)e; return "ok"; }

static unsigned g_pcm_bytes;                   /* bytes in /audio.pcm since it was last emptied */

long snd_pcm_writei(void *p, const void *buf, unsigned long size){
  (void)p;
  long bytes = (long)size * g_ch * g_sb;
  int fresh = g_fd < 0;                        /* a process starts a new recording */
  if (fresh) g_fd = sys3(__NR_open, (long)(ASNDSHIM_ROOT "/audio.pcm"), O_CAPTURE, 0644);
  else if (g_pcm_bytes && g_pcm_bytes + (unsigned long long)bytes > CAPTURE_MAX)
    fresh = sys3(__NR_ftruncate, g_fd, 0, 0) == 0;
  if (fresh){ g_pcm_bytes = 0; fmt_write(); }  /* new /audio.fmt mtime: a new generation */
  if (g_fd >= 0 && buf && size){
    long off = 0;
    while (off < bytes){                       /* write() may be partial */
      long w = sys3(__NR_write, g_fd, (long)((const char*)buf + off), bytes - off);
      if (w <= 0) break;
      off += w;
      g_pcm_bytes += (unsigned)w;
    }
  }
  return (long)size;
}
long snd_pcm_readi(void *p, void *buf, unsigned long size){ (void)p;(void)buf; return (long)size; }

/* ---- hw params ---- */
unsigned long snd_pcm_hw_params_sizeof(void){ return sizeof g_hwp; }
int  snd_pcm_hw_params_malloc(void **p){ if(p)*p=(void*)g_hwp; return 0; }
void snd_pcm_hw_params_free(void *p){ (void)p; }
int  snd_pcm_hw_params_any(void *pcm, void *p){ (void)pcm;(void)p; return 0; }
int  snd_pcm_hw_params(void *pcm, void *p){ (void)pcm;(void)p; return 0; }
int  snd_pcm_hw_params_dump(void *p, void *out){ (void)p;(void)out; return 0; }
int  snd_pcm_hw_params_set_access(void *pcm, void *p, int a){ (void)pcm;(void)p;(void)a; return 0; }
int  snd_pcm_hw_params_set_format(void *pcm, void *p, int fmt){
  (void)pcm;(void)p;
  /* ALSA format enum -> bytes/sample */
  if (fmt==2||fmt==3||fmt==4||fmt==5) g_sb=2;              /* S16/U16 */
  else if (fmt>=32 && fmt<=39) g_sb=3;                     /* S24_3LE etc. (packed 3-byte) */
  else g_sb=4;                                            /* S24_LE/S32_LE and friends */
  fmt_write(); return 0;
}
int  snd_pcm_hw_params_set_channels(void *pcm, void *p, unsigned int ch){ (void)pcm;(void)p; if(ch)g_ch=(int)ch; fmt_write(); return 0; }
int  snd_pcm_hw_params_set_rate(void *pcm, void *p, unsigned int rate, int dir){ (void)pcm;(void)p;(void)dir; if(rate)g_rate=rate; fmt_write(); return 0; }
int  snd_pcm_hw_params_set_rate_near(void *pcm, void *p, unsigned int *rate, int *dir){ (void)pcm;(void)p;(void)dir; if(rate&&*rate)g_rate=*rate; fmt_write(); return 0; }
int  snd_pcm_hw_params_set_period_size_near(void *pcm, void *p, unsigned long *val, int *dir){ (void)pcm;(void)p;(void)dir; if(val&&!*val)*val=1024; return 0; }
int  snd_pcm_hw_params_set_period_time_near(void *pcm, void *p, unsigned int *val, int *dir){ (void)pcm;(void)p;(void)dir; if(val&&!*val)*val=20000; return 0; }
int  snd_pcm_hw_params_set_buffer_size_near(void *pcm, void *p, unsigned long *val){ (void)pcm;(void)p; if(val&&!*val)*val=8192; return 0; }
int  snd_pcm_hw_params_set_buffer_time_near(void *pcm, void *p, unsigned int *val, int *dir){ (void)pcm;(void)p;(void)dir; if(val&&!*val)*val=200000; return 0; }
int  snd_pcm_hw_params_get_buffer_size(void *p, unsigned long *val){ (void)p; if(val)*val=8192; return 0; }
int  snd_pcm_hw_params_get_period_size(void *p, unsigned long *val, int *dir){ (void)p;(void)dir; if(val)*val=1024; return 0; }
int  snd_pcm_hw_params_get_buffer_time_max(void *p, unsigned int *val, int *dir){ (void)p;(void)dir; if(val)*val=500000; return 0; }

/* ---- sw params ---- */
unsigned long snd_pcm_sw_params_sizeof(void){ return sizeof g_swp; }
int snd_pcm_sw_params_current(void *pcm, void *p){ (void)pcm;(void)p; return 0; }
int snd_pcm_sw_params(void *pcm, void *p){ (void)pcm;(void)p; return 0; }
int snd_pcm_sw_params_dump(void *p, void *out){ (void)p;(void)out; return 0; }
int snd_pcm_sw_params_set_avail_min(void *pcm, void *p, unsigned long v){ (void)pcm;(void)p;(void)v; return 0; }
int snd_pcm_sw_params_set_start_threshold(void *pcm, void *p, unsigned long v){ (void)pcm;(void)p;(void)v; return 0; }
int snd_pcm_sw_params_set_stop_threshold(void *pcm, void *p, unsigned long v){ (void)pcm;(void)p;(void)v; return 0; }
