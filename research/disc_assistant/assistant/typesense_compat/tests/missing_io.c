/* Test-only procfs fault injection; never copied into the runtime image. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *fixture_open(const char *symbol, const char *path, const char *mode) {
    if (strcmp(path, "/proc/self/io") == 0) {
        const char *scenario = getenv("TEST_PROC_IO");
        if (scenario && strcmp(scenario, "present") != 0) {
            errno = strcmp(scenario, "missing") == 0 ? ENOENT : EACCES;
            return NULL;
        }
        static char actual[] = "rchar: 123\n";
        return fmemopen(actual, sizeof(actual) - 1, "r");
    }
    FILE *(*real_open)(const char *, const char *) = dlsym(RTLD_NEXT, symbol);
    return real_open(path, mode);
}

FILE *fopen(const char *path, const char *mode) {
    return fixture_open("fopen", path, mode);
}

FILE *fopen64(const char *path, const char *mode) {
    return fixture_open("fopen64", path, mode);
}
