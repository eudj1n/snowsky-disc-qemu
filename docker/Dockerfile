# Reproducible environment for emulating the FiiO Snowsky Disc firmware
# (Ingenic X2000, MIPS32 LE) under qemu-user on any host via Docker.
#
# Build:  docker build -t diskos-qemu docker/
# Run:    see ../README.md  (needs --privileged for binfmt_misc + POSIX mqueue + qemu VA reservation)
#
# Works on both amd64 and arm64 Docker hosts (Debian is multi-arch; qemu-user-static
# runs the MIPS guest regardless of host arch).
FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      qemu-user-static \
      binfmt-support \
      squashfs-tools \
      gcc-mipsel-linux-gnu \
      binutils-mipsel-linux-gnu \
      libc6-dev-mipsel-cross \
      sqlite3 \
      dosfstools \
      sox \
      python3 \
      openssl \
      xxd \
      file \
      procps \
      util-linux \
      iproute2 \
      netcat-openbsd \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# /work holds the extracted rootfs and runtime state (mount a host dir or volume here
# so it survives container restarts). /repo is this repository (mount read-write).
WORKDIR /work

CMD ["/bin/bash"]
