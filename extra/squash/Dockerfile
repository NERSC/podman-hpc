FROM alpine

RUN \
   apk add zlib-dev git alpine-sdk zlib-static lz4-static lz4-dev

RUN \
   git clone https://github.com/plougher/squashfs-tools && \
   cd squashfs-tools/squashfs-tools/ && \
   sed 's/#LZ4_SUPPORT/LZ4_SUPPORT/' -i Makefile  && \
   export EXTRA_LDFLAGS="-static" && \
   make  && make install

