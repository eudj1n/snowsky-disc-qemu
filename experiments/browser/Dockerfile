ARG BASE_IMAGE=snowsky-disc-qemu-ci
FROM ${BASE_IMAGE}

# Build tools only. The browser runtime is a separate RISC-V Linux disk image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-riscv64-linux-gnu libc6-dev-riscv64-cross \
    e2fsprogs cpio xz-utils bc flex bison \
    && rm -rf /var/lib/apt/lists/*
