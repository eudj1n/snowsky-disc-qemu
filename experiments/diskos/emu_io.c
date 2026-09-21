/* SPDX-License-Identifier: MIT
 * Link-time adapter for the static diskOS UI, never for installation on hardware.
 * Stock mq_player continues to use fbshim; keep its firmware binary untouched.
 * Link with -Wl,--wrap=ioctl. All non-framebuffer calls retain libc semantics.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

extern int __real_ioctl(int fd, int request, ...);

static int is_framebuffer(int fd)
{
    char path[64], target[128];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    ssize_t n = readlink(path, target, sizeof(target) - 1);
    if (n < 0) return 0;
    target[n] = 0;
    return strcmp(target, "/dev/fb0") == 0;
}

int __wrap_ioctl(int fd, int request, ...)
{
    va_list ap;
    va_start(ap, request);
    void *arg = va_arg(ap, void *);
    va_end(ap);
    if (!is_framebuffer(fd)) return __real_ioctl(fd, request, arg);
    if (!arg) { errno = EINVAL; return -1; }
    switch (request) {
    case FBIOGET_VSCREENINFO: {
        struct fb_var_screeninfo *v = arg;
        memset(v, 0, sizeof(*v));
        v->xres = v->xres_virtual = 360;
        v->yres = 360; v->yres_virtual = 1080; v->bits_per_pixel = 32;
        v->red.offset = 16; v->green.offset = 8; v->transp.offset = 24;
        v->red.length = v->green.length = v->blue.length = v->transp.length = 8;
        return 0;
    }
    case FBIOGET_FSCREENINFO: {
        struct fb_fix_screeninfo *f = arg;
        memset(f, 0, sizeof(*f));
        strcpy(f->id, "diskos-emu");
        f->smem_len = 360 * 1080 * 4;
        f->line_length = 360 * 4;
        f->visual = FB_VISUAL_TRUECOLOR;
        return 0;
    }
    case FBIOPAN_DISPLAY: {
        /* diskOS uses partial writes into page zero and pans only at startup.
         * Its direct pixel stores bypass fbshim's memcpy observation. */
        const struct fb_var_screeninfo *v = arg;
        if (v->xoffset || v->yoffset) { errno = EINVAL; return -1; }
        int marker = open("/emu/fb-live", O_WRONLY);
        if (marker < 0) return -1;
        const char page = 0;
        ssize_t n = write(marker, &page, 1);
        close(marker);
        return n == 1 ? 0 : -1;
    }
    default:
        return __real_ioctl(fd, request, arg);
    }
}
