/* Calls the ALSA shim's snd_pcm_writei N times (1024 frames of its default S32_LE stereo,
   8192 bytes each) outside a guest, so a firmware-free test can read its capture file.
   Built together with asndshim.c. */
#include <stdlib.h>
long snd_pcm_writei(void *pcm, const void *buf, unsigned long size);

int main(int argc, char **argv){
  static int frames[2 * 1024];
  int i, n = argc > 1 ? atoi(argv[1]) : 1;
  for (i = 0; i < n; ++i)
    if (snd_pcm_writei(0, frames, 1024) != 1024) return 1;
  return 0;
}
