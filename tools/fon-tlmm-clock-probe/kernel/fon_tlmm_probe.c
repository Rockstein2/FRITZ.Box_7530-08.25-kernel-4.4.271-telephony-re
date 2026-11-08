// SPDX-License-Identifier: GPL-2.0-only
/*
 * Optional kernel-side read-only TLMM TDM clock probe.
 *
 * DO NOT BUILD OR LOAD THIS MODULE WITHOUT A SEPARATE HARDWARE APPROVAL.
 * Loading it performs one bounded MMIO read measurement.  The source contains
 * no MMIO writes, no GPIO requests, no pinctrl changes, no clock/reset calls
 * and no interrupt setup, but it is still a hardware action.
 */
#include <linux/init.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/module.h>
#include <linux/types.h>

#define TLMM_BASE		0x01000000UL
#define TLMM_GPIO_STRIDE	0x1000UL
#define TLMM_GPIO_CFG_OFF	0x0UL
#define TLMM_GPIO_IO_OFF	0x4UL
#define TLMM_MAX_GPIO		40
#define TLMM_MAP_SIZE		((TLMM_MAX_GPIO + 1) * TLMM_GPIO_STRIDE)
#define MAX_DURATION_MS		2000U

static int gpio = 22;
module_param(gpio, int, 0444);
MODULE_PARM_DESC(gpio, "TLMM GPIO to read (20-27 or 40), default 22");

static unsigned int duration_ms = 200;
module_param(duration_ms, uint, 0444);
MODULE_PARM_DESC(duration_ms, "measurement window in ms, 10..2000, default 200");

static int expected_hz = 8000;
module_param(expected_hz, int, 0444);
MODULE_PARM_DESC(expected_hz, "nominal signal frequency for confidence, default 8000");

static const char *status_name(unsigned int edges, u64 sample_rate_hz,
			       u64 elapsed_ns, int cfg_changed)
{
	u64 min_rate = (u64)(expected_hz > 0 ? expected_hz : 1) * 4ULL;

	if (cfg_changed)
		return "INCONCLUSIVE";
	if (edges == 0)
		return sample_rate_hz >= min_rate &&
		       elapsed_ns >= 50000000ULL ? "STATIC_OBSERVED" :
						   "INCONCLUSIVE";
	if (edges >= 2 && sample_rate_hz >= min_rate &&
	    elapsed_ns >= 50000000ULL)
		return "FREQUENCY_ESTIMATED";
	return "DETECTED";
}

static int __init fon_tlmm_probe_init(void)
{
	void __iomem *map;
	void __iomem *cfg_reg;
	void __iomem *io_reg;
	u32 cfg_before, cfg_after;
	u64 start_ns, now_ns, elapsed_ns;
	u64 samples = 0, edges = 0;
	u64 sample_rate_hz, freq_hz;
	int last = 0, have_last = 0;
	const char *status;
	unsigned int level;

	if (!((gpio >= 20 && gpio <= 27) || gpio == 40)) {
		pr_err("fon_tlmm_probe: unsupported gpio %d (use 20-27 or 40)\n",
		       gpio);
		return -EINVAL;
	}
	if (duration_ms < 10 || duration_ms > MAX_DURATION_MS) {
		pr_err("fon_tlmm_probe: duration_ms must be 10..%u\n",
		       MAX_DURATION_MS);
		return -EINVAL;
	}
	if (expected_hz <= 0) {
		pr_err("fon_tlmm_probe: expected_hz must be positive\n");
		return -EINVAL;
	}

	map = ioremap(TLMM_BASE, TLMM_MAP_SIZE);
	if (!map) {
		pr_err("fon_tlmm_probe: ioremap failed\n");
		return -ENOMEM;
	}

	cfg_reg = map + gpio * TLMM_GPIO_STRIDE + TLMM_GPIO_CFG_OFF;
	io_reg = map + gpio * TLMM_GPIO_STRIDE + TLMM_GPIO_IO_OFF;
	cfg_before = readl(cfg_reg);

	start_ns = ktime_get_ns();
	for (;;) {
		level = readl(io_reg) & 1U;
		if (have_last && level != (unsigned int)last)
			edges++;
		last = (int)level;
		have_last = 1;
		samples++;

		/* Bound the time-check overhead; the inner loop is read-only. */
		if ((samples & 0xffULL) != 0)
			continue;

		now_ns = ktime_get_ns();
		if (now_ns - start_ns >= (u64)duration_ms * 1000000ULL)
			break;
	}

	now_ns = ktime_get_ns();
	elapsed_ns = now_ns - start_ns;
	if (elapsed_ns == 0)
		elapsed_ns = 1;
	cfg_after = readl(cfg_reg);

	sample_rate_hz = div_u64(samples * 1000000000ULL, elapsed_ns);
	freq_hz = div_u64(edges * 500000000ULL, elapsed_ns);
	status = status_name((unsigned int)edges, sample_rate_hz, elapsed_ns,
			     cfg_before != cfg_after);

	pr_info("fon_tlmm_probe: gpio=%d cfg=0x%08x io=0x%08x func=%u "
		"oe=%u input=%u samples=%llu edges=%llu elapsed_ns=%llu "
		"sample_rate_hz=%llu freq_hz=%llu status=%s cfg_changed=%u\n",
		gpio, cfg_before, readl(io_reg), (cfg_before >> 2) & 0xf,
		(cfg_before >> 9) & 1, readl(io_reg) & 1,
		(unsigned long long)samples, (unsigned long long)edges,
		(unsigned long long)elapsed_ns,
		(unsigned long long)sample_rate_hz,
		(unsigned long long)freq_hz, status,
		cfg_before != cfg_after);

	iounmap(map);
	return 0;
}

static void __exit fon_tlmm_probe_exit(void)
{
}

module_init(fon_tlmm_probe_init);
module_exit(fon_tlmm_probe_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("OpenWrt-FB7530 FON research");
MODULE_DESCRIPTION("Read-only IPQ4019 TLMM TDM clock diagnostic");
