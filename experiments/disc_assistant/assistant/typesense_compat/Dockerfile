# Match the official 30.2 image's glibc baseline; compile for the native platform.
FROM ubuntu:22.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY proc_io.c .
RUN gcc -shared -fPIC -O2 -Wall -Wextra -Werror -o /proc-io-compat.so proc_io.c -ldl
COPY tests/ tests/
RUN gcc -shared -fPIC -Wall -Wextra -Werror -o /fixture.so tests/missing_io.c -ldl \
    && gcc -Wall -Wextra -Werror -o /probe tests/probe.c \
    && TEST_PROC_IO=missing LD_PRELOAD=/proc-io-compat.so:/fixture.so /probe \
    && TEST_PROC_IO=denied LD_PRELOAD=/proc-io-compat.so:/fixture.so /probe \
    && TEST_PROC_IO=present LD_PRELOAD=/proc-io-compat.so:/fixture.so /probe

FROM typesense/typesense:30.2 AS runtime
COPY --from=build /proc-io-compat.so /opt/disc/proc-io-compat.so
ENV LD_PRELOAD=/opt/disc/proc-io-compat.so

# Optional real-binary validation target; fault injection is not shipped.
FROM runtime AS verification
COPY --from=build /fixture.so /opt/disc/fixture.so
COPY tests/verify_startup.sh /opt/disc/verify_startup.sh
RUN sh /opt/disc/verify_startup.sh

FROM runtime
