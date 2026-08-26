#!/bin/sh
# Emits a clock sample for host/container skew correction, then execs the traced command.
echo "PANO_CLOCK $(date +%s.%N)" >&2
exec strace -f -ttt -yy -o /tmp/pano.strace \
  -e trace=openat,open,stat,newfstatat,readlink,execve,execveat,connect,sendto,sendmsg,bind,clone,fork \
  "$@"
