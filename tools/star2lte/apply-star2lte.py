#!/usr/bin/env python3
"""Apply the Galaxy S9+ (star2lte, Exynos 9810) hardware layer to an
A5XELTE-patched xnu tree (tools/prep-xnu-tree.sh output).

The A5XELTE machine config and its guards are reused unchanged. What
differs on the S9+ is expressed as A5_* macros in A5XELTE.h, with the A5
values kept for a non-STAR2LTE build. Every replacement asserts its
expected match count. Usage: apply-star2lte.py XNU_TREE
"""

import sys
from pathlib import Path

tree = Path(sys.argv[1])


def edit(rel, pairs):
    path = tree / rel
    text = path.read_text()
    for old, new, count in pairs:
        found = text.count(old)
        if found != count:
            raise SystemExit(f'{rel}: expected {count}x {old!r}, found {found}')
        text = text.replace(old, new)
    path.write_text(text)
    print(f'edited {rel}')


edit('pexpert/pexpert/arm64/A5XELTE.h', [(
'#define A5XELTE_VTIMER_INTID         27\n',
'#define A5XELTE_VTIMER_INTID         27\n'
'\n'
'/*\n'
' * Samsung Galaxy S9+ (SM-G965F, star2lte, Exynos 9810) build of this port.\n'
' * Samsung S-Boot handoff, 26 MHz timer, Cortex-A55 boot core.\n'
' */\n'
'#define STAR2LTE                     1\n'
'#if defined(STAR2LTE)\n'
'#define A5_FB_PHYS                    0xcc000000  /* s3cfb.bootloaderfb */\n'
'#define A5_FB_WIDTH                   1440\n'
'#define A5_FB_HEIGHT                  2960\n'
'#define A5_FB_STRIDE                  5760        /* bytes per row */\n'
'#define A5_FB_2M_BLOCKS               9           /* 1440*2960*4 bytes */\n'
'#define A5_ENTRY_MARKER_PHYS          0x920ff000  /* slot in the loader\'s pstore text */\n'
'#define A5_BOOT_MPIDR                 0x000       /* first Cortex-A55 */\n'
'#define A5_KEYS_DEFAULT               1           /* S9+ keys: GPA0/GPA2 */\n'
'#define A5_TOUCH_DEFAULT              0           /* A5 ZT7538 path absent */\n'
'#define A5_KLOG_PHYS                  0xfed10000  /* TWRP ramoops pmsg zone */\n'
'#define A5_KLOG_SIZE                  0x80000\n'
'/* Samsung\'s S9 kernel DT: arch timer "use-physical-timer".\n'
' * Use the non-secure physical timer, PPI 14 = INTID 30. */\n'
'#define A5_USE_PHYS_TIMER             1\n'
'#undef A5XELTE_VTIMER_INTID\n'
'#define A5XELTE_VTIMER_INTID         30\n'
'#else\n'
'#define A5_FB_PHYS                    0x67000000\n'
'#define A5_FB_WIDTH                   1080\n'
'#define A5_FB_HEIGHT                  1920\n'
'#define A5_FB_STRIDE                  4320\n'
'#define A5_FB_2M_BLOCKS               5\n'
'#define A5_ENTRY_MARKER_PHYS          0x469ff100\n'
'#define A5_BOOT_MPIDR                 0\n'
'#define A5_KEYS_DEFAULT               1\n'
'#define A5_TOUCH_DEFAULT              1\n'
'#endif\n', 1)])

# Early assembly: entry/MMU/stage blocks are 36x21 px at x=240, rows 88..216.
stage_rows = {'0x6705d0c0': 88, '0x6707ecc0': 120, '0x670a08c0': 152,
              '0x670c24c0': 184, '0x670e40c0': 216}
pairs = [('MOV64\tx10, 0x469ff100', 'MOV64\tx10, A5_ENTRY_MARKER_PHYS', 1)]
for addr, row in stage_rows.items():
    pairs.append((f'MOV64\tx10, {addr}',
                  f'MOV64\tx10, (A5_FB_PHYS + {row} * A5_FB_STRIDE + 240 * 4)', 1))
pairs += [
    ('mov\t\tx15, #4320', 'mov\t\tx15, #A5_FB_STRIDE', 2),
    ('mov\tx15, #4320', 'mov\tx15, #A5_FB_STRIDE', 3),
    ('MOV64\tx0, 0x67000000\n\tmov\t\tx4, x0\n\tmov\t\tx5, #5\n',
     'MOV64\tx0, A5_FB_PHYS\n\tmov\t\tx4, x0\n\tmov\t\tx5, #A5_FB_2M_BLOCKS\n', 1),
    ('MOV64\tx10, 0x67000000', 'MOV64\tx10, A5_FB_PHYS', 1),
    ('mov\t\tx13, #5\nLa5_fb_attr:', 'mov\t\tx13, #A5_FB_2M_BLOCKS\nLa5_fb_attr:', 1),
    ('MOV64\tx4, 0x67000000\n\tmov\tx5, #4320',
     'MOV64\tx4, A5_FB_PHYS\n\tmov\tx5, #A5_FB_STRIDE', 1),
    ('mov\tx13, #8640', 'mov\tx13, #(2 * A5_FB_STRIDE)', 1),
    ('/* Five 2 MiB blocks map the 1080x1920 scanout buffer VA=PA.',
     '/* A5_FB_2M_BLOCKS 2 MiB blocks map the scanout buffer VA=PA.', 1),
]
edit('osfmk/arm64/start.s', pairs)

