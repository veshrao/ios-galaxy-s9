#!/usr/bin/env python3
"""
mkadt_star2lte.py: Compiled Apple Device Tree (ADT) generator for the 
Samsung Galaxy S9+ (SM-G965F, star2lte, Exynos 9810).
Generates the proprietary Apple DT structure parsed by the bootstrap/XNU kernel.
"""

import sys
import struct
import argparse

def u32(val):
    return struct.pack('<I', val)

def u64(val):
    return struct.pack('<Q', val)

def pstr(val):
    return val.encode('utf-8') + b'\x00'

class DeviceTreeWriter:
    def __init__(self):
        self.data = bytearray()
        self.node_count = 0

    def start_node(self, name):
        self.data += u32(1)  # Node Start marker
        self.data += pstr(name).ljust(32, b'\x00')[:32]
        self.node_count += 1

    def end_node(self):
        self.data += u32(2)  # Node End marker

    def add_property(self, name, value):
        self.data += u32(3)  # Property marker
        self.data += pstr(name).ljust(32, b'\x00')[:32]
        self.data += u32(len(value))
        self.data += value
        # Align to 4 bytes
        pad = (4 - (len(value) % 4)) % 4
        self.data += b'\x00' * pad

    def finalize(self):
        self.data += u32(4)  # EOF marker
        return self.data

def generate_adt(canvas_w, canvas_h):
    writer = DeviceTreeWriter()

    # Root Node
    writer.start_node("")
    writer.add_property("model", pstr("Samsung Galaxy S9+"))
    writer.add_property("compatible", pstr("samsung,star2lte") + pstr("samsung,exynos9810"))
    writer.add_property("device_type", pstr("soc"))
    writer.add_property("#address-cells", u32(2))
    writer.add_property("#size-cells", u32(2))

    # CPU Topology Node
    writer.start_node("cpus")
    writer.add_property("#address-cells", u32(1))
    writer.add_property("#size-cells", u32(0))

    # 4x LITTLE Clusters (Cortex-A55, MPIDR 0x0..0x3)
    # 4x Big Clusters (Meerkat M3, MPIDR 0x100..0x103)
    for i in range(8):
        mpidr = i if i < 4 else 0x100 + (i - 4)
        writer.start_node(f"cpu@{i}")
        writer.add_property("device_type", pstr("cpu"))
        writer.add_property("reg", u32(mpidr))
        writer.add_property("compatible", pstr("arm,cortex-a55") if i < 4 else pstr("samsung,meerkat-m3"))
        writer.add_property("state", pstr("running" if i == 0 else "disabled"))
        writer.end_node()
    writer.end_node()  # cpus

    # Memory Nodes (S9+ Bank 1 Layout starting at 0x80000000)
    writer.start_node("memory")
    writer.add_property("device_type", pstr("memory"))
    # Map physical high RAM base 0x880000000 (Size: 2GB / 0x80000000)
    writer.add_property("reg", u64(0x880000000) + u64(0x80000000))
    writer.end_node()

    # GICv3 Interrupt Controller Node
    writer.start_node("interrupt-controller")
    writer.add_property("compatible", pstr("arm,gic-v3"))
    writer.add_property("interrupt-controller", b"")
    writer.add_property("#interrupt-cells", u32(3))
    # GICv3 Distributor (0x10900000) and Redistributor (0x10940000) Bases
    writer.add_property("reg", u64(0x10900000) + u64(0x10000) + u64(0x10940000) + u64(0x80000))
    writer.end_node()

    # Exynos UART Node
    writer.start_node("uart")
    writer.add_property("compatible", pstr("samsung,exynos4210-uart"))
    # UART2 Base Register Base (0x13820000)
    writer.add_property("reg", u64(0x13820000) + u64(0x1000))
    writer.add_property("interrupts", u32(0) + u32(120) + u32(4)) # SPI index for UART2
    writer.end_node()

    # DECON Framebuffer Node
    writer.start_node("display")
    writer.add_property("compatible", pstr("samsung,star2lte-display"))
    # Hardcoded framebuffer physical address handed from S-Boot (0xcc000000)
    writer.add_property("reg", u64(0xcc000000) + u64(canvas_w * canvas_h * 4))
    writer.add_property("width", u32(canvas_w))
    writer.add_property("height", u32(canvas_h))
    writer.add_property("stride", u32(canvas_w * 4))
    writer.end_node()

    # Exynos UFS Node (star2lte-ufs)
    writer.start_node("star2lte-ufs")
    writer.add_property("compatible", pstr("samsung,exynos-ufs"))
    # Host Controller base (0x11240000) and Vendor-specific register block (0x11244000)
    writer.add_property("reg", u64(0x11240000) + u64(0x1000) + u64(0x11244000) + u64(0x1000))
    writer.add_property("interrupts", u32(0) + u32(160) + u32(4))
    writer.end_node()

    # End Root
    writer.end_node()

    return writer.finalize()

def main():
    parser = argparse.ArgumentParser(description="Compile Apple Device Tree (ADT) for star2lte.")
    parser.add_argument("outfile", help="Output file path for binary ADT.")
    parser.add_argument("--canvas", default="1440x2960", help="Resolution format, e.g. 1440x2960")
    args = parser.parse_args()

    try:
        w, h = map(int, args.canvas.split('x'))
    except ValueError:
        print("[-] Invalid canvas resolution format. Must be WxH (e.g. 1440x2960)")
        sys.exit(1)

    print(f"[*] Building star2lte ADT with canvas resolution: {w}x{h}...")
    adt_bin = generate_adt(w, h)
    
    with open(args.outfile, "wb") as f:
        f.write(adt_bin)
    print(f"[+] Successfully wrote compiled ADT to {args.outfile}")

if __name__ == "__main__":
    main()
