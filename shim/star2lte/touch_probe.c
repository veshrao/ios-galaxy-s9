/* SPDX-License-Identifier: GPL-2.0-only
 * Galaxy S9+ (SM-G965F, Exynos 9810, star2lte) touchscreen and battery probe.
 *
 * Polled I2C over Exynos 9810 HSI2C blocks to inspect touch panel and MAX77865 fuel gauge.
 */
#include <stdint.h>
#include "touch_probe.h"

/* Exynos 9810 Pin Control & HSI2C bases */
#define GPA1_CON            (0x11830000UL + 0x040) /* Exynos 9810 ALIVE domain GPA1 */
#define HSI2C               0x14360000UL           /* Exynos 9810 Touchscreen HSI2C channel */
#define BAT_HSI2C           0x14350000UL           /* Exynos 9810 Fuel Gauge HSI2C channel */

#define CTL         0x00
#define FIFO_CTL        0x04
#define TRAILIG_CTL     0x08
#define INT_ENABLE      0x20
#define INT_STATUS      0x24
#define FIFO_STATUS     0x30
#define TX_DATA         0x34
#define RX_DATA         0x38
#define CONF            0x40
#define AUTO_CONF       0x44
#define TIMEOUT         0x48
#define TRANS_STATUS        0x50
#define TIMING_FS1      0x60
#define TIMING_FS2      0x64
#define TIMING_FS3      0x68
#define TIMING_SLA      0x6c
#define ADDR            0x70

#define CTL_I2C_MASTER      ((1u << 0) | (1u << 3))
#define CTL_RXCHON      (1u << 6)
#define CTL_TXCHON      (1u << 7)
#define CTL_SW_RST      (1u << 31)
#define CONF_AUTO_MODE      (1u << 31)
#define AUTO_READ       (1u << 16)
#define AUTO_STOP       (1u << 17)
#define AUTO_RUN        (1u << 31)
#define INT_DONE        (1u << 7)
#define INT_ERRS        (0xfu << 8) /* abort, no ack, no dev, timeout */
#define RX_EMPTY        (1u << 24)
#define TX_FULL         (1u << 7)

#define TS_ADDR         0x48
#define TIMER_HZ        26000000UL
#define CLKIN           26000000u
#define SCL_HZ          400000u

static void (*kv)(const char *, uint64_t);
static void (*out)(const char *);

static inline uint32_t rd(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }

static uintptr_t bus = HSI2C;   /* active controller */
static unsigned dev = TS_ADDR;  /* active slave address */

static inline uint32_t hr(unsigned o) { return rd(bus + o); }
static inline void hw(unsigned o, uint32_t v) { wr(bus + o, v); }

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

static void set_timing(void)
{
    unsigned ftl = (hr(CONF) >> 16) & 7;
    unsigned temp = CLKIN / SCL_HZ - (ftl + 3) * 2;
    unsigned div = temp / 512;
    unsigned cyc = (temp + ((ftl + 3) % (div + 1)) * 2) / (div + 1) - 2;
    unsigned l = cyc * 64 / 100, h = cyc - l;
    hw(TIMING_FS1, l << 24 | l << 16 | l << 8);
    hw(TIMING_FS2, (l / 2) << 24 | l << 8 | h);
    hw(TIMING_FS3, div << 16 | cyc);
    hw(TIMING_SLA, l / 2);
}

static void hsi2c_reset(void)
{
    hw(CTL, hr(CTL) | CTL_SW_RST);
    hw(CTL, hr(CTL) & ~CTL_SW_RST);
    set_timing();
    hw(TIMEOUT, hr(TIMEOUT) & ~(1u << 31));
    hw(CTL, CTL_I2C_MASTER);
    hw(TRAILIG_CTL, 0xf);
    hw(CONF, hr(CONF) | CONF_AUTO_MODE);
}

static uint32_t wait_done(void)
{
    uint64_t end = ticks() + TIMER_HZ / 20;
    for (;;) {
        uint32_t s = hr(INT_STATUS);
        if (s & (INT_DONE | INT_ERRS)) {
            hw(INT_STATUS, s);
            return (s & INT_ERRS) ? s : 0;
        }
        if (ticks() > end)
            return 0x80000000u | hr(TRANS_STATUS);
    }
}