edit('osfmk/arm64/sweet_early.c', [
    ('#define A5_FB ((volatile uint32_t *)(uintptr_t)0x67000000)\n#define A5_STRIDE 1080u\n',
     '#define A5_FB ((volatile uint32_t *)(uintptr_t)A5_FB_PHYS)\n#define A5_STRIDE (A5_FB_STRIDE / 4u)\n', 1),
    ('#define A5_COLS (1080u / A5_COL_WIDTH)', '#define A5_COLS (A5_FB_WIDTH / A5_COL_WIDTH)', 1),
    ('(1920u / A5_ROW_HEIGHT)', '(A5_FB_HEIGHT / A5_ROW_HEIGHT)', 1),
    ('for (unsigned int x = 0; x < A5_STRIDE; x++) {', 'for (unsigned int x = 0; x < A5_FB_WIDTH; x++) {', 1),
])

edit('iokit/Kernel/arm/SweetFramebuffer.cpp', [
    ('#include <pexpert/pexpert.h>\n',
     '#include <pexpert/pexpert.h>\n#include <pexpert/arm64/board_config.h>\n', 1),
    ('\tfPhys = 0x67000000ULL;\n\tfWidth = 1080;\n\tfHeight = 1920;\n\tfRowBytes = 4320;\n',
     '\tfPhys = A5_FB_PHYS;\n\tfWidth = A5_FB_WIDTH;\n\tfHeight = A5_FB_HEIGHT;\n\tfRowBytes = A5_FB_STRIDE;\n', 1),
])

edit('iokit/Kernel/arm/SweetCPU.cpp', [
    ('\tuint32_t expected_mpidr = cpu->cpu_id < 4 ? cpu->cpu_id :\n\t    0x100U + cpu->cpu_id - 4;\n',
     '#if defined(STAR2LTE)\n'
     '\t/* Exynos 9810: logical 0..3 = Cortex-A55 MPIDR 0x000..0x003 (boot cluster);\n'
     '\t * logical 4..7 = Meerkat M3 MPIDR 0x100..0x103. */\n'
     '\tuint32_t expected_mpidr = cpu->cpu_id < 4 ? cpu->cpu_id :\n'
     '\t    0x100U + cpu->cpu_id - 4;\n'
     '#else\n'
     '\tuint32_t expected_mpidr = cpu->cpu_id < 4 ? cpu->cpu_id :\n'
     '\t    0x100U + cpu->cpu_id - 4;\n'
     '#endif\n', 1),
    ('\t/* The A5 ADT describes CPU0 as the boot CPU. */\n'
     '\tif (topology->boot_cpu->cpu_id != 0 || topology->boot_cpu->phys_id != 0) {\n'
     '\t\tpanic(CPU_PORT_NAME " CPU: expected boot MPIDR 0 and logical CPU 0");\n',
     '\t/* The ADT describes logical CPU 0 as the boot CPU. */\n'
     '\tif (topology->boot_cpu->cpu_id != 0 || topology->boot_cpu->phys_id != A5_BOOT_MPIDR) {\n'
     '\t\tpanic(CPU_PORT_NAME " CPU: expected boot MPIDR %#x and logical CPU 0", A5_BOOT_MPIDR);\n', 1),
])

edit('pexpert/arm/pe_serial.c', [
    ('static uint32_t fbcon_cols, fbcon_rows, fbcon_col, fbcon_row;\n',
     'static uint32_t fbcon_cols, fbcon_rows, fbcon_col, fbcon_row;\n'
     '\n'
     '#if defined(STAR2LTE)\n'
     '/*\n'
     ' * Copy of the console in TWRP\'s ramoops pmsg zone, in persistent_ram\n'
     ' * format (sig "DBGC", start, size, ring data), appended to the loader\'s\n'
     ' * text there.\n'
     ' */\n'
     '#define KLOG_CAP        (A5_KLOG_SIZE - 12)\n'
     'static volatile uint32_t *klog_hdr;\n'
     'static volatile uint8_t *klog_data;\n'
     'static uint32_t klog_start, klog_size;\n'
     'static void klog_putc(uint8_t c);\n'
     '\n'
     'static void\n'
     'klog_init(void)\n'
     '{\n'
     '\tklog_hdr = (volatile uint32_t *)ml_io_map(A5_KLOG_PHYS, A5_KLOG_SIZE);\n'
     '\tif (klog_hdr == NULL) {\n'
     '\t\treturn;\n'
     '\t}\n'
     '\tklog_data = (volatile uint8_t *)(klog_hdr + 3);\n'
     '\tif (klog_hdr[0] == 0x43474244u && klog_hdr[1] == klog_hdr[2] &&\n'
     '\t    klog_hdr[2] < KLOG_CAP - 0x10000) {\n'
     '\t\tklog_start = klog_size = klog_hdr[2];\n'
     '\t} else {\n'
     '\t\tklog_hdr[0] = 0x43474244u;\n'
     '\t\tklog_start = klog_size = 0;\n'
     '\t}\n'
     '\tconst char *banner = "\\n--- XNU console (star2lte) ---\\n";\n'
     '\tfor (; *banner; banner++) {\n'
     '\t\tklog_putc((uint8_t)*banner);\n'
     '\t}\n'
     '}\n'
     '\n'
     'static void\n'
     'klog_putc(uint8_t c)\n'
     '{\n'
     '\tif (klog_data == NULL) {\n'
     '\t\treturn;\n'
     '\t}\n'
     '\tklog_data[klog_start] = c;\n'
     '\tklog_start = (klog_start + 1) % KLOG_CAP;\n'
     '\tif (klog_size < KLOG_CAP) {\n'
     '\t\tklog_size++;\n'
     '\t}\n'
     '\tklog_hdr[1] = klog_start;\n'
     '\tklog_hdr[2] = klog_size;\n'
     '}\n'
     '#endif\n', 1),
    ('fbcon_transmit_data(uint8_t c)\n{\n',
     'fbcon_transmit_data(uint8_t c)\n{\n'
     '#if defined(STAR2LTE)\n'
     '\tklog_putc(c);\n'
     '#endif\n', 1),
    ('\tfbcon_base = (volatile uint32_t *)ml_io_map_wcomb(reg[0], reg[1]);\n',
     '\tfbcon_base = (volatile uint32_t *)ml_io_map_wcomb(reg[0], reg[1]);\n'
     '#if defined(STAR2LTE)\n'
     '\tklog_init();\n'
     '#endif\n', 1),
])

