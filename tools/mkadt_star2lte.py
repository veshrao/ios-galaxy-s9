"""Build the Galaxy S9+ (SM-G965F, star2lte, Exynos 9810) ADT.
Starts from the donor schema like tools/mkadt_a5xelte.py and replaces the
board facts with the S9+'s:
  - XNU RAM: the 2 GiB bank 0x880000000-0x8ffffffff, free of firmware carve-outs
  - Stock DT GICv2: distributor 0x10101000, CPU interface 0x10102000
  - timer 26 MHz
  - CPUs: logical 0-3 = Cortex-A55 MPIDR 0x000-0x003 (S-Boot boots 0x000),
    logical 4-7 = Meerkat M3 MPIDR 0x100-0x103
  - S-Boot framebuffer 1440x2960 XRGB8888 at 0xcc000000
"""

import argparse
import os
from pathlib import Path
import adt
import mkadt

DRAM_BASE = 0x880000000
# 512 MiB, the A5XELTE-proven size
DRAM_SIZE = 0x20000000
FB_PHYS, FB_W, FB_H = 0xcc000000, 1440, 2960
TIMEBASE = 26000000

def set_prop(node, name, value):
    for i, (key, flags, _) in enumerate(node.props):
        if key == name:
            node.props[i] = (key, flags, value)
            return
    node.props.append((name, 0, value))

def child(node, name):
    for candidate in node.children:
        if candidate.prop('name') == mkadt.cstr(name):
            return candidate
    raise ValueError(f'missing donor ADT node {name}')

def cpu_node(logical):
    a55 = logical < 4
    mpidr = logical if a55 else 0x100 + (logical - 4)
    cluster = 0 if a55 else 1
    return [
        ('device_type', mkadt.cstr('cpu')),
        ('compatible', mkadt.cstr('arm,cortex-a55' if a55 else 'samsung,meerkat-m3') +
         mkadt.cstr('ARM,v8')),
        ('reg', mkadt.u32(mpidr)),
        ('cpu-id', mkadt.u32(logical)),
        ('cluster-id', mkadt.u32(cluster)),
        ('cluster-type', mkadt.u32(0)),
        ('die-cluster-id', mkadt.u32(cluster)),
        ('cluster-core-id', mkadt.u32(logical % 4)),
        ('l2-cache-id', mkadt.u32(cluster)),
        ('l3-cache-id', mkadt.u32(0)),
        ('state', mkadt.cstr('running' if logical == 0 else 'stopped')),
        ('timebase-frequency', mkadt.u32(TIMEBASE)),
        ('clock-frequency', mkadt.u32(1790000000 if a55 else 2700000000)),
        ('bus-frequency', mkadt.u32(100000000)),
        ('memory-frequency', mkadt.u32(1794000000)),
        ('peripheral-frequency', mkadt.u32(TIMEBASE)),
        ('fixed-frequency', mkadt.u32(TIMEBASE)),
    ]

def build(canvas=(FB_W, FB_H)):
    root = mkadt.build(seed=os.urandom(64), qemu=True)
    
    # Platform Expert matching compatible strings
    set_prop(root, 'compatible', mkadt.cstr('samsung,star2lte') +
             mkadt.cstr('samsung,a5xelte') + mkadt.cstr('samsung,exynos9810') +
             mkadt.cstr('AppleARM'))
    
    chosen = child(root, 'chosen')
    set_prop(chosen, 'dram-base', mkadt.u64(DRAM_BASE))
    set_prop(chosen, 'dram-size', mkadt.u64(DRAM_SIZE))
    set_prop(chosen, 'firmware-version', mkadt.cstr('star2lte-entry'))
    set_prop(chosen, 'system-firmware-version', mkadt.cstr('star2lte-entry'))
    
    cpus = child(root, 'cpus')
    cpu0 = child(cpus, 'cpu0')
    for key, value in cpu_node(0):
        if key != 'cpu-id':
            set_prop(cpu0, key, value)
            
    for logical in range(1, 8):
        cpus.children.append(mkadt.node(f'cpu{logical}', cpu_node(logical)))
        
    arm_io = child(root, 'arm-io')
    set_prop(arm_io, 'device_type', mkadt.cstr('star2lte-io'))
    set_prop(arm_io, 'compatible', mkadt.cstr('samsung,exynos9810-io') + mkadt.cstr('arm-io'))
    set_prop(arm_io, 'ranges', mkadt.u64(0, 0x10000000, 0xf0000000))
    arm_io.children = [n for n in arm_io.children if n.prop('name') == mkadt.cstr('wdt')]
    
    # Stock star2lte DT uses GICv2. pe_init_fiq adds the arm-io base
    # (0x10000000), so reg contains bus-relative offsets, not physical PAs.
    arm_io.children.append(mkadt.node('gic', [
        ('compatible', mkadt.cstr('arm,cortex-a15-gic')),
        ('interrupt-controller', mkadt.cstr('master')),
        ('virtual-timer-intid', mkadt.u32(30)),
        ('reg', mkadt.u64(0x00101000, 0x1000, 0x00102000, 0x1000)),
    ]))
    
    arm_io.children.append(mkadt.node('disp0', [
        ('device_type', mkadt.cstr('display-subsystem')),
        ('compatible', mkadt.cstr('samsung,star2lte-display') +
         mkadt.cstr('samsung,a5xelte-display')),
        ('canvas-width', mkadt.u32(canvas[0])),
        ('canvas-height', mkadt.u32(canvas[1])),
    ]))
    
    root.children = [n for n in root.children if n.prop('name') not in
                     (mkadt.cstr('sweet-fbcon'), mkadt.cstr('sweet-ufs'))]
                     
    # Serial frame buffer console
    root.children.append(mkadt.node('a5xelte-fbcon', [
        ('reg', mkadt.u64(FB_PHYS, FB_W * FB_H * 4)),
        ('width', mkadt.u32(FB_W)),
        ('height', mkadt.u32(FB_H)),
        ('stride', mkadt.u32(FB_W * 4)),
    ]))
    
    # Exynos 9810 UFS register offsets
    root.children.append(mkadt.node('star2lte-ufs', [
        ('reg', mkadt.u64(0x11240000, 0x200, 0x11241100, 0x200)),
    ]))
    return root

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--canvas', default=f'{FB_W}x{FB_H}',
                        help='display size presented to iOS, WxH')
    args = parser.parse_args()
    blob = adt.serialize(build(tuple(int(v) for v in args.canvas.split('x'))))
    args.output.write_bytes(blob)
    print(f'{args.output}: {len(blob)} bytes')
