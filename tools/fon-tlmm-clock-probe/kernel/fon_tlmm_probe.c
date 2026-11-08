// SPDX-License-Identifier: GPL-2.0-only
/*
 * Optional kernel-side read-only TLMM TDM clock probe.
 *
 * Architecture:
 *   insmod   -> create /sys/kernel/debug/fon_tlmm_probe only; idle
 *   write 1  -> one bounded measurement of one allowed GPIO
 *   read     -> last result only; no new measurement
 *   rmmod    -> remove the debugfs node; no measurement
 *
 * The source contains no MMIO writes, no GPIO requests, no pinctrl changes,
 * no clock/reset calls and no interrupt setup.  It is still a hardware action
 * when triggered and must not be loaded or triggered without the separate
 * approval in docs/runbook/fon-stage-c0plus-kernel-probe.md.
 */
#include <linux/debugfs.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <linux/types.h>
#include <linux/uaccess.h>

#include "fon_tlmm_probe_logic.h"

#define TLMM_BASE		0x01000000UL
#define TLMM_GPIO_STRIDE	0x1000UL
#define TLMM_GPIO_CFG_OFF	0x0UL
#define TLMM_GPIO_IO_OFF	0x4UL
#define TLMM_PAGE_SIZE		0x1000UL

#define DEFAULT_DURATION_MS	20U
#define MIN_DURATION_MS		20U
#define MAX_DURATION_MS		50U
#define MIN_DURATION_NS		10000000ULL
#define SIGNIFICANT_GAP_NS	1000000ULL
#define CHECK_EVERY		32U
#define RESCHED_EVERY		1024U
#define RESULT_SIZE		768

static int gpio = 22;
module_param(gpio, int, 0444);
MODULE_PARM_DESC(gpio, "allowed TLMM GPIO: 21, 22, 25 or 26 (default 22)");

static unsigned int duration_ms = DEFAULT_DURATION_MS;
module_param(duration_ms, uint, 0444);
MODULE_PARM_DESC(duration_ms, "one-shot window in ms: 20..50 (default 20)");

static int expected_hz;
module_param(expected_hz, int, 0444);
MODULE_PARM_DESC(expected_hz, "0 = derive from GPIO (8 kHz or 1.024 MHz)");

static struct dentry *probe_entry;
static DEFINE_MUTEX(probe_lock);
static int probe_state = PROBE_TRIGGER_IDLE;
static char last_result[RESULT_SIZE] = "idle\n";

static bool gpio_allowed(int pin)
{
	return pin == 21 || pin == 22 || pin == 25 || pin == 26;
}

static u64 derived_expected_hz(int pin)
{
	return (pin == 21 || pin == 25) ? 1024000ULL : 8000ULL;
}

static int run_measurement(void)
{
	void __iomem *map;
	void __iomem *cfg_reg;
	void __iomem *io_reg;
	struct probe_timing timing = {0};
	u32 cfg_before, cfg_after;
	u64 start_ns, now_ns, elapsed_ns;
	u64 sample_rate_hz, frequency_hz;
	u64 expected;
	const char *status;
	int timing_bad;
	unsigned int level;
	int last_level = 0;
	int have_last = 0;

	if (!gpio_allowed(gpio)) {
		scnprintf(last_result, sizeof(last_result),
			  "ERROR gpio=%d allowed=21,22,25,26\n", gpio);
		return -EINVAL;
	}
	if (duration_ms < MIN_DURATION_MS || duration_ms > MAX_DURATION_MS) {
		scnprintf(last_result, sizeof(last_result),
			  "ERROR duration_ms=%u allowed=%u..%u\n",
			  duration_ms, MIN_DURATION_MS, MAX_DURATION_MS);
		return -EINVAL;
	}

	expected = expected_hz > 0 ? (u64)expected_hz :
					 derived_expected_hz(gpio);

	map = ioremap(TLMM_BASE + (unsigned long)gpio * TLMM_GPIO_STRIDE,
		      TLMM_PAGE_SIZE);
	if (!map) {
		scnprintf(last_result, sizeof(last_result),
			  "ERROR ioremap gpio=%d\n", gpio);
		return -ENOMEM;
	}

	cfg_reg = map + TLMM_GPIO_CFG_OFF;
	io_reg = map + TLMM_GPIO_IO_OFF;
	cfg_before = readl(cfg_reg);

	start_ns = ktime_get_ns();
	probe_timing_start(&timing, start_ns);
	for (;;) {
		level = readl(io_reg) & 1U;
		if (have_last && level != (unsigned int)last_level)
			timing.edges++;
		last_level = (int)level;
		have_last = 1;
		timing.samples++;

		if ((timing.samples % CHECK_EVERY) == 0) {
			now_ns = ktime_get_ns();
			probe_timing_checkpoint(&timing, now_ns);
			elapsed_ns = now_ns - start_ns;
			if (elapsed_ns >= (u64)duration_ms * 1000000ULL)
				break;
			if ((timing.samples % RESCHED_EVERY) == 0)
				cond_resched();
		}
	}

	now_ns = ktime_get_ns();
	probe_timing_checkpoint(&timing, now_ns);
	probe_timing_close_segment(&timing, now_ns);
	elapsed_ns = now_ns - start_ns;
	if (elapsed_ns == 0)
		elapsed_ns = 1;
	cfg_after = readl(cfg_reg);

	sample_rate_hz = div_u64(timing.samples * 1000000000ULL,
				 (u32)elapsed_ns);
	frequency_hz = div_u64(timing.edges * 500000000ULL,
			       (u32)elapsed_ns);
	timing_bad = probe_timing_evaluate(&timing, elapsed_ns, expected);

	if (cfg_before != cfg_after)
		timing_bad = 1;

	if (timing_bad) {
		status = "INCONCLUSIVE";
	} else if (timing.edges == 0) {
		if (sample_rate_hz >= 4ULL * expected &&
		    elapsed_ns >= MIN_DURATION_NS)
			status = "STATIC_OBSERVED";
		else
			status = "INCONCLUSIVE";
	} else if (timing.edges < 2 || sample_rate_hz < 4ULL * expected ||
		   elapsed_ns < MIN_DURATION_NS ||
		   frequency_hz < expected / 2ULL ||
		   frequency_hz > expected * 2ULL) {
		status = "DETECTED";
	} else {
		status = "FREQUENCY_ESTIMATED";
	}

	scnprintf(last_result, sizeof(last_result),
		  "gpio=%d cfg=0x%08x io=0x%08x func=%u oe=%u input=%u "
		  "samples=%llu edges=%llu elapsed_ns=%llu "
		  "sample_rate_hz=%llu freq_hz=%llu status=%s "
		  "cfg_changed=%u max_gap_ns=%llu gap_total_ns=%llu "
		  "gap_count=%llu segments=%llu valid_segments=%llu "
		  "zero_edge_segments=%llu low_edge_segments=%llu "
		  "min_freq_hz=%llu "
		  "max_freq_hz=%llu min_segment_edges=%llu "
		  "max_segment_edges=%llu timing_suspect=%d\n",
		  gpio, cfg_before, readl(io_reg), (cfg_before >> 2) & 0xf,
		  (cfg_before >> 9) & 1, readl(io_reg) & 1,
		  (unsigned long long)timing.samples,
		  (unsigned long long)timing.edges,
		  (unsigned long long)elapsed_ns,
		  (unsigned long long)sample_rate_hz,
		  (unsigned long long)frequency_hz, status,
		  cfg_before != cfg_after,
		  (unsigned long long)timing.max_gap_ns,
		  (unsigned long long)timing.gap_total_ns,
		  (unsigned long long)timing.gap_count,
		  (unsigned long long)timing.segments,
		  (unsigned long long)timing.valid_segments,
		  (unsigned long long)timing.zero_edge_segments,
		  (unsigned long long)timing.low_edge_segments,
		  (unsigned long long)timing.min_freq_hz,
		  (unsigned long long)timing.max_freq_hz,
		  (unsigned long long)timing.min_segment_edges,
		  (unsigned long long)timing.max_segment_edges,
		  timing_bad);

	iounmap(map);
	return 0;
}