edit('osfmk/arm64/arm_vm_init.c', [
    ('\tuint64_t physmap_slide = early_random() & ARM64_PHYSMAP_SLIDE_MASK & ~((uint64_t)PAGE_MASK);\n',
     '#if defined(STAR2LTE)\n'
     '\tuint64_t physmap_slide = 0;\n'
     '#else\n'
     '\tuint64_t physmap_slide = early_random() & ARM64_PHYSMAP_SLIDE_MASK & ~((uint64_t)PAGE_MASK);\n'
     '#endif\n', 1),
    ('\tva_l1_end += round_page(args->Video.v_height * args->Video.v_rowBytes);\n',
     '\tva_l1_end += round_page(args->Video.v_height * args->Video.v_rowBytes);\n'
     '#if defined(STAR2LTE)\n'
     '\tva_l1_end += round_page((vm_size_t)A5_FB_STRIDE * A5_FB_HEIGHT) + (64ULL << 20);\n'
     '#endif\n', 1),
    ('\tphysmap_base += physmap_slide;\n',
     '\tphysmap_base += physmap_slide;\n'
     '#if defined(STAR2LTE) && !XNU_MONITOR\n'
     '\tphysmap_base = ROUND_TWIG(physmap_base);\n'
     '#endif\n', 1),
])

edit('osfmk/vm/vm_resident.c', [
    ('\tpmap_startup(&virtual_space_start, &virtual_space_end);\n',
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tkprintf("A5 vm: vm_page_bootstrap -> pmap_startup\\n");\n'
     '#endif\n'
     '\tpmap_startup(&virtual_space_start, &virtual_space_end);\n', 1),
    ('\tvm_pages = (vm_page_t) pmap_steal_freeable_memory(npages * sizeof *vm_pages);\n',
     '\tvm_pages = (vm_page_t) pmap_steal_freeable_memory(npages * sizeof *vm_pages);\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tkprintf("A5 vm: npages=%u vm_pages=%p mem_sz=%#llx\\n", npages, vm_pages, (unsigned long long)mem_sz);\n'
     '#endif\n', 1),
    ('\t\tif (!pmap_next_page(&phys_page)) {\n\t\t\tbreak;\n\t\t}\n\n\t\tif (phys_page < max_valid_low_ppnum) {\n',
     '\t\tif (!pmap_next_page(&phys_page)) {\n\t\t\tbreak;\n\t\t}\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\t\tif ((i & 0x7fff) == 0) {\n'
     '\t\t\tkprintf("A5 vm: page %u ppn %#x\\n", i, phys_page);\n'
     '\t\t}\n'
     '#endif\n'
     '\n\t\tif (phys_page < max_valid_low_ppnum) {\n', 1),
    ('\tvm_page_pages = vm_pages_count; /* used to report to user space */\n',
     '\tvm_page_pages = vm_pages_count; /* used to report to user space */\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tkprintf("A5 vm: %u pages initialized, releasing\\n", vm_pages_count);\n'
     '#endif\n', 1),
])

