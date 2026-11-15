#!/bin/bash
set -euo pipefail
compiler=/cygdrive/c/rv_toolchains/sail-0.20.3/sail/bin/sail.exe
export PATH="$(dirname "$compiler"):$PATH"
if [[ ${1:-} == --dir ]]; then
    cygpath -u "$("$compiler" --dir | tr -d '\r')"
    exit
fi
args=()
for arg in "$@"; do
    if [[ $arg == /cygdrive/* ]]; then
        args+=("$(cygpath -m "$arg")")
    else
        args+=("$arg")
    fi
done
exec "$compiler" "${args[@]}"
