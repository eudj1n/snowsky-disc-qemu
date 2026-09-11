/* Freestanding tinyalsa interposer: capture the PCM the LOCAL DAC path writes, no hardware.
 *
 * mq_player links both libasound and libtinyalsa; LOCAL playback (the internal CS43131) goes
 * through tinyalsa: pcm_params_get() to validate the card, then pcm_open()/pcm_write() to the DAC.
 * Under emulation there's no card, so pcm_params_get()/pcm_open() would fail and playback aborts
 * ("error config pcm params"). We interpose libtinyalsa (preloaded via /etc/ld.so.preload, ahead
 * of libtinyalsa.so.1): pcm_params_* report a permissive card, pcm_open returns a fake handle and
 * records the config, and pcm_write appends the raw PCM to /audio.pcm. tinyalsa's pcm_write takes
 * a BYTE count, so capture is exact without knowing the frame size.
 *
 * Freestanding (-nostdlib, raw MIPS syscalls) — device glibc 2.29 != host toolchain glibc, same as
 * fbshim. The negotiated format (channels, sample-bytes, rate) goes to /audio.fmt as 3x u32 LE so
 * the host can wrap /audio.pcm into a WAV.
 */
#define __NR_open  4005
#define __NR_write 4004
#define __NR_close 4006
#define O_WCA 0x109   /* MIPS O_WRONLY|O_CREAT|O_APPEND */
#define O_WCT 0x301   /* MIPS O_WRONLY|O_CREAT|O_TRUNC  */

static long sys3(long n, long a, long b, long c){
  register long v0 asm("$2")=n, a0 asm("$4")=a, a1 asm("$5")=b, a2 asm("$6")=c;
  register long a3 asm("$7");
  asm volatile("syscall":"+r"(v0),"=r"(a3):"r"(a0),"r"(a1),"r"(a2)
    :"memory","$8","$9","$10","$11","$12","$13","$14","$15","$24","$25","hi","lo");
  return a3 ? -v0 : v0;
}

static char g_pcm[16], g_params[16];
static int g_fd = -1, g_ch = 2, g_sb = 4;
static unsigned g_rate = 48000;

static void fmt_write(void){
  long fd = sys3(__NR_open, (long)"/audio.fmt", O_WCT, 0644);
  if (fd >= 0){ unsigned r[3] = {(unsigned)g_ch,(unsigned)g_sb,g_rate}; sys3(__NR_write,fd,(long)r,sizeof r); sys3(__NR_close,fd,0,0); }
}

/* struct pcm_config: channels@0, rate@4, period_size@8, period_count@12, format@16 (u32 each) */
struct pcm *pcm_open(unsigned card, unsigned device, unsigned flags, const void *config){
  (void)card;(void)device;(void)flags;
  if (config){
    const unsigned *c = (const unsigned *)config;
    if (c[0]) g_ch = (int)c[0];
    if (c[1]) g_rate = c[1];
    unsigned fmt = c[4];                      /* tinyalsa pcm_format enum */
    /* 0 S16_LE,1 S32_LE,2 S8,3 S24_LE,4 S24_3LE (packed 3B); bytes/sample: */
    g_sb = (fmt==0)?2 : (fmt==2)?1 : (fmt==4)?3 : 4;
    fmt_write();
  }
  return (struct pcm *)g_pcm;
}
int pcm_close(struct pcm *p){ (void)p; return 0; }
int pcm_is_ready(const struct pcm *p){ (void)p; return 1; }
unsigned pcm_get_buffer_size(const struct pcm *p){ (void)p; return 8192; }
const char *pcm_get_error(const struct pcm *p){ (void)p; return ""; }

int pcm_write(struct pcm *p, const void *data, unsigned count){
  (void)p;
  if (g_fd < 0) g_fd = sys3(__NR_open, (long)"/audio.pcm", O_WCA, 0644);
  if (g_fd >= 0 && data && count){
    unsigned off = 0;
    while (off < count){
      long w = sys3(__NR_write, g_fd, (long)((const char*)data + off), count - off);
      if (w <= 0) break;
      off += (unsigned)w;
    }
  }
  return 0;
}
int pcm_read(struct pcm *p, void *data, unsigned count){ (void)p;(void)data; return (int)count; }

/* card capability query — report a permissive card so the config validation passes */
struct pcm_params *pcm_params_get(unsigned card, unsigned device, unsigned flags){ (void)card;(void)device;(void)flags; return (struct pcm_params *)g_params; }
void pcm_params_free(struct pcm_params *p){ (void)p; }
unsigned pcm_params_get_min(const struct pcm_params *p, int param){ (void)p;(void)param; return 1; }
unsigned pcm_params_get_max(const struct pcm_params *p, int param){ (void)p;(void)param; return 384000; }