# ---- Galaxy S9+ internal UFS: Exynos 9810 quirks ----
edit('bsd/dev/sweet_ufs.c', [
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\n#include <sys/param.h>\n',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '#include <sys/param.h>\n', 1),
    ('#define CAP_64AS        (1u << 24)              /* 64-bit DMA addressing */\n',
     '#define CAP_64AS        (1u << 24)              /* 64-bit DMA addressing */\n'
     '\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '/*\n'
     ' * Galaxy S9+ (Exynos 9810) host.\n'
     ' */\n'
     '#define EXYNOS_UFS              1\n'
     '#define VS_UTRL_NEXUS_TYPE      0x40\n'
     '#define UFS_WLUN_DEVICE         0xd0\n'
     '#define UFS_ADT_NODE            "/star2lte-ufs"\n'
     '#define UFS_DEFAULT_PART        "USERDATA"\n'
     '#define PRDT_BYTES(field)       (field)\n'
     '#else\n'
     '#define UFS_ADT_NODE            "/sweet-ufs"\n'
     '#define UFS_DEFAULT_PART        "userdata"\n'
     '#define PRDT_BYTES(field)       ((field) * 16u)\n'
     '#endif\n', 1),
    ('#define PRDT_CHUNK      (256u << 10)            /* PRDT byte count field: 18 bits */\n',
     '#if defined(EXYNOS_UFS)\n'
     '#define PRDT_CHUNK      4096u                   /* HCI_TXPRDT_ENTRY_SIZE 12 */\n'
     '#else\n'
     '#define PRDT_CHUNK      (256u << 10)            /* PRDT byte count field: 18 bits */\n'
     '#endif\n', 1),
    ('\tvm_offset_t regs;\n',
     '\tvm_offset_t regs;\n\tvm_offset_t vs_regs;                    /* Exynos vendor HCI registers */\n', 1),
    ('\tutrd->resp = (512u / 4) << 16 | (512u / 4);\n',
     '#if defined(EXYNOS_UFS)\n'
     '\tutrd->resp = 512u << 16 | 512u;\n'
     '#else\n'
     '\tutrd->resp = (512u / 4) << 16 | (512u / 4);\n'
     '#endif\n', 1),
    ('\t\tutrd->prdt = (1024u / 4) << 16 | n;\n',
     '#if defined(EXYNOS_UFS)\n'
     '\t\tutrd->prdt = 1024u << 16 | (n * (uint32_t)sizeof(ucd->prdt[0]));\n'
     '#else\n'
     '\t\tutrd->prdt = (1024u / 4) << 16 | n;\n'
     '#endif\n', 1),
    ('\t\t\t    (utrd->prdt & 0xffff) * sizeof(ucd->prdt[0]));\n',
     '\t\t\t    PRDT_BYTES(utrd->prdt & 0xffff));\n', 1),
    ('\tufs_wr(REG_UTRLDBR, 1);\n',
     '#if defined(EXYNOS_UFS)\n'
     '\t*(volatile uint32_t *)(su.vs_regs + VS_UTRL_NEXUS_TYPE) |= 1;  /* slot 0: SCSI */\n'
     '#endif\n'
     '\tufs_wr(REG_UTRLDBR, 1);\n', 1),
    ('\t\t\tufs_wr(REG_UTRLCLR, ~1u);\n',
     '#if !defined(EXYNOS_UFS)\n'
     '\t\t\tufs_wr(REG_UTRLCLR, ~1u);\n'
     '#endif\n', 1),
    ('\tif (!(hce & 1) || !(hcs & HCS_DP) || !(hcs & HCS_UTRLRDY)) {\n',
     '#if defined(EXYNOS_UFS)\n'
     '\t(void)hce;\n'
     '\tif (!(hcs & HCS_DP) || !(hcs & HCS_UTRLRDY)) {\n'
     '#else\n'
     '\tif (!(hce & 1) || !(hcs & HCS_DP) || !(hcs & HCS_UTRLRDY)) {\n'
     '#endif\n', 1),
    ('\tchar want[64] = "userdata";\n', '\tchar want[64] = UFS_DEFAULT_PART;\n', 1),
    ('\tif (SecureDTLookupEntry(NULL, "/sweet-ufs", &node) != kSuccess ||\n'
     '\t    SecureDTGetProperty(node, "reg", (void const **)&reg, &size) != kSuccess ||\n'
     '\t    size < 2 * sizeof(uintptr_t)) {\n'
     '\t\tprintf("SWEET UFS: no /sweet-ufs node in the device tree\\n");\n',
     '\tif (SecureDTLookupEntry(NULL, UFS_ADT_NODE, &node) != kSuccess ||\n'
     '\t    SecureDTGetProperty(node, "reg", (void const **)&reg, &size) != kSuccess ||\n'
     '#if defined(EXYNOS_UFS)\n'
     '\t    size < 4 * sizeof(uintptr_t)) {\n'
     '#else\n'
     '\t    size < 2 * sizeof(uintptr_t)) {\n'
     '#endif\n'
     '\t\tprintf("SWEET UFS: no " UFS_ADT_NODE " node in the device tree\\n");\n', 1),
    ('\tsu.regs = ml_io_map(reg[0], reg[1]);\n',
     '\tsu.regs = ml_io_map(reg[0], reg[1]);\n'
     '#if defined(EXYNOS_UFS)\n'
     '\tsu.vs_regs = ml_io_map(reg[2], reg[3]);\n'
     '#endif\n', 1),
    ('\terror = ufs_take_over_host();\n',
     '\terror = ufs_take_over_host();\n'
     '#if defined(EXYNOS_UFS)\n'
     '\tif (!error) {\n'
     '\t\tstatic const uint8_t ssu_active[6] = { 0x1b, 0, 0, 0, 0x10, 0 };\n'
     '\t\tsu.lun = UFS_WLUN_DEVICE;\n'
     '\t\terror = ufs_scsi(ssu_active, sizeof(ssu_active), 0, false);\n'
     '\t\tsu.lun = 0;\n'
     '\t\tprintf("SWEET UFS: START STOP UNIT (ACTIVE) to the device W-LUN: %d\\n", error);\n'
     '\t}\n'
     '#endif\n', 1),
    ('\tsweet_sample_start();\n\t/* Input drivers (HID services in iokit/Kernel/arm/hid/SweetHID.cpp). */\n'
     '\tsweet_keys_init();\n\tsweet_touch_init();\n\tsweet_usb_probe();\n',
     '\tsweet_sample_start();\n'
     '#if defined(ARM64_BOARD_CONFIG_SWEET)\n'
     '\t/* Input drivers (HID services in iokit/Kernel/arm/hid/SweetHID.cpp). */\n'
     '\tsweet_keys_init();\n\tsweet_touch_init();\n\tsweet_usb_probe();\n'
     '#endif\n', 1),
])

