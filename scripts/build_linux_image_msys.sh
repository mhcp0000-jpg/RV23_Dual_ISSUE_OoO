#!/usr/bin/bash
# Run in the portable MSYS2 UCRT64 environment, from the RV23 workspace.
set -euo pipefail
export MSYS=winsymlinks:sys
workspace=/c/rv_workspaces/rv23
output=$workspace/out/linux_bringup
source=$output/linux-6.12
build=$output/kbuild-native
gcc=/c/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc.exe
cd "$workspace"
test -f "$source/arch/riscv/Kconfig"
mkdir -p "$build"

"$gcc" -march=rv64i -mabi=lp64 -nostdlib -static -Wl,--no-relax \
    -o "$output/init.elf" tb/fixtures/opensbi/linux_init.S
cat > "$output/initramfs.list" <<EOF
dir /dev 755 0 0
nod /dev/console 600 0 0 c 5 1
nod /dev/kmsg 600 0 0 c 1 11
file /init $output/init.elf 755 0 0
EOF

# Native Clang emits CRLF and drive-letter paths. Linux fixdep expects LF and
# POSIX paths, so normalize dependency files before Kbuild consumes them.
cat > "$output/clang-kbuild" <<'EOF'
#!/usr/bin/bash
set -e
depfile=
take_path=0
for argument in "$@"; do
    if (( take_path )); then
        depfile=$argument
        take_path=0
    else
        case "$argument" in
            -Wp,-MMD,*|-Wp,-MD,*) depfile=${argument#*,*,} ;;
            -MF) take_path=1 ;;
            -MF?*) depfile=${argument#-MF} ;;
        esac
    fi
done
/ucrt64/bin/clang.exe "$@"
if [[ -n $depfile && -f $depfile ]]; then
    sed -i -E 's/\r$//; s@(^|[[:space:]])([A-Za-z]):/@\1/\L\2\E/@g' "$depfile"
fi
EOF

# Windows LLD chooses the ELF driver when emulation is a separate argument.
cat > "$output/ld-kbuild" <<'EOF'
#!/usr/bin/bash
args=()
for argument in "$@"; do
    case "$argument" in
        -melf*) args+=(-m "${argument#-m}") ;;
        *) args+=("$argument") ;;
    esac
done
exec /ucrt64/bin/lld.exe -flavor gnu "${args[@]}"
EOF
chmod +x "$output/clang-kbuild" "$output/ld-kbuild"

make_args=(-C "$source" "O=$build" ARCH=riscv LLVM=1 HOSTCC=/usr/bin/gcc
           "CC=$output/clang-kbuild" "LD=$output/ld-kbuild" DTC=./scripts/dtc/dtc.exe -j4)
if [[ ! -f $build/.config ]]; then
    make "${make_args[@]}" tinyconfig
fi
"$source/scripts/config" --file "$build/.config" -e PRINTK -e TTY \
    -e SERIAL_EARLYCON_RISCV_SBI -e RISCV_SBI_V01 -e BINFMT_ELF -e BLK_DEV_INITRD \
    -d RISCV_ISA_V -d FPU --set-str INITRAMFS_SOURCE "$output/initramfs.list"
make "${make_args[@]}" olddefconfig
make "${make_args[@]}" Image
sha256sum "$build/arch/riscv/boot/Image"
