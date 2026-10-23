# S9 Plus boot investigation

## 2026-10-24 — loader marker hang

- Target checkout: `port/star2lte`, based on `598af2a`. The user reports that
  their flashed image stays on the Samsung logo. The exact image hash,
  recovered boot log, and model number have not been supplied.
- Confirmed source defect: `reserve_marker()` subtracts console data base
  `0xfed1000c` from marker `0x8f0ff000`, truncates to uint32_t, and pads toward
  that invalid offset. `log_ch1()` stops advancing at the buffer limit, so
  the loop never terminates if execution reaches it before the XNU jump.
- Added full-width bounds checks and a check for logs already past the
  marker slot. Invalid slots are skipped with a diagnostic; no hardware
  address was guessed or changed. The configured entry marker remains
  unusable and must be reconciled with the kernel and actual reserved RAM.
- Validation: host harness reproduced the original hang and passed seven
  cases with the fix (current address, high address, insufficient prefix,
  valid slot, last valid slot, insufficient suffix, log past slot).
  The harness is `/workspace/.cloud-setup/check-marker.py`. Linux ARM64 GCC
  compiled all linked loader sources with `-Wall -Wextra -Werror`, linked
  the ELF, and produced an Image. No ABS64 relocations were found in its C
  objects. Build outputs are outside the checkout in
  `/workspace/.cloud-setup/star2lte-build`.
- No complete BOOT image was packaged or flashed, and no device or XNU boot
  was verified. A successful cross-build does not validate MMIO addresses.
- Outstanding: recover `/sys/fs/pstore` directly from recovery after a
  failed boot; inspect the exact stock and generated image headers and
  hashes. Early DECON/framebuffer/log writes precede the first loader text.
  Loader framebuffer is `0x10000000`, while ADT and checked-in kernel patch
  use `0xcc000000`. ADT declares GICv3 while the kernel config retains
  `HAS_GIC_V3=0`. The patch generator and checked-in patch also disagree.
  These require hardware evidence and kernel-path investigation before
  claiming a boot fix.