edit('bsd/dev/sweet_sample.c', [
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\n/*\n * SWEET process sampler',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\n/*\n * SWEET process sampler', 1),
])

edit('iokit/bsddev/IOKitBSDInit.cpp', [
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\n//\n//\tSWEET: root on a GPT partition of the internal UFS (bsd/dev/sweet_ufs.c)\n',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\n//\n'
     '//\tSWEET / Galaxy S9+: root on a GPT partition of the internal UFS (bsd/dev/sweet_ufs.c)\n', 1),
])

edit('osfmk/console/serial_console.c', [
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\nextern void sweet_log_append',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\nextern void sweet_log_append', 1),
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\n\tsweet_log_append(c, size);',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\n\tsweet_log_append(c, size);', 1),
])

edit('osfmk/arm64/machine_routines.c', [
    ('\t\t__builtin_arm_wsr64("CNTV_TVAL_EL0", (uint64_t)dec_value);\n',
     '#if defined(A5_USE_PHYS_TIMER)\n'
     '\t\t__builtin_arm_wsr64("CNTP_TVAL_EL0", (uint64_t)dec_value);\n'
     '#else\n'
     '\t\t__builtin_arm_wsr64("CNTV_TVAL_EL0", (uint64_t)dec_value);\n'
     '#endif\n', 1),
    ('\t\twide_val = __builtin_arm_rsr64("CNTV_TVAL_EL0");\n',
     '#if defined(A5_USE_PHYS_TIMER)\n'
     '\t\twide_val = __builtin_arm_rsr64("CNTP_TVAL_EL0");\n'
     '#else\n'
     '\t\twide_val = __builtin_arm_rsr64("CNTV_TVAL_EL0");\n'
     '#endif\n', 1),
    ('\tuint64_t cntv_ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");\n',
     '#if defined(A5_USE_PHYS_TIMER)\n'
     '\tuint64_t cntv_ctl = __builtin_arm_rsr64("CNTP_CTL_EL0");\n'
     '#else\n'
     '\tuint64_t cntv_ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");\n'
     '#endif\n', 1),
    ('\t__builtin_arm_wsr64("CNTV_CTL_EL0", cntvctl);\n'
     '\t/* disable the physical timer as a precaution, as its registers reset to architecturally unknown values */\n'
     '\t__builtin_arm_wsr64("CNTP_CTL_EL0", CNTP_CTL_EL0_IMASKED);\n',
     '#if defined(A5_USE_PHYS_TIMER)\n'
     '\t__builtin_arm_wsr64("CNTP_CTL_EL0", cntvctl);   /* same ENABLE bit */\n'
     '\t__builtin_arm_wsr64("CNTP_CTL_EL0", CNTP_CTL_EL0_IMASKED);\n'
     '#else\n'
     '\t__builtin_arm_wsr64("CNTV_CTL_EL0", cntvctl);\n'
     '\t/* disable the physical timer as a precaution, as its registers reset to architecturally unknown values */\n'
     '\t__builtin_arm_wsr64("CNTP_CTL_EL0", CNTP_CTL_EL0_IMASKED);\n'
     '#endif\n', 1),
])

edit('pexpert/arm/pe_fiq.c', [
    ('\t    a5_gic_read32(a5_gicd_base, 0x080) | (1U << 27) | (1U << 1));\n',
     '\t    a5_gic_read32(a5_gicd_base, 0x080) | (1U << A5XELTE_VTIMER_INTID) | (1U << 1));\n', 1),
    ('\ta5_gic_write32(a5_gicd_base, 0x100, (1U << 27) | (1U << 1));\n',
     '\ta5_gic_write32(a5_gicd_base, 0x100, (1U << A5XELTE_VTIMER_INTID) | (1U << 1));\n', 1),
])

edit('iokit/Kernel/arm/SweetFramebuffer.cpp', [
    ('#if !defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tif (!native && fWidth <= SWEET_FB_LOGICAL_W && fHeight <= SWEET_FB_LOGICAL_H) {\n',
     '#if defined(STAR2LTE)\n'
     '\tif (!native) {\n'
     '\t\tfLogicalW = SWEET_FB_LOGICAL_W;\n'
     '\t\tfLogicalH = SWEET_FB_LOGICAL_H;\n'
     '\t}\n'
     '#elif !defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tif (!native && fWidth <= SWEET_FB_LOGICAL_W && fHeight <= SWEET_FB_LOGICAL_H) {\n', 1),
])

edit('iokit/KernelConfigTables.cpp', [
    ("    \"     'IONameMatch'     = 'samsung,a5xelte-display';\"\n",
     "    \"     'IONameMatch'     = ('samsung,a5xelte-display', 'samsung,star2lte-display');\"\n", 1),
    ("    \"     'IONameMatch'     = 'samsung,a5xelte';\"\n",
     "    \"     'IONameMatch'     = ('samsung,a5xelte', 'samsung,star2lte');\"\n", 1),
])

