#!/usr/bin/bash
# Run the separate Supm Linux bring-up build in the portable UCRT64 environment.
set -euo pipefail
export MSYS=winsymlinks:sys
workspace=/c/rv_workspaces/rv23
base=$workspace/out/linux_bringup
source=$base/linux-6.14
output=$base/supm
build=$output/kbuild-native
gcc=/c/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc.exe

cd "$workspace"
test -f "$source/arch/riscv/Kconfig"
mkdir -p "$build"
"$gcc" -march=rv64gcv -mabi=lp64 -nostdlib -static -Wl,--no-relax \
    -o "$output/init.elf" tb/fixtures/opensbi/linux_supm_init.S
cat > "$output/initramfs.list" <<EOF
dir /dev 755 0 0
nod /dev/console 600 0 0 c 5 1
nod /dev/kmsg 600 0 0 c 1 11
file /init $output/init.elf 755 0 0
EOF

# Normalize the native compiler's dependency files for MSYS fixdep.
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
    -e RISCV_ISA_V -e FPU -e RISCV_ISA_SUPM -e INITRAMFS_COMPRESSION_GZIP \
    --set-str INITRAMFS_SOURCE "$output/initramfs.list"
make "${make_args[@]}" olddefconfig
for flag in RISCV_ISA_SUPM RISCV_ISA_V FPU MMU INITRAMFS_COMPRESSION_GZIP; do
    grep -qx "CONFIG_$flag=y" "$build/.config"
done
make "${make_args[@]}" Image
sha256sum "$build/arch/riscv/boot/Image"
