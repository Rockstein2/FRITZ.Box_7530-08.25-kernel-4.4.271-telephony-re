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
static char last_result[RESULT_SIZE] = "idle\n";

struct timing_state {
	u64 samples;
	u64 edges;
	u64 start_ns;
	u64 last_check_ns;
	u64 last_check_samples;
	u64 last_check_edges;
	u64 max_gap_ns;
	u64 max_gap_samples;
	u64 gap_total_ns;
	u64 gap_count;
	u64 checkpoints;
	u64 segments;
	u64 zero_edge_segments;
	u64 min_rate_q;
	u64 max_rate_q;
	int have_rate;
	int started;
};

static bool gpio_allowed(int pin)
{
	return pin == 21 || pin == 22 || pin == 25 || pin == 26;
}

static u64 derived_expected_hz(int pin)
{
	return (pin == 21 || pin == 25) ? 1024000ULL : 8000ULL;
}

static void timing_start(struct timing_state *t, u64 now_ns)
{
	t->start_ns = now_ns;
	t->last_check_ns = now_ns;
	t->last_check_samples = t->samples;
	t->last_check_edges = t->edges;
	t->started = 1;
}

static void timing_checkpoint(struct timing_state *t, u64 now_ns)
{
	u64 gap_ns;
	u64 samples_since;
	u64 edges_since;
	u64 rate_q;
	u64 average_interval_ns;

	if (!t->started || now_ns <= t->last_check_ns)
		return;

	gap_ns = now_ns - t->last_check_ns;
	samples_since = t->samples - t->last_check_samples;
	edges_since = t->edges - t->last_check_edges;
	t->checkpoints++;

	if (gap_ns > t->max_gap_ns) {
		t->max_gap_ns = gap_ns;
		t->max_gap_samples = samples_since;
	}

	average_interval_ns = t->samples ?
		div_u64(t->last_check_ns - t->start_ns, (u32)t->samples) : 0;
	if (samples_since == 0) {
		if (gap_ns >= SIGNIFICANT_GAP_NS) {
			t->gap_total_ns += gap_ns;
			t->gap_count++;
		}
	} else if (average_interval_ns > 0 &&
		   gap_ns > 8ULL * samples_since * average_interval_ns) {
		t->gap_total_ns += gap_ns;
		t->gap_count++;
	}

	if (samples_since > 0) {
		t->segments++;
		if (edges_since == 0)
			t->zero_edge_segments++;

		rate_q = div_u64(edges_since * 1000000ULL, (u32)samples_since);
		if (!t->have_rate || rate_q < t->min_rate_q)
			t->min_rate_q = rate_q;
		if (!t->have_rate || rate_q > t->max_rate_q)
			t->max_rate_q = rate_q;
		t->have_rate = 1;
	}

	t->last_check_ns = now_ns;
	t->last_check_samples = t->samples;
	t->last_check_edges = t->edges;
}

static int timing_suspicious(const struct timing_state *t, u64 elapsed_ns,
			     u64 expected)
{
	u64 avg;
	u64 avg_segment_ns;

	if (!t->checkpoints || t->samples < 2)
		return 0;

	avg = div_u64(elapsed_ns, (u32)t->samples);

	if (t->max_gap_ns >= SIGNIFICANT_GAP_NS) {
		if (t->max_gap_samples == 0)
			return 1;
		if (t->max_gap_ns > 4ULL * t->max_gap_samples * avg)
			return 1;
	}

	if (t->gap_total_ns * 100ULL > elapsed_ns * 5ULL)
		return 1;

	if (t->edges == 0)
		return 0;

	avg_segment_ns = div_u64(elapsed_ns,
				 (u32)(t->segments ? t->segments : 1));
	if (t->segments >= 4 &&
	    expected * avg_segment_ns >= 2000000000ULL &&
	    t->zero_edge_segments > 0)
		return 1;

	if (t->segments >= 4 && t->have_rate && t->min_rate_q > 0 &&
	    t->max_rate_q * 2ULL > t->min_rate_q * 3ULL)
		return 1;

	return 0;
}

static int run_measurement(void)
{
	void __iomem *map;
	void __iomem *cfg_reg;
	void __iomem *io_reg;
	struct timing_state timing = {0};
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
	timing_start(&timing, start_ns);
	for (;;) {
		level = readl(io_reg) & 1U;
		if (have_last && level != (unsigned int)last_level)
			timing.edges++;
		last_level = (int)level;
		have_last = 1;
		timing.samples++;

		if ((timing.samples % CHECK_EVERY) == 0) {
			now_ns = ktime_get_ns();
			timing_checkpoint(&timing, now_ns);
			elapsed_ns = now_ns - start_ns;
			if (elapsed_ns >= (u64)duration_ms * 1000000ULL)
				break;
			if ((timing.samples % RESCHED_EVERY) == 0)
				cond_resched();
		}
	}

	now_ns = ktime_get_ns();
	timing_checkpoint(&timing, now_ns);
	elapsed_ns = now_ns - start_ns;
	if (elapsed_ns == 0)
		elapsed_ns = 1;
	cfg_after = readl(cfg_reg);

	sample_rate_hz = div_u64(timing.samples * 1000000000ULL,
				 (u32)elapsed_ns);
	frequency_hz = div_u64(timing.edges * 500000000ULL,
			       (u32)elapsed_ns);
	timing_bad = timing_suspicious(&timing, elapsed_ns, expected);

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
		  "gap_count=%llu segments=%llu zero_edge_segments=%llu "
		  "min_rate_q=%llu max_rate_q=%llu timing_suspect=%d\n",
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
		  (unsigned long long)timing.zero_edge_segments,
		  (unsigned long long)timing.min_rate_q,
		  (unsigned long long)timing.max_rate_q,
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
	command[len] = '\0';
	if (command[0] != '1' ||
	    (command[1] != '\0' && command[1] != '\n'))
		return -EINVAL;

	if (!mutex_trylock(&probe_lock))
		return -EBUSY;
	ret = run_measurement();
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
	debugfs_remove(probe_entry);
	probe_entry = NULL;
}

module_init(fon_tlmm_probe_init);
module_exit(fon_tlmm_probe_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("OpenWrt-FB7530 FON research");
MODULE_DESCRIPTION("One-shot read-only IPQ4019 TLMM TDM clock diagnostic");