edit('bsd/dev/a5xelte_touch.c', [
    ('#include <pexpert/pexpert.h>\n',
     '#include <pexpert/pexpert.h>\n#include <pexpert/arm64/board_config.h>\n', 1),
    ('a5xelte_touch_probe(void)\n{\n\tint enabled = 1;\n',
     'a5xelte_touch_probe(void)\n{\n\tint enabled = A5_TOUCH_DEFAULT; /* A5 touch: off on S9+ */\n', 1),
])

edit('iokit/Kernel/IOPlatformExpert.cpp', [
    ('\tif (gIOPlatform) {\n\t\tgIOPlatform->getUTCTimeOfDay(secs, &nsecs);\n\t}\n\n\tassert(nsecs < NSEC_PER_SEC);\n',
     '\tif (gIOPlatform) {\n\t\tgIOPlatform->getUTCTimeOfDay(secs, &nsecs);\n\t}\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tuint64_t s8rtc = 0;\n'
     '\tif (*secs == 0 && PE_parse_boot_argn("s8rtc", &s8rtc, sizeof(s8rtc)) && s8rtc) {\n'
     '\t\tuint64_t ns;\n'
     '\t\tabsolutetime_to_nanoseconds(mach_absolute_time(), &ns);\n'
     '\t\t*secs = (clock_sec_t)(s8rtc + ns / NSEC_PER_SEC);\n'
     '\t\tnsecs = (clock_nsec_t)(ns % NSEC_PER_SEC);\n'
     '\t}\n'
     '#endif\n\n\tassert(nsecs < NSEC_PER_SEC);\n', 1),
    ('#include <pexpert/pexpert.h>\n#include <uuid/uuid.h>\n',
     '#include <pexpert/pexpert.h>\n#include <uuid/uuid.h>\n#include <kern/clock.h>\n'
     '#include <mach/mach_time.h>\n', 1),
])

edit('iokit/Kernel/arm/SweetFramebuffer.cpp', [
    ('\tuint32_t      fFadeStep;      /* fade-out steps done while off */\n',
     '\tuint32_t      fFadeStep;      /* fade-out steps done while off */\n'
     '\tIOLock       *fPresentLock;   /* one panel copy at a time */\n'
     '\tuint64_t      fLastPresent;   /* mach_absolute_time of the last copy */\n'
     '\tuint64_t      fMinGap;        /* 1/hz in timebase ticks */\n', 1),
    ('\tfFlushTicks = (hz == 0 || hz >= 60) ? 1 : 60 / hz;\n',
     '\tfFlushTicks = (hz == 0 || hz >= 60) ? 1 : 60 / hz;\n'
     '\tfMinGap = 26000000ULL / (hz == 0 ? 60 : hz);     /* 26 MHz timebase */\n'
     '\tfPresentLock = IOLockAlloc();\n'
     '\tif (fPresentLock == NULL) {\n'
     '\t\treturn false;\n'
     '\t}\n', 1),
    ('\tmemcpy(fPending, rec, SWEET_FB_SWAP_REC_SIZE);\n\tfDirty = true;\n\tIOLockUnlock(fLock);\n',
     '\tmemcpy(fPending, rec, SWEET_FB_SWAP_REC_SIZE);\n\tfDirty = true;\n'
     '\tuint64_t now = mach_absolute_time();\n'
     '\tbool copyNow = !fPowerOff && now - fLastPresent >= fMinGap;\n'
     '\tif (copyNow) {\n'
     '\t\tfDirty = false;\n'
     '\t\tfLastPresent = now;\n'
     '\t}\n'
     '\tIOLockUnlock(fLock);\n'
     '\tif (copyNow) {\n'
     '\t\tpresent(rec);\n'
     '\t}\n', 1),
    ('\tuint32_t mask = get32(rec, 0x104);\n',
     '\tuint32_t mask = get32(rec, 0x104);\n\tIOLockLock(fPresentLock);\n'
     '#if defined(STAR2LTE)\n\tsweet_fb_wait_frame_done();\n#endif\n', 1),
    ('static uint32_t sweet_fb_swaps_logged;\n',
     '#if defined(STAR2LTE)\n'
     '/* Exynos 9810 DECON frame done wait */\n'
     'extern "C" vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);\n'
     'static vm_offset_t sweet_fb_decon;\n'
     '\n'
     'static void\n'
     'sweet_fb_wait_frame_done(void)\n'
     '{\n'
     '\tif (sweet_fb_decon == 0) {\n'
     '\t\tsweet_fb_decon = ml_io_map(0x14040000, 0x1000); /* Exynos 9810 DECON */\n'
     '\t\tif (sweet_fb_decon == 0) {\n'
     '\t\t\treturn;\n'
     '\t\t}\n'
     '\t\t*(volatile uint32_t *)(sweet_fb_decon + 0x40) |= (1u << 13) | 1u;\n'
     '\t}\n'
     '\tvolatile uint32_t *pend = (volatile uint32_t *)(sweet_fb_decon + 0x4c);\n'
     '\t*pend = 1u << 13;\n'
     '\tfor (int i = 0; i < 200 && !(*pend & (1u << 13)); i++) {\n'
     '\t\tIODelay(100);\n'
     '\t}\n'
     '}\n'
     '#endif\n'
     '\n'
     'static uint32_t sweet_fb_swaps_logged;\n', 1),
    ('\t\ts->release();\n\t}\n}\n',
     '\t\ts->release();\n\t}\n\tIOLockUnlock(fPresentLock);\n}\n', 1),
])