static uint32_t xfer(const uint8_t *w, unsigned wlen, uint8_t *r, unsigned rlen)
{
    uint32_t st;
    hw(INT_STATUS, hr(INT_STATUS));
    hw(ADDR, (dev & 0x3ff) << 10);
    hw(INT_ENABLE, INT_DONE | INT_ERRS);
    if (wlen) {
        hw(FIFO_CTL, 3);
        hw(CTL, CTL_I2C_MASTER | CTL_TXCHON);
        hw(AUTO_CONF, (rlen ? 0 : AUTO_STOP) | wlen | AUTO_RUN);
        for (unsigned i = 0; i < wlen; i++) {
            uint64_t end = ticks() + TIMER_HZ / 100;
            while ((hr(FIFO_STATUS) & TX_FULL) && ticks() < end)
                ;
            hw(TX_DATA, w[i]);
        }
        if ((st = wait_done()))
            goto bad;
    }
    if (rlen) {
        hw(FIFO_CTL, 3);
        hw(CTL, CTL_I2C_MASTER | CTL_RXCHON);
        hw(AUTO_CONF, AUTO_READ | AUTO_STOP | rlen | AUTO_RUN);
        for (unsigned i = 0; i < rlen; i++) {
            uint64_t end = ticks() + TIMER_HZ / 20;
            while ((hr(FIFO_STATUS) & RX_EMPTY) && ticks() < end)
                ;
            if (hr(FIFO_STATUS) & RX_EMPTY) {
                st = 0x40000000u | i;
                goto bad;
            }
            r[i] = (uint8_t)hr(RX_DATA);
        }
        if ((st = wait_done()))
            goto bad;
    }
    hw(CTL, CTL_I2C_MASTER);
    return 0;
bad:
    hsi2c_reset();
    return st;
}

static void dump(const char *what, const uint8_t *b, unsigned n, uint32_t st)
{
    out(what);
    kv(" st", st);
    if (!st) {
        uint64_t v = 0;
        for (unsigned i = 0; i < n && i < 8; i++)
            v = v << 8 | b[i];
        kv("data", v);
    }
    out("\n");
}

void touch_probe(void (*kv_fn)(const char *, uint64_t), void (*out_fn)(const char *))
{
    uint8_t c, b[11];
    uint32_t st;

    kv = kv_fn;
    out = out_fn;
    out("TOUCH probe (S6SY761 hsi2c_star2lte 0x14360000)\n");
    delay_ms(200);  /* wait for rails to settle */

    kv("gpa1 con", rd(GPA1_CON));
    kv("dat", rd(GPA1_CON + 4));
    out("\n");

    out("hsi2c regs: ");
    kv("ctl", hr(CTL));
    kv("conf", hr(CONF));
    kv("trans", hr(TRANS_STATUS));
    kv("fifo", hr(FIFO_STATUS));
    out("\n");

    hsi2c_reset();
    out("reset: ");
    kv("ctl", hr(CTL));
    kv("conf", hr(CONF));
    kv("fs2", hr(TIMING_FS2));
    kv("fs3", hr(TIMING_FS3));
    out("\n");

    c = 0x55;   /* BOOT_STATUS */
    st = xfer(&c, 1, b, 1);
    dump("boot status", b, 1, st);
    c = 0x52;   /* DEVICE_ID */
    st = xfer(&c, 1, b, 3);
    dump("device id", b, 3, st);
    c = 0x23;   /* PANEL_INFO */
    st = xfer(&c, 1, b, 11);
    dump("panel info", b, 8, st);
    c = 0x21;   /* FIRMWARE_INTEGRITY */
    st = xfer(&c, 1, b, 1);
    dump("fw integrity", b, 1, st);

    /* SENSE_ON, poll touches for 1 second */
    c = 0x10;
    st = xfer(&c, 1, 0, 0);
    kv("sense on", st);
    out("\n");

    unsigned shown = 0;
    uint64_t end = ticks() + TIMER_HZ;
    while (ticks() < end && shown < 24) {
        if (rd(GPA1_CON + 4) & 1) {
            delay_ms(2);
            continue;
        }
        c = 0x60;   /* READ_ONE_EVENT */
        st = xfer(&c, 1, b, 8);
        dump("ev", b, 8, st);
        shown++;
        if (st)
            delay_ms(50);
    }
    kv("gpa1 dat", rd(GPA1_CON + 4));
    out("\nTOUCH probe done\n");
}

/* One 16-bit LE fuel-gauge register read */
static void fg_show(const char *name, uint8_t reg)
{
    uint8_t b[2];
    uint32_t st = xfer(&reg, 1, b, 2);
    kv(name, st ? 0xdead0000u | (st & 0xffff) : (uint32_t)(b[0] | b[1] << 8));
}

void battery_probe(void (*kv_fn)(const char *, uint64_t), void (*out_fn)(const char *))
{
    uint8_t r, b[2];
    kv = kv_fn;
    out = out_fn;
    out("BATTERY (MAX77865 hsi2c_star2lte 0x14350000)\n");

    bus = BAT_HSI2C;
    hsi2c_reset();
    dev = 0x36;
    fg_show("soc", 0x06);
    fg_show("vcell", 0x09);
    fg_show("cur", 0x0a);
    fg_show("design", 0x18);
    out("\n");

    dev = 0x69;
    r = 0xb2;
    kv("chg int_ok", xfer(&r, 1, b, 1) ? 0xdead : b[0]);
    r = 0xb4;
    kv("dtls01", xfer(&r, 1, b, 1) ? 0xdead : b[0]);
    out("\n");

    bus = HSI2C;
    dev = TS_ADDR;
}
