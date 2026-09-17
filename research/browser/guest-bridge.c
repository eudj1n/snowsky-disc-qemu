/* RISC-V host adapter inside TinyEMU: DISC framebuffer and one-at-a-time taps.
 * Firmware and existing MIPS shims stay unmodified by this adapter.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/random.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define WIDTH 360
#define FRAME_BYTES (WIDTH * WIDTH * 4)
static unsigned char frame[FRAME_BYTES], previous[FRAME_BYTES];
static pid_t ui, player;

static int write_all(int fd, const void *ptr, size_t size) {
    const unsigned char *p = ptr;
    while (size) {
        ssize_t n = write(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}

static int save(const char *path, const void *buf, size_t len) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return -1;
    int rc = write_all(fd, buf, len);
    if (close(fd)) rc = -1;
    return rc;
}

static int publish(const char *name, const void *buf, size_t len) {
    char path[128], command[128];
    snprintf(path, sizeof(path), "/exchange/%s", name);
    if (save(path, buf, len)) return -1;
    snprintf(command, sizeof(command), "export_file /%s", name);
    return save("/exchange/.fscmd", command, strlen(command));
}

static pid_t launch(const char *program, const char *log) {
    pid_t pid = fork();
    if (pid != 0) return pid;
    int fd = open(log, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0 || dup2(fd, 1) < 0 || dup2(fd, 2) < 0) _exit(126);
    if (fd > 2) close(fd);
    if (chroot("/disc") || chdir("/")) _exit(126);
    execl(program, program, (char *)NULL);
    perror("exec DISC");
    _exit(127);
}

static int input_open(pid_t pid, const char *event) {
    char path[128], link[256];
    snprintf(path, sizeof(path), "/proc/%d/fd", (int)pid);
    DIR *dir = opendir(path);
    if (!dir) return 0;
    struct dirent *entry;
    int found = 0;
    while ((entry = readdir(dir))) {
        if (entry->d_name[0] == '.') continue;
        char file[512];
        snprintf(file, sizeof(file), "%s/%s", path, entry->d_name);
        ssize_t n = readlink(file, link, sizeof(link) - 1);
        if (n < 0) continue;
        link[n] = 0;
        if (strstr(link, event)) { found = 1; break; }
    }
    closedir(dir);
    return found;
}

/* MIPS input_event uses 32-bit timeval even though this adapter is 64-bit. */
struct event32 { int32_t sec, usec; uint16_t type, code; int32_t value; };
_Static_assert(sizeof(struct event32) == 16, "MIPS input_event layout");
static int event(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct event32 e = {0, 0, type, code, value};
    return write_all(fd, &e, sizeof(e));
}

static int tap(int x, int y) {
    if (x < 0 || x >= WIDTH || y < 0 || y >= WIDTH) return -1;
    int fd = open("/disc/dev/input/event1", O_WRONLY | O_APPEND);
    if (fd < 0) return -1;
    x = WIDTH - 1 - x; y = WIDTH - 1 - y;
    int rc = event(fd, 3, 0x39, 0) || event(fd, 3, 0x35, x) ||
        event(fd, 3, 0x36, y) || event(fd, 3, 0, x) || event(fd, 3, 1, y) ||
        event(fd, 1, 0x14a, 1) || event(fd, 0, 0, 0);
    /* Separate phases so LVGL sees a press, preserving the normal tap duration. */
    usleep(300000);
    rc |= event(fd, 3, 0x39, -1) || event(fd, 1, 0x14a, 0) || event(fd, 0, 0, 0);
    close(fd);
    return rc ? -1 : 0;
}