static ssize_t trigger_write(struct file *file, const char __user *buf,
			     size_t len, loff_t *ppos)
{
	char command[8];
	int ret;

	(void)file;
	(void)ppos;
	if (len == 0 || len >= sizeof(command))
		return -EINVAL;
	if (copy_from_user(command, buf, len))
		return -EFAULT;

	/* Accept exactly "1" or "1\n"; no extra bytes and no CR. */
	if (!((len == 1 && command[0] == '1') ||
	      (len == 2 && command[0] == '1' && command[1] == '\n')))
		return -EINVAL;

	if (!mutex_trylock(&probe_lock))
		return -EBUSY;
	if (!probe_trigger_can_start(probe_state)) {
		mutex_unlock(&probe_lock);
		return -EALREADY;
	}

	probe_state = PROBE_TRIGGER_RUNNING;
	ret = run_measurement();
	probe_state = probe_trigger_next_state(ret == 0);
	mutex_unlock(&probe_lock);
	return ret ? ret : (ssize_t)len;
}

static ssize_t result_read(struct file *file, char __user *buf, size_t len,
			   loff_t *ppos)
{
	ssize_t ret;
	size_t count;

	(void)file;
	mutex_lock(&probe_lock);
	count = strlen(last_result);
	ret = simple_read_from_buffer(buf, len, ppos, last_result, count);
	mutex_unlock(&probe_lock);
	return ret;
}

static const struct file_operations probe_fops = {
	.owner = THIS_MODULE,
	.open = simple_open,
	.read = result_read,
	.write = trigger_write,
	.llseek = default_llseek,
};

static int __init fon_tlmm_probe_init(void)
{
	if (!gpio_allowed(gpio)) {
		pr_err("fon_tlmm_probe: gpio %d is not allowed\n", gpio);
		return -EINVAL;
	}
	if (duration_ms < MIN_DURATION_MS || duration_ms > MAX_DURATION_MS) {
		pr_err("fon_tlmm_probe: duration_ms must be %u..%u\n",
		       MIN_DURATION_MS, MAX_DURATION_MS);
		return -EINVAL;
	}
	if (expected_hz < 0) {
		pr_err("fon_tlmm_probe: expected_hz must be >= 0\n");
		return -EINVAL;
	}

	probe_entry = debugfs_create_file("fon_tlmm_probe", 0600, NULL, NULL,
					  &probe_fops);
	if (IS_ERR_OR_NULL(probe_entry)) {
		pr_err("fon_tlmm_probe: debugfs_create_file failed\n");
		return probe_entry ? PTR_ERR(probe_entry) : -ENODEV;
	}

	pr_info("fon_tlmm_probe: idle; write 1 to trigger one bounded measurement\n");
	return 0;
}

static void __exit fon_tlmm_probe_exit(void)
{
	mutex_lock(&probe_lock);
	debugfs_remove(probe_entry);
	probe_entry = NULL;
	mutex_unlock(&probe_lock);
}

module_init(fon_tlmm_probe_init);
module_exit(fon_tlmm_probe_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("OpenWrt-FB7530 FON research");
MODULE_DESCRIPTION("One-shot read-only IPQ4019 TLMM TDM clock diagnostic");
