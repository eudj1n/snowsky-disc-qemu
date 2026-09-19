#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void verify(FILE *(*open_file)(const char *, const char *)) {
    const char *scenario = getenv("TEST_PROC_IO");
    FILE *stream = open_file("/proc/self/io", "re");
    if (strcmp(scenario, "denied") == 0) {
        assert(!stream && errno == EACCES);
    } else {
        assert(stream);
        char buffer[256] = {0};
        size_t length = fread(buffer, 1, sizeof(buffer) - 1, stream);
        assert(length > 0 && feof(stream));
        if (strcmp(scenario, "missing") == 0) {
            assert(strcmp(buffer, "rchar: 0\nwchar: 0\nsyscr: 0\nsyscw: 0\n"
                          "read_bytes: 0\nwrite_bytes: 0\ncancelled_write_bytes: 0\n") == 0);
            FILE *other = open_file("/proc/self/io", "r");
            assert(other && fgetc(other) == 'r');
            assert(fgetc(stream) == EOF); /* Streams have independent positions. */
            rewind(stream);
            assert(fgetc(stream) == 'r');
            fclose(other);
        } else {
            assert(strcmp(buffer, "rchar: 123\n") == 0);
        }
        fclose(stream);
    }
    assert(!open_file("/disc-test-no-such-file", "r") && errno == ENOENT);
    stream = open_file("/etc/os-release", "r");
    assert(stream && fgetc(stream) != EOF);
    fclose(stream);
    if (strcmp(scenario, "missing") == 0) {
        assert(!open_file("/proc/self/io", "r+") && errno == ENOENT);
        assert(!open_file("/proc/self/io", "w") && errno == ENOENT);
    }
}

/* Exercise the workaround before main, like the failing brpc initializer. */
__attribute__((constructor)) static void before_main(void) {
    verify(fopen);
    verify(fopen64);
}

int main(void) {
    puts("proc I/O compatibility checks passed");
    return 0;
}
