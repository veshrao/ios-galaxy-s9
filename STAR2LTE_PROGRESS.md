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

## 2026-10-24 — uploaded image and local loader sources

- Uploaded image SHA-256:
  `6248362c37f7d3938fab16f0dc9659d73dced279330472fbbded99391d63e0e5`.
  Boot-container component SHA-1, section bounds, ten payload segment
  bounds, and the embedded ADT parsed successfully. This is offline
  structural validation, not bootloader acceptance or device execution.
- Its disassembly confirms the unfixed marker loop. The user's uploaded
  loader source adds a ten-second delay and an unconditional PMU write
  labelled SYSTEM_RESET before returning the XNU entry. Integrated the
  delay, removed that reset write, and retained the marker bounds fix.
  All thirteen other uploaded loader files match the branch baseline.
- Removed the second log buffer. The bundled stock DT reserves only
  `[0xfed10000, 0xfed18000)` as `exynos_ss,log_pstore`; the original second
  buffer starts halfway through it and extends into `log_kevents`. The
  loader now uses one buffer wholly within that reservation. Compatibility
  of its DBGC format with recovery's driver remains unverified.
- All six bundled stock DTBs specify GICv2, distributor `0x10101000` and
  CPU interface `0x10102000`, both 4 KiB. Corrected the ADT compatible and
  bus-relative offsets (`0x00101000`, `0x00102000`), accounting for the
  `0x10000000` arm-io base added by `pe_init_fiq`. This supersedes the
  earlier suspicion that HAS_GIC_V3=0 was itself wrong. Do not enable
  GICv3 simply to match the previous incorrect ADT.
- Build script now selects either aarch64-elf or aarch64-linux-gnu tools,
  accepts overrides, and uses Python for Image padding/header checks and
  SHA-256 instead of platform-specific awk/stat/truncate/hash commands.
  Ignored the loader's generated out directory.
- Validation: repository build script compiled and linked the corrected
  loader and validated its ARM64 Image header; seven marker cases passed;
  generated ADT GIC addresses match all six stock DTBs after translation.
  Python (28 files) and shell (10 files) validation passed. The repository
  validator fails on the pre-existing missing patch 0124 before 0125; no
  patch renumbering was attempted.
- No framebuffer address was changed: loader/start.S use `0x10000000`,
  while ADT/kernel patch use `0xcc000000`. The uploaded boot header requests
  kernel and ramdisk addresses within the loader framebuffer clear range;
  actual S-Boot relocation remains unknown. Early cache maintenance, MMIO,
  PMIC access, RAM window and framebuffer handoff still require device
  evidence. No new BOOT image is claimed boot-ready, no flash was performed,
  and no push is authorized.

## 2026-10-24 — recovery /proc/iomem evidence

- The user supplied recovery `/proc/iomem`. It lists System RAM at
  `0x80000000..0xbc7fffff`, `0xc0000000..0xdfffffff`,
  `0xe1900000..0xff7fffff`, and `0x880000000..0x97fffffff`.
  The configured high XNU RAM bank exists; this does not establish that
  every byte is free of boot-time firmware reservations or live data.
- Loader framebuffer clear `[0x10000000, 0x11042800)` crosses registered
  watchdog, UART, I2C, SPI and USB MMIO. This is not a usable framebuffer
  interval and is an early abort/corruption candidate before the first
  console message. Do not substitute another address without evidence.
  `0xcc000000` lies in System RAM, but the map does not identify it as
  the bootloader framebuffer.
- Recovery confirms UFS HCI `0x11120000..0x111201ff` and vendor HCI
  `0x11121100..0x111212ff`, not the source's `0x11240000/0x11241100`.
  The loader UFS probe is currently bypassed; correcting its base alone
  would not verify the driver or explain the earliest display failure.
- Display DECON range `0x16030000..0x1603ffff` and SPEEDY
  `0x141c0000..0x141c1fff` are listed; that does not validate individual
  register offsets, values or boot-time clock/power state.
- The listed `gicd/gicc` at `0x17cf1000/0x17cf2000` must not be assumed
  to replace the main CPU interrupt-controller addresses established by
  the stock DT. Obtain live device-tree identity and topology first.
- Next read-only evidence: pull `/sys/firmware/fdt` from recovery. Inspect
  live `/chosen`, memory and display/reserved-memory properties. Recovery
  display handoff may still differ from S-Boot's direct BOOT handoff.
  No source hardware address was changed from this map, and no new image
  was flashed or claimed boot-ready.
