FROM alpine@sha256:f271e74b17ced29b915d351685fd4644785c6d1559dd1f2d4189a5e851ef753a

RUN \
   apk add zlib-dev git alpine-sdk zlib-static lz4-static lz4-dev

RUN \
   git clone https://github.com/plougher/squashfs-tools && \
   cd squashfs-tools/squashfs-tools/ && \
   sed 's/#LZ4_SUPPORT/LZ4_SUPPORT/' -i Makefile  && \
   export EXTRA_LDFLAGS="-static" && \
   make  && make install

