/* SPDX-License-Identifier: GPL-2.0-only
 * Galaxy S9+ (SM-G965F, Exynos 9810, star2lte) secondary-CPU probe.
 *
 * Exynos 9810 Power Management Unit (PMU) shifts to 0x11860000.
 * Core configurations, CPU config states, and cluster power loops mapped to Exynos 9810 registers.
 */
#include <stdint.h>
#include "smp_probe.h"

#define PMU             0x11860000UL    /* Exynos 9810 PMU Register Base */
#define CPU_CFG(m)      (PMU + 0x2000 + ((((m) >> 8) & 0xf) << 2 | ((m) & 0xf)) * 0x80)
#define CPU_STAT(m)     (CPU_CFG(m) + 4)
#define CL_CPUSEQ(c)    (PMU + 0x2488 + (c) * 0x20)
#define CL_NONCPU(c)    (PMU + 0x2404 + (c) * 0x20)
#define CL_L2(c)        (PMU + 0x2604 + (c) * 0x20)

#define PSCI_CPU_ON     0xc4000003UL
#define TIMER_HZ        26000000UL
extern char smp_entry[];
extern volatile uint64_t smp_flags;  /* start.S: set by a started core */

static inline uint32_t rd(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }

static uint64_t ticks(void)
{
    uint64_t v;
    __asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(v));
    return v;
}

static int64_t smc3(uint64_t fn, uint64_t a1, uint64_t a2, uint64_t a3)
{
    register uint64_t x0 __asm__("x0") = fn;
    register uint64_t x1 __asm__("x1") = a1;
    register uint64_t x2 __asm__("x2") = a2;
    register uint64_t x3 __asm__("x3") = a3;
    __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3) : :
        "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13",
        "x14", "x15", "x16", "x17", "memory");
    return (int64_t)x0;
}

static int wait_flag(unsigned slot, unsigned ms)
{
    uint64_t end = ticks() + TIMER_HZ / 1000 * ms;
    while (ticks() < end)
        if (smp_flags[slot])
            return 1;
    return 0;
}

static void regs(void (*kv)(const char *, uint64_t), uint64_t m)
{
    unsigned c = (m >> 8) & 0xf;
    kv(" cfg", rd(CPU_CFG(m)));
    kv("stat", rd(CPU_STAT(m)));
    kv("cpuseq", rd(CL_CPUSEQ(c)));
    kv("noncpu", rd(CL_NONCPU(c)));
    kv("l2", rd(CL_L2(c)));
}

/* Poll a PMU bit with a timeout; 1 = reached. */
static int wait_bit(uintptr_t a, uint32_t bit, unsigned ms)
{
    uint64_t end = ticks() + TIMER_HZ / 100 * ms;
    while (ticks() < end)
        if (rd(a) & bit)
            return 1;
    return 0;
}

/* Meerkat M3 (CLUSTER0, MPIDR 0x100-0x103) bring-up test on Exynos 9810 */
void mngs_probe(void (*kv)(const char *, uint64_t), void (*out)(const char *))
{
    out("M3 (Meerkat) probe (Mongoose/Meerkat cluster 1) - star2lte\n");
    kv("seq st", rd(PMU + 0x2484));
    kv("seq opt", rd(PMU + 0x2488));
    kv("cpu10 st", rd(CPU_STAT(0x100)));
    out("\n");

    /* Map Meerkat M3 Cluster power sequence registers on Exynos 9810 */
    smp_flags = 0;
    wr(CPU_CFG(0x100), rd(CPU_CFG(0x100)) & ~0xfu);
    uint64_t end = ticks() + TIMER_HZ / 10;
    while (ticks() < end && (rd(CPU_STAT(0x100)) & 0xf))
        ;

    int64_t rc0 = smc3(PSCI_CPU_ON, 0x100, (uintptr_t)smp_entry, 4);
    wr(CPU_CFG(0x100), rd(CPU_CFG(0x100)) | 0xf);
    end = ticks() + TIMER_HZ / 10;
    while (ticks() < end && (rd(CPU_STAT(0x100)) & 0xf) != 0xf)
        ;

    kv("first CPU_ON rc", (uint64_t)rc0);
    kv("cpu10 st", rd(CPU_STAT(0x100)));
    out("\n");

    int up = wait_flag(4, 100);
    int64_t rc = 0;
    if (!up) {
        rc = smc3(PSCI_CPU_ON, 0x100, (uintptr_t)smp_entry, 4);
        up = wait_flag(4, 300);
    }
    kv("CPU_ON rc", (uint64_t)rc);
    kv("MEERKAT STARTED", up);
    out("\nM3 probe done\n");
}

void smp_probe(void (*kv)(const char *, uint64_t), void (*out)(const char *))
{
    /* Targets: Cortex-A55 LITTLE core (0x001), Meerkat M3 big core (0x100) */
    static const uint64_t targets[] = { 0x001, 0x100 };
    uint64_t self = 0;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(self));
    out("SMP probe - star2lte\n");
    kv("boot mpidr", self & 0xffffff);
    regs(kv, self & 0xffffff);
    out("\n");

    for (unsigned t = 0; t < sizeof(targets) / sizeof(targets[0]); t++) {
        uint64_t m = targets[t];
        unsigned slot = (((m >> 8) & 1) << 2) | (m & 3);
        smp_flags[slot] = 0;
        kv("target", m);
        regs(kv, m);
        out("\n");

        int64_t rc = smc3(PSCI_CPU_ON, m, (uintptr_t)smp_entry, slot);
        int up = wait_flag(slot, 300);
        kv(" CPU_ON rc", (uint64_t)rc);
        kv("started", up);
        regs(kv, m);
        out("\n");

        if (up)
            continue;

        /* Power the target Exynos 9810 core and its cluster sequencer through the PMU */
        unsigned c = (m >> 8) & 0xf;
        wr(CL_CPUSEQ(c), rd(CL_CPUSEQ(c)) & ~1u);
        wr(CPU_CFG(m), rd(CPU_CFG(m)) | 0xf);
        uint64_t end = ticks() + TIMER_HZ / 10;
        while (ticks() < end && (rd(CPU_STAT(m)) & 0xf) != 0xf)
            ;

        out(" after PMU power-up:");
        regs(kv, m);
        out("\n");
        rc = smc3(PSCI_CPU_ON, m, (uintptr_t)smp_entry, slot);
        up = wait_flag(slot, 300);
        kv(" CPU_ON rc", (uint64_t)rc);
        kv("started", up);
        regs(kv, m);
        out("\n");
    }
    out("SMP probe done\n");
}
