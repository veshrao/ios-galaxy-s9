/* SPDX-License-Identifier: GPL-2.0-only
 * Galaxy S9+ (SM-G965F, Exynos 9810, star2lte) display pipeline probe.
 *
 * Checks DECON_F and DPU IDMA channels under Exynos 9810 MMIO mapping.
 */
#include <stdint.h>
#include "display_probe.h"

#define DECON               0x14040000UL    /* Exynos 9810 DECON_F */
#define SHADOW_REQ          0x60
#define SHADOW_GLOBAL       (1u << 31)
#define FB_PHYS             0xcc000000u
#define FB_STRIDE           (1440u * 4)
#define TIMER_HZ            26000000UL

/* Exynos 9810 DPU IDMA channels */static const uintptr_t idma[] = {
    0x14051000UL, 0x14052000UL, 0x14053000UL, 0x14054000UL, 0x14055000UL, 0x14057000UL,
};

/* Exynos 9810 Display SYSMMU blocks */static const uintptr_t sysmmu[] = { 0x14080000UL, 0x14090000UL, 0x140a0000UL };

static inline uint32_t rd(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }

static uint64_t ticks(void)
{
    uint64_t v;
    __asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(v));
    return v;
}

static void delay_ms(unsigned ms)
{
    uint64_t end = ticks() + TIMER_HZ / 1000 * ms;
    while (ticks() < end)
        ;
}

static void update(void)
{
    wr(DECON + SHADOW_REQ, rd(DECON + SHADOW_REQ) | SHADOW_GLOBAL | 0x3f);
    for (unsigned n = 0; n < 100 && rd(DECON + SHADOW_REQ); n++)
        delay_ms(1);
}

/* DECON INTERRUPT_PENDING (0x4c) bit 13 DPU_FRAME_DONE over 0.5 s */
static uint64_t frames(void)
{
    uint32_t en = rd(DECON + 0x40);
    wr(DECON + 0x40, en | (1u << 13) | 1u);
    wr(DECON + 0x4c, 1u << 13);
    uint64_t n = 0, end = ticks() + TIMER_HZ / 2;
    while (ticks() < end) {
        if (rd(DECON + 0x4c) & (1u << 13)) {
            n++;
            wr(DECON + 0x4c, 1u << 13);
        }
    }
    wr(DECON + 0x40, en);
    return n;
}

void display_probe(void (*kv)(const char *, uint64_t), void (*out)(const char *))
{
    out("DISPLAY probe (DECON_F + IDMA) - star2lte\n");
    kv("decon 0x0", rd(DECON + 0x0));
    kv("0x60", rd(DECON + SHADOW_REQ));
    kv("0x70", rd(DECON + 0x70));
    kv("dp0", rd(DECON + 0x214));
    out("\n");

    for (unsigned w = 0; w < 6; w++) {
        uint32_t c = rd(DECON + 0x1000 + w * 0x30);
        if (c) {
            kv("win", w);
            kv("ctl0", c);
            kv("ctl1", rd(DECON + 0x1004 + w * 0x30));
            out("\n");
        }
    }

    int scan = -1;
    for (unsigned n = 0; n < 6; n++) {
        uintptr_t b = idma[n];
        uint32_t base = rd(b + 0x40);
        kv("idma", n);
        kv("en", rd(b + 0x00));
        kv("in", rd(b + 0x08));
        kv("src", rd(b + 0x10));
        kv("off", rd(b + 0x14));
        kv("img", rd(b + 0x18));
        kv("Y", base);
        out("\n");
        if (base == FB_PHYS && scan < 0)
            scan = (int)n;
    }

    if (scan >= 0) {
        kv("flip test on idma", (uint64_t)scan);
        kv("frames/0.5s", frames());
        out("\n");

        uintptr_t y = idma[scan] + 0x40;
        out("TEST: base +800 lines. PICTURE JUMPS UP NOW?\n");
        wr(y, FB_PHYS + FB_STRIDE * 800);
        wr(DECON + SHADOW_REQ, rd(DECON + SHADOW_REQ) | SHADOW_GLOBAL | 0x3f);
        kv("req after write", rd(DECON + SHADOW_REQ));
        kv("frames/0.5s", frames());
        kv("req", rd(DECON + SHADOW_REQ));
        kv("Y", rd(y));
        out("\n");

        delay_ms(2500);

        wr(y, FB_PHYS);
        update();
        kv("restored Y", rd(y));
        kv("idma en", rd(idma[scan]));
        out("\nTEST DONE\n");
    } else {
        out("no IDMA reads 0xcc000000: skipping flip test\n");
    }

    for (unsigned s = 0; s < 3; s++) {
        kv("sysmmu", sysmmu[s]);
        kv("ctrl", rd(sysmmu[s] + 0x0));
        kv("cfg", rd(sysmmu[s] + 0x4));
        out("\n");
    }
    out("DISPLAY probe done\n");
}
