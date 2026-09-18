FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
# Reviewed whisper.cpp v1.9.4 commit, not the moving default branch.
RUN curl --fail --location --retry 3 https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/927cfce34f31707e17f2bff35c349632fb9e2c3a | tar xz --strip-components=1
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_METAL=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_CURL=OFF && cmake --build build --target whisper-server -j 4
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/whisper-server /usr/local/bin/whisper-server
COPY --from=build /src/LICENSE /usr/share/doc/whisper/LICENSE
USER 65534:65534
ENTRYPOINT ["whisper-server"]
CMD ["-m", "/models/whisper.bin", "--host", "0.0.0.0", "--port", "18119", "-ng", "-nf", "-nlp"]