# Battery: Galaxy S9+ battery is 3500 mAh
edit('iokit/Kernel/arm/SweetBattery.cpp', [
    ('#if defined(ARM64_BOARD_CONFIG_SWEET)\n#include <device/device_types.h>',
     '#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '#include <device/device_types.h>', 1),
    ('/* bsd/dev/sweet_spmi.c */\n'
     'extern "C" int sweet_spmi_init(void);\n'
     'extern "C" int sweet_spmi_read(unsigned sid, unsigned addr, uint8_t *out);\n',
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '/* Galaxy S9+: fuel gauge */\n'
     'extern "C" int dreamlte_battery_read(unsigned *percent, unsigned *mv, int *ma,\n'
     '    int *external, int *charging, int *full);\n'
     'static inline int sweet_spmi_init(void) { return -1; }\n'
     'static inline int sweet_spmi_read(unsigned, unsigned, uint8_t *) { return -1; }\n'
     '#define SWEET_BAT_MAH 3500u\n'
     '#else\n'
     '/* bsd/dev/sweet_spmi.c */\n'
     'extern "C" int sweet_spmi_init(void);\n'
     'extern "C" int sweet_spmi_read(unsigned sid, unsigned addr, uint8_t *out);\n'
     '#define SWEET_BAT_MAH 5020u\n'
     '#endif\n', 1),
    ('5020u * percent', 'SWEET_BAT_MAH * percent', 1),
    ('setMaxCapacity(5020)', 'setMaxCapacity(SWEET_BAT_MAH)', 1),
    ('"AppleRawMaxCapacity", 5020)', '"AppleRawMaxCapacity", SWEET_BAT_MAH)', 1),
    ('"DesignCapacity", 5020)', '"DesignCapacity", SWEET_BAT_MAH)', 1),
    ('{capacity, 5020, mv', '{capacity, SWEET_BAT_MAH, mv', 1),
    ('void\nSweetBattery::poll(void)\n{\n',
     'void\nSweetBattery::poll(void)\n{\n'
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n'
     '\tunsigned pct = 0, s8mv = 0;\n'
     '\tint s8ma = 0, ext = 0, chg = 0, full = 0;\n'
     '\tif (fReal && dreamlte_battery_read(&pct, &s8mv, &s8ma, &ext, &chg, &full) == 0) {\n'
     '\t\tpublish(full ? 100 : pct, s8mv, s8ma, ext != 0, ext != 0, chg != 0, full != 0, true, true);\n'
     '\t} else {\n'
     '\t\tpublish(100, 4200, 0, true, true, false, true, false, false);\n'
     '\t}\n'
     '#else\n', 1),
    ('\t    charging, full, true, currentValid);\n}\n',
     '\t    charging, full, true, currentValid);\n#endif\n}\n', 1),
    ('\tint real = 0;\n\t(void)PE_parse_boot_argn("sweetbattery"',
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n\tint real = 1;\n#else\n\tint real = 0;\n#endif\n'
     '\t(void)PE_parse_boot_argn("sweetbattery"', 1),
    ('\tfReal = real == 1 && sweet_spmi_init() == 0;\n',
     '#if defined(ARM64_BOARD_CONFIG_A5XELTE)\n\tfReal = real == 1;\n#else\n'
     '\tfReal = real == 1 && sweet_spmi_init() == 0;\n#endif\n', 1),
    ('measured ? "PM6150 / estimated SOC" : "static fallback"',
     'measured ? "fuel gauge" : "static fallback"', 1),
])

edit('iokit/KernelConfigTables.cpp', [
    ('#if !defined(ARM64_BOARD_CONFIG_A5XELTE)\n    "   {"\n    "     \'IOClass\'         = SweetBattery;"',
     '#if !defined(ARM64_BOARD_CONFIG_A5XELTE) || 1  /* S9+: fuel gauge */\n    "   {"\n'
     '    "     \'IOClass\'         = SweetBattery;"', 1),
])

# S9+ S6SY761 touch driver stub
edit('bsd/dev/a5xelte_touch.c', [
    ('void\na5xelte_touch_probe(void)\n{\n',
     (Path(__file__).parent / 'dreamlte_touch.c').read_text() +
     'void\na5xelte_touch_probe(void)\n{\n'
     '#if defined(STAR2LTE)\n\tdreamlte_touch_start();   /* the A5 path below stays off */\n#endif\n', 1),
])

# Secondary CPUs for Exynos 9810 (PMU at 0x11860000)
edit('iokit/Kernel/arm/SweetCPU.cpp', [
    ('#include <pexpert/pexpert.h>\n',
     '#include <pexpert/pexpert.h>\n'
     '#if defined(STAR2LTE)\n'
     'extern "C" vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);\n'
     '#endif\n', 1),
    ('\tif (start_paddr != 0 || arg_paddr != 0 || cpu->phys_id == 0 ||\n',
     '\tif (start_paddr != 0 || arg_paddr != 0 || cpu->phys_id == A5_BOOT_MPIDR ||\n', 1),
    ('\t__builtin_arm_dsb(DSB_SY);\n\tint32_t rc = sweet_psci_cpu_on(cpu->phys_id, entry, getCPUNumber());\n',
     '#if defined(STAR2LTE)\n'
     '\t{\n'
     '\t\tstatic vm_offset_t tramp;\n'
     '\t\tconst uint64_t tramp_pa = 0x8f000000ULL;\n'
     '\t\tif (tramp == 0) {\n'
     '\t\t\ttramp = ml_io_map(tramp_pa, 0x1000);\n'
     '\t\t}\n'
     '\t\tvolatile uint32_t *t = (volatile uint32_t *)tramp;\n'
     '\t\tt[0] = 0x58000041;              /* ldr x1, #8 */\n'
     '\t\tt[1] = 0xd61f0020;              /* br x1 */\n'
     '\t\tt[2] = (uint32_t)entry;\n'
     '\t\tt[3] = (uint32_t)((uint64_t)entry >> 32);\n'
     '\t\t__builtin_arm_dsb(DSB_SY);\n'
     '\t\tIOLog(CPU_PORT_NAME " CPU: cpu=%u entry 0x%llx via low trampoline 0x%llx\\n",\n'
     '\t\t    getCPUNumber(), (uint64_t)entry, tramp_pa);\n'
     '\t\tentry = (vm_offset_t)tramp_pa;\n'
     '\t\tstatic vm_offset_t pmu;\n'
     '\t\tif (pmu == 0) {\n'
     '\t\t\tpmu = ml_io_map(0x11860000, 0x10000); /* Exynos 9810 PMU */\n'
     '\t\t}\n'
     '\t\tuint32_t off = 0x2000 + (uint32_t)(((((cpu->phys_id >> 8) & 0xf) << 2) |\n'
     '\t\t    (cpu->phys_id & 0xf)) * 0x80);\n'
     '\t\tvolatile uint32_t *cfg = (volatile uint32_t *)(pmu + off);\n'
     '\t\tcfg[0] &= ~0xfu;\n'
     '\t\tfor (int i = 0; i < 10000 && (cfg[1] & 0xf) != 0; i++) {\n'
     '\t\t\tIODelay(1);\n'
     '\t\t}\n'
     '\t\t__builtin_arm_dsb(DSB_SY);\n'
     '\t\tint32_t rc0 = sweet_psci_cpu_on(cpu->phys_id, entry, getCPUNumber());\n'
     '\t\tcfg[0] |= 0xf;\n'
     '\t\tfor (int i = 0; i < 10000 && (cfg[1] & 0xf) != 0xf; i++) {\n'
     '\t\t\tIODelay(1);\n'
     '\t\t}\n'
     '\t\tIOLog(CPU_PORT_NAME " CPU: cpu=%u first CPU_ON rc=%d, PMU power-up cfg=0x%x status=0x%x\\n",\n'
     '\t\t    getCPUNumber(), rc0, cfg[0], cfg[1]);\n'
     '\t}\n'
     '#endif\n'
     '\t__builtin_arm_dsb(DSB_SY);\n\tint32_t rc = sweet_psci_cpu_on(cpu->phys_id, entry, getCPUNumber());\n', 1),
])

# Hardware keys on Exynos 9810 (pinctrl ALIVE at 0x11830000)
edit('bsd/dev/a5xelte_keys.c', [
    ('#include <pexpert/pexpert.h>\n',
     '#include <pexpert/pexpert.h>\n#include <pexpert/arm64/board_config.h>\n', 1),
    ('#define A5_ALIVE_PA 0x139b0000u\n',
     '#if defined(STAR2LTE)\n'
     '#define A5_ALIVE_PA 0x11830000u            /* Exynos 9810 pinctrl ALIVE */\n'
     '#else\n'
     '#define A5_ALIVE_PA 0x139b0000u\n'
     '#endif\n', 1),
    ('static void\na5_keys_wait(void)\n',
     '#if defined(STAR2LTE)\n'
     'typedef uint16_t keys_t;\n'
     '#define KEYS_SAMPLE() ((keys_t)((a5_keys_read(0x24) & 0xff) | (a5_keys_read(0x64) & 0xff) << 8))\n'
     '#define KEYS_PINS { 12, 3, 4, 6 }\n'
     '#else\n'
     'typedef uint8_t keys_t;\n'
     '#define KEYS_SAMPLE() ((keys_t)a5_keys_read(A5_GPA2_DAT))\n'
     '#define KEYS_PINS { 7, 0, 1, 5 }\n'
     '#endif\n'
     '\n'
     'static void\na5_keys_wait(void)\n', 1),
    ('\tstatic const uint8_t pins[4] = {7, 0, 1, 5};\n'
     '\tuint8_t stable = (uint8_t)a5_keys_read(A5_GPA2_DAT);\n'
     '\tuint8_t previous = stable;\n',
     '\tstatic const uint8_t pins[4] = KEYS_PINS;\n'
     '\tkeys_t stable = KEYS_SAMPLE();\n'
     '\tkeys_t previous = stable;\n', 1),
    ('\t\tuint8_t sample = (uint8_t)a5_keys_read(A5_GPA2_DAT);\n',
     '\t\tkeys_t sample = KEYS_SAMPLE();\n', 1),
    ('\t\t\t\tuint8_t bit = 1u << pins[key];\n',
     '\t\t\t\tkeys_t bit = (keys_t)(1u << pins[key]);\n', 1),
    ('\tint enabled = 1;\n\tif (a5_keys_started) {',
     '\tint enabled = A5_KEYS_DEFAULT;\n\tif (a5_keys_started) {', 1),
])
