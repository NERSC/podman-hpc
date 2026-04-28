FROM alpine@sha256:865b95f46d98cf867a156fe4a135ad3fe50d2056aa3f25ed31662dff6da4eb62

RUN \
   apk add zlib-dev git alpine-sdk zlib-static lz4-static lz4-dev \
   lzo-dev xz-static xz-dev zstd-dev zstd-static sed
RUN \
   git clone https://github.com/plougher/squashfs-tools && \
   cd squashfs-tools/squashfs-tools/ && \
   sed 's/#LZ4_SUPPORT/LZ4_SUPPORT/' -i Makefile  && \
   export EXTRA_LDFLAGS="-static" && \
   make  && make install

