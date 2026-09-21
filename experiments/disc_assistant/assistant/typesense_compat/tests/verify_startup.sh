#!/bin/sh
set -eu
ulimit -c 0
# 30.2 prints its version but still validates required config, returning 1.
# Without the shim the missing-file fixture must reproduce the earlier SIGSEGV.
result=0
TEST_PROC_IO=missing LD_PRELOAD=/opt/disc/fixture.so \
    /opt/typesense-server --version >/tmp/typesense-probe.log 2>&1 || result=$?
test "$result" -eq 139
result=0
TEST_PROC_IO=missing LD_PRELOAD=/opt/disc/proc-io-compat.so:/opt/disc/fixture.so \
    /opt/typesense-server --version >/tmp/typesense-probe.log 2>&1 || result=$?
test "$result" -eq 1
grep -q 'Typesense 30.2' /tmp/typesense-probe.log
grep -q 'Data directory is not specified' /tmp/typesense-probe.log
rm /tmp/typesense-probe.log
echo 'Typesense startup: stock SIGSEGV reproduced; shim reaches config validation'
