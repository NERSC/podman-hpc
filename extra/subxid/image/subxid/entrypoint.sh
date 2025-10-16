#! /bin/sh

: "${SUBXID_OUT:=/subxid-html}"
mkdir -p $SUBXID_OUT
cp /subxid/index.html $SUBXID_OUT/

exec python3 ./generate_maps $SUBXID_OUT/subxid