int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    /* No physical RNG in TinyEMU. The worker supplies fresh Web Crypto entropy;
     * never bake a reusable entropy seed into the disk image. */
    struct { int entropy_count, buf_size; unsigned char data[64]; } entropy = {512, 64, {0}};
    int seeded = 0;
    for (int n = 0; n < 200; n++) {
        int fd = open("/exchange/entropy", O_RDONLY);
        if (fd >= 0) {
            ssize_t size = read(fd, entropy.data, sizeof(entropy.data));
            close(fd); unlink("/exchange/entropy");
            if (size != sizeof(entropy.data)) { fprintf(stderr, "Invalid entropy seed\n"); return 1; }
            fd = open("/dev/random", O_RDWR);
            if (fd < 0 || ioctl(fd, RNDADDENTROPY, &entropy)) { perror("RNDADDENTROPY"); return 1; }
            close(fd); memset(entropy.data, 0, sizeof(entropy.data)); seeded = 1; break;
        }
        usleep(100000);
    }
    if (!seeded) { fprintf(stderr, "Browser entropy did not arrive\n"); return 1; }
    printf("BROWSER_DISC: entropy seeded\n");
    struct rlimit limit = {RLIM_INFINITY, RLIM_INFINITY};
    if (setrlimit(RLIMIT_MSGQUEUE, &limit)) { perror("RLIMIT_MSGQUEUE"); return 1; }
    limit.rlim_cur = limit.rlim_max = 65536;
    if (setrlimit(RLIMIT_NOFILE, &limit)) { perror("RLIMIT_NOFILE"); return 1; }
    printf("BROWSER_DISC: starting mq_ui\n");
    ui = launch("/usr/bin/mq_ui", "/var/log/mq_ui.log");
    if (ui <= 0) return 1;
    sleep(4);
    printf("BROWSER_DISC: starting mq_player\n");
    player = launch("/usr/bin/mq_player", "/var/log/mq_player.log");
    if (player <= 0) { kill(ui, SIGTERM); return 1; }
    int fb = open("/disc/dev/fb0", O_RDONLY);
    if (fb < 0) { perror("framebuffer"); return 1; }
    unsigned sequence = 1, frames = 0;
    int ready = 0, failed = 0;
    for (;;) {
        int status;
        if (waitpid(ui, &status, WNOHANG) == ui || waitpid(player, &status, WNOHANG) == player) {
            char message[128];
            snprintf(message, sizeof(message), "{\"state\":\"failed\",\"waitStatus\":%d}", status);
            publish("status.json", message, strlen(message));
            printf("BROWSER_DISC: guest exited, wait status %d; inspect /var/log\n", status);
            failed = 1; break;
        }
        unsigned char active = 255;
        int marker = open("/disc/emu/fb-live", O_RDONLY);
        if (marker >= 0) { if (read(marker, &active, 1) != 1) active = 255; close(marker); }
        if (active < 2 && pread(fb, frame, sizeof(frame), (off_t)active * FRAME_BYTES) == FRAME_BYTES) {
            /* Match the viewer's last-written-buffer selection. */
            unsigned char after = 255;
            marker = open("/disc/emu/fb-live", O_RDONLY);
            if (marker >= 0) { if (read(marker, &after, 1) != 1) after = 255; close(marker); }
            if (after == active && (!frames || memcmp(previous, frame, sizeof(frame)))) {
                if (!publish("frame.bgrx", frame, sizeof(frame))) {
                    memcpy(previous, frame, sizeof(frame)); frames++;
                }
            }
            if (!ready && input_open(ui, "/dev/input/event1") && input_open(player, "/dev/input/event0")) {
                ready = 1;
                const char *s = "{\"state\":\"ready\"}";
                publish("status.json", s, strlen(s));
                printf("BROWSER_DISC: both inputs open and framebuffer live\n");
            }
        }
        if (ready) {
            char path[128];
            snprintf(path, sizeof(path), "/exchange/tap-%u", sequence);
            FILE *f = fopen(path, "r");
            if (f) {
                int x, y, rc = -1;
                char extra;
                if (fscanf(f, "%d %d %c", &x, &y, &extra) == 2) rc = tap(x, y);
                fclose(f); unlink(path);
                char message[128];
                snprintf(message, sizeof(message), "{\"state\":\"ready\",\"tap\":%u,\"ok\":%s}", sequence, rc ? "false" : "true");
                publish("status.json", message, strlen(message));
                printf("BROWSER_DISC: tap %u %s\n", sequence, rc ? "failed" : "injected");
                sequence++;
            }
        }
        usleep(200000);
    }
    kill(ui, SIGTERM); kill(player, SIGTERM); close(fb);
    return failed;
}
