#!/bin/bash
# Build the Galaxy S9 Plus XNU loader (Samsung S-Boot "kernel" Image).
# Optionally pack a BOOT image: build.sh STOCK_BOOT.img PAYLOAD.bin OUT.img
# (PAYLOAD from tools/mkpayload.py; STOCK_BOOT supplies header and DTBH).
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${CROSS_COMPILE:-}" ]; then
	if command -v aarch64-elf-gcc >/dev/null 2>&1; then
		CROSS_COMPILE=aarch64-elf-
	else
		CROSS_COMPILE=aarch64-linux-gnu-
	fi
fi
CC=${CC:-${CROSS_COMPILE}gcc}
OBJCOPY=${OBJCOPY:-${CROSS_COMPILE}objcopy}
READELF=${READELF:-${CROSS_COMPILE}readelf}
NM=${NM:-${CROSS_COMPILE}nm}
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -fno-tree-loop-distribute-patterns -march=armv8-a -Wall -Wextra -Werror"
mkdir -p out
$CC $CFLAGS -c start.S -o out/start.o
$CC $CFLAGS -c loader.c -o out/loader.o
$CC $CFLAGS -c smp_probe.c -o out/smp_probe.o
$CC $CFLAGS -c ../fdt.c -o out/fdt.o
$CC $CFLAGS -c ufs_probe.c -o out/ufs_probe.o

$CC $CFLAGS -c touch_probe.c -o out/touch_probe.o
$CC $CFLAGS -c pmic.c -o out/pmic.o
$CC $CFLAGS -c display_probe.c -o out/display_probe.o
objs="out/loader.o out/fdt.o out/ufs_probe.o  out/touch_probe.o out/pmic.o out/display_probe.o"
# Runs wherever S-Boot puts it with no relocation pass.
relocs=$("$READELF" -r $objs)
abs=$(printf '%s\n' "$relocs" | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations" >&2; exit 1; }
$CC $CFLAGS -static -T loader.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	out/start.o $objs -o out/loader.elf
$OBJCOPY -O binary out/loader.elf out/Image
"$NM" out/loader.elf > out/loader.nm
python3 - <<'PY'
from pathlib import Path
import struct

symbols = [line.split() for line in Path('out/loader.nm').read_text().splitlines()]
size = int(next(fields[0] for fields in symbols if len(fields) == 3 and fields[2] == '_end'), 16)
image = Path('out/Image')
assert image.stat().st_size <= size, 'Image exceeds _end'
with image.open('r+b') as f:
    f.truncate(size)
header = image.read_bytes()[:64]
assert header[56:60] == b'ARMd', 'invalid ARM64 Image magic'
assert struct.unpack_from('<Q', header, 16)[0] == size, 'Image header size mismatch'
print(f'out/Image: {size} bytes; ARM64 Image header OK')
PY
if [ $# = 3 ]; then
	python3 ../../tools/star2lte_mkboot.py "$1" out/Image "$2" "$3"
	python3 - "$3" <<'PY'
from pathlib import Path
import hashlib
import sys
p = Path(sys.argv[1])
print(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}')
PY
fi
