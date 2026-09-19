/* Typesense #2998: avoid brpc logging before main when proc I/O is absent.
 * No constructor or logging here. Only ENOENT on the exact read-only path
 * receives synthetic counters; permission errors and real data pass through.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static FILE *open_io(const char *symbol, const char *path, const char *mode) {
    FILE *(*real_open)(const char *, const char *) = dlsym(RTLD_NEXT, symbol);
    if (!real_open) {
        errno = ENOSYS;
        return NULL;
    }
    FILE *stream = real_open(path, mode);
    if (stream || errno != ENOENT || strcmp(path, "/proc/self/io") != 0 ||
        mode[0] != 'r' || strchr(mode, '+'))
        return stream;
    static char counters[] = "rchar: 0\nwchar: 0\nsyscr: 0\nsyscw: 0\n"
                             "read_bytes: 0\nwrite_bytes: 0\ncancelled_write_bytes: 0\n";
    return fmemopen(counters, sizeof(counters) - 1, "r");
}

FILE *fopen(const char *path, const char *mode) {
    return open_io("fopen", path, mode);
}

FILE *fopen64(const char *path, const char *mode) {
    return open_io("fopen64", path, mode);
}
