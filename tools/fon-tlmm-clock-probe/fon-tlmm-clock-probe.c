// SPDX-License-Identifier: GPL-2.0-only
/*
 * Read-only TLMM input-level probe for the IPQ4019 TDM clock candidates.
 *
 * This program maps the TLMM register window with PROT_READ only.  It never
 * writes a register, never requests a GPIO through the GPIO character device,
 * never changes pinmux, and never touches clocks or reset.
 *
 * It is a diagnostic instrument, not a driver.  A positive edge count proves
 * only that the IPQ4019 input path saw transitions; it does not prove the
 * physical connection to the SC14448, signal amplitude or signal quality.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include "fon-tlmm-clock-probe-core.h"

#define TLMM_BASE		0x01000000UL
#define TLMM_GPIO_STRIDE	0x1000UL
#define TLMM_GPIO_CFG_OFF	0x0UL
#define TLMM_GPIO_IO_OFF	0x4UL
#define TLMM_MAX_GPIO		40
#define TLMM_MAP_SIZE		((TLMM_MAX_GPIO + 1) * TLMM_GPIO_STRIDE)

#define DEFAULT_DURATION_MS	200UL
#define HARD_MAX_DURATION_MS	2000UL
#define DEFAULT_MIN_OVERSAMPLING 4.0

#define FSC_EXPECTED_HZ		8000.0
#define BCLK_EXPECTED_HZ	1024000.0

struct pin_info {
	int gpio;
	const char *name;
};

struct measure_plan {
	int gpio;
	const char *signal;
	double expected_hz;
};

static const struct pin_info inspect_pins[] = {
	{ 20, "MCL" },
	{ 21, "DCL" },
	{ 22, "FSC" },
	{ 23, "DI" },
	{ 24, "MCL_2" },
	{ 25, "DCL_2" },
	{ 26, "FSC_2" },
	{ 27, "DO" },
	{ 40, "RESET" },
};

static const struct measure_plan fsc_plans[] = {
	{ 22, "FSC", FSC_EXPECTED_HZ },
	{ 26, "FSC_2", FSC_EXPECTED_HZ },
};

static const struct measure_plan bclk_plans[] = {
	{ 21, "DCL", BCLK_EXPECTED_HZ },
	{ 25, "DCL_2", BCLK_EXPECTED_HZ },
};

static const struct measure_plan all_plans[] = {
	{ 21, "DCL", BCLK_EXPECTED_HZ },
	{ 22, "FSC", FSC_EXPECTED_HZ },
	{ 25, "DCL_2", BCLK_EXPECTED_HZ },
	{ 26, "FSC_2", FSC_EXPECTED_HZ },
};

static volatile uint32_t *tlmm;
static void *tlmm_map;
static size_t tlmm_map_len;

static void usage(FILE *out)
{
	fprintf(out,
		"usage: fon-tlmm-clock-probe MODE [options]\n"
		"\n"
		"Modes (exactly one):\n"
		"  --inspect          print CFG/IO for GPIO20-27 and GPIO40\n"
		"  --measure-fsc      measure GPIO22 and GPIO26 (FSC candidates)\n"
		"  --measure-bclk     measure GPIO21 and GPIO25 (DCL/BCLK candidates)\n"
		"  --measure-all      measure GPIO21,22,25,26\n"
		"\n"
		"Options:\n"
		"  --dry-run          print the plan and do not open /dev/mem\n"
		"  --duration-ms N    observation time per pin, default %lu, max %lu\n"
		"  --max-duration-ms N  lower cap, default %lu, cannot exceed %lu\n"
		"  --min-oversampling X  required sample rate / expected Hz, default %.1f\n"
		"  --help             show this text\n"
		"\n"
		"The program only reads the TLMM CFG and IO registers.  It never writes\n"
		"MMIO, never requests GPIO lines and never changes pinmux, clocks or reset.\n",
		DEFAULT_DURATION_MS, HARD_MAX_DURATION_MS, HARD_MAX_DURATION_MS,
		HARD_MAX_DURATION_MS, DEFAULT_MIN_OVERSAMPLING);
}

static uint32_t reg_read(size_t off)
{
	return tlmm[off / sizeof(uint32_t)];
}

static size_t gpio_cfg_off(int gpio)
{
	return (size_t)gpio * TLMM_GPIO_STRIDE + TLMM_GPIO_CFG_OFF;
}

static size_t gpio_io_off(int gpio)
{
	return (size_t)gpio * TLMM_GPIO_STRIDE + TLMM_GPIO_IO_OFF;
}

static unsigned int cfg_func(uint32_t cfg)
{
	return (cfg >> 2) & 0xf;
}

static unsigned int cfg_oe(uint32_t cfg)
{
	return (cfg >> 9) & 1;
}

static double elapsed_seconds(const struct timespec *start,
			      const struct timespec *end)
{
	return (double)(end->tv_sec - start->tv_sec) +
	       (double)(end->tv_nsec - start->tv_nsec) / 1000000000.0;
}

static int open_tlmm(void)
{
	long page = sysconf(_SC_PAGESIZE);
	off_t base;
	size_t delta;
	int fd;

	if (page <= 0) {
		fprintf(stderr, "error: cannot determine page size\n");
		return -1;
	}

	base = (off_t)(TLMM_BASE & ~((unsigned long)page - 1UL));
	delta = (size_t)(TLMM_BASE - (unsigned long)base);
	tlmm_map_len = TLMM_MAP_SIZE + delta;

	fd = open("/dev/mem", O_RDONLY | O_SYNC);
	if (fd < 0) {
		fprintf(stderr,
			"error: open /dev/mem: %s\n"
			"hint: stock OpenWrt 25.12.6 has CONFIG_DEVMEM disabled; "
			"use a reviewed test kernel or the kernel-side variant\n",
			strerror(errno));
		return -1;
	}

	tlmm_map = mmap(NULL, tlmm_map_len, PROT_READ, MAP_SHARED, fd, base);
	close(fd);
	if (tlmm_map == MAP_FAILED) {
		fprintf(stderr, "error: mmap TLMM: %s\n", strerror(errno));
		return -1;
	}

	tlmm = (volatile uint32_t *)((volatile unsigned char *)tlmm_map + delta);
	return 0;
}

static void close_tlmm(void)
{
	if (tlmm_map && tlmm_map != MAP_FAILED)
		munmap(tlmm_map, tlmm_map_len);
	tlmm_map = NULL;
	tlmm = NULL;
	tlmm_map_len = 0;
}

static void print_inspect(void)
{
	size_t i;

	for (i = 0; i < sizeof(inspect_pins) / sizeof(inspect_pins[0]); i++) {
		const struct pin_info *pin = &inspect_pins[i];
		uint32_t cfg = reg_read(gpio_cfg_off(pin->gpio));
		uint32_t io = reg_read(gpio_io_off(pin->gpio));

		printf("inspect gpio=%d name=%s address=0x%08lx "
		       "cfg=0x%08x io=0x%08x func=%u oe=%u input=%u\n",
		       pin->gpio, pin->name,
		       (unsigned long)(TLMM_BASE + gpio_io_off(pin->gpio)),
		       cfg, io, cfg_func(cfg), cfg_oe(cfg), io & 1u);
	}
}

static void print_plan(const struct measure_plan *plans, size_t count,
		       unsigned long duration_ms, double min_oversampling)
{
	size_t i;

	printf("dry-run mode=measure duration_ms=%lu min_oversampling=%.1f "
	       "tlmm_base=0x%08lx map_size=0x%lx\n",
	       duration_ms, min_oversampling, (unsigned long)TLMM_BASE,
	       (unsigned long)TLMM_MAP_SIZE);

	for (i = 0; i < count; i++) {
		printf("dry-run gpio=%d signal=%s expected_hz=%.1f "
		       "cfg_address=0x%08lx io_address=0x%08lx\n",
		       plans[i].gpio, plans[i].signal, plans[i].expected_hz,
		       (unsigned long)(TLMM_BASE + gpio_cfg_off(plans[i].gpio)),
		       (unsigned long)(TLMM_BASE + gpio_io_off(plans[i].gpio)));
	}
}

static int measure_one(const struct measure_plan *plan,
		       double duration_s, double min_oversampling)
{
	struct probe_counter counter;
	struct probe_result result;
	struct timespec start, now;
	uint32_t cfg_before, cfg_after;
	uint32_t io_now = 0;
	double elapsed;
	int clock_ok = 1;

	cfg_before = reg_read(gpio_cfg_off(plan->gpio));
	probe_counter_reset(&counter);

	if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) {
		fprintf(stderr, "error: clock_gettime: %s\n", strerror(errno));
		return -1;
	}

	for (;;) {
		io_now = reg_read(gpio_io_off(plan->gpio));
		probe_counter_sample(&counter, io_now & 1u);

		/*
		 * Do not call clock_gettime() on every sample.  The check is
		 * frequent enough to bound overshoot but leaves the inner loop
		 * dominated by MMIO reads.
		 */
		if ((counter.samples & 0xffu) != 0)
			continue;

		if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
			clock_ok = 0;
			break;
		}
		elapsed = elapsed_seconds(&start, &now);
		if (elapsed >= duration_s)
			break;
	}

	if (!clock_ok) {
		fprintf(stderr, "error: clock_gettime failed during measurement\n");
		return -1;
	}

	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
		fprintf(stderr, "error: clock_gettime: %s\n", strerror(errno));
		return -1;
	}

	elapsed = elapsed_seconds(&start, &now);
	cfg_after = reg_read(gpio_cfg_off(plan->gpio));
	result = probe_finalize(&counter, elapsed, plan->expected_hz,
				duration_s / 4.0, min_oversampling);

	/*
	 * We did not write CFG.  If it changed, another agent is active and the
	 * measurement must not be treated as a clean result.
	 */
	if (cfg_before != cfg_after)
		result.status = PROBE_INCONCLUSIVE;

	printf("gpio=%d signal=%s address=0x%08lx cfg=0x%08x io=0x%08x "
	       "func=%u oe=%u input=%u samples=%" PRIu64 " edges=%" PRIu64
	       " elapsed_s=%.6f sample_rate_hz=%.1f freq_hz=%.1f "
	       "status=%s cfg_changed=%u\n",
	       plan->gpio, plan->signal,
	       (unsigned long)(TLMM_BASE + gpio_io_off(plan->gpio)),
	       cfg_before, io_now, cfg_func(cfg_before), cfg_oe(cfg_before),
	       io_now & 1u, result.samples,
	       result.edges, result.elapsed_s, result.sample_rate_hz,
	       result.frequency_hz, probe_status_name(result.status),
	       cfg_before != cfg_after);

	if (result.status == PROBE_ERROR)
		return -1;
	if (result.status == PROBE_INCONCLUSIVE)
		return 1;
	return 0;
}

static int parse_ulong(const char *text, unsigned long *value)
{
	char *end = NULL;
	unsigned long parsed;

	errno = 0;
	parsed = strtoul(text, &end, 0);
	if (errno || !end || *end != '\0')
		return -1;
	*value = parsed;
	return 0;
}

static int parse_double(const char *text, double *value)
{
	char *end = NULL;
	double parsed;

	errno = 0;
	parsed = strtod(text, &end);
	if (errno || !end || *end != '\0' || parsed <= 0.0)
		return -1;
	*value = parsed;
	return 0;
}

int main(int argc, char **argv)
{
	enum {
		MODE_NONE = 0,
		MODE_INSPECT,
		MODE_FSC,
		MODE_BCLK,
		MODE_ALL,
	} mode = MODE_NONE;
	unsigned long duration_ms = DEFAULT_DURATION_MS;
	unsigned long max_duration_ms = HARD_MAX_DURATION_MS;
	double min_oversampling = DEFAULT_MIN_OVERSAMPLING;
	const struct measure_plan *plans = NULL;
	size_t plan_count = 0;
	int dry_run = 0;
	int option;
	int i;
	int rc = 0;

	static const struct option long_options[] = {
		{ "inspect", no_argument, NULL, 'i' },
		{ "measure-fsc", no_argument, NULL, 'f' },
		{ "measure-bclk", no_argument, NULL, 'b' },
		{ "measure-all", no_argument, NULL, 'a' },
		{ "dry-run", no_argument, NULL, 'n' },
		{ "duration-ms", required_argument, NULL, 'd' },
		{ "max-duration-ms", required_argument, NULL, 'm' },
		{ "min-oversampling", required_argument, NULL, 'o' },
		{ "help", no_argument, NULL, 'h' },
		{ NULL, 0, NULL, 0 },
	};

	while ((option = getopt_long(argc, argv, "ifband:m:o:h",
				     long_options, NULL)) != -1) {
		switch (option) {
		case 'i':
			if (mode != MODE_NONE) {
				fprintf(stderr, "error: choose one mode\n");
				return 2;
			}
			mode = MODE_INSPECT;
			break;
		case 'f':
			if (mode != MODE_NONE) {
				fprintf(stderr, "error: choose one mode\n");
				return 2;
			}
			mode = MODE_FSC;
			break;
		case 'b':
			if (mode != MODE_NONE) {
				fprintf(stderr, "error: choose one mode\n");
				return 2;
			}
			mode = MODE_BCLK;
			break;
		case 'a':
			if (mode != MODE_NONE) {
				fprintf(stderr, "error: choose one mode\n");
				return 2;
			}
			mode = MODE_ALL;
			break;
		case 'n':
			dry_run = 1;
			break;
		case 'd':
			if (parse_ulong(optarg, &duration_ms) != 0) {
				fprintf(stderr, "error: bad --duration-ms\n");
				return 2;
			}
			break;
		case 'm':
			if (parse_ulong(optarg, &max_duration_ms) != 0) {
				fprintf(stderr, "error: bad --max-duration-ms\n");
				return 2;
			}
			break;
		case 'o':
			if (parse_double(optarg, &min_oversampling) != 0) {
				fprintf(stderr, "error: bad --min-oversampling\n");
				return 2;
			}
			break;
		case 'h':
			usage(stdout);
			return 0;
		default:
			usage(stderr);
			return 2;
		}
	}

	if (optind != argc) {
		fprintf(stderr, "error: unexpected argument: %s\n", argv[optind]);
		return 2;
	}
	if (mode == MODE_NONE) {
		fprintf(stderr, "error: no mode selected\n");
		usage(stderr);
		return 2;
	}
	if (max_duration_ms < 10 || max_duration_ms > HARD_MAX_DURATION_MS) {
		fprintf(stderr, "error: --max-duration-ms must be 10..%lu\n",
			HARD_MAX_DURATION_MS);
		return 2;
	}
	if (duration_ms < 10 || duration_ms > max_duration_ms) {
		fprintf(stderr,
			"error: --duration-ms must be 10..%lu (<= max)\n",
			max_duration_ms);
		return 2;
	}
	if (min_oversampling < 2.0) {
		fprintf(stderr,
			"error: --min-oversampling must be >= 2.0\n");
		return 2;
	}

	switch (mode) {
	case MODE_FSC:
		plans = fsc_plans;
		plan_count = sizeof(fsc_plans) / sizeof(fsc_plans[0]);
		break;
	case MODE_BCLK:
		plans = bclk_plans;
		plan_count = sizeof(bclk_plans) / sizeof(bclk_plans[0]);
		break;
	case MODE_ALL:
		plans = all_plans;
		plan_count = sizeof(all_plans) / sizeof(all_plans[0]);
		break;
	case MODE_INSPECT:
	case MODE_NONE:
	default:
		break;
	}

	if (dry_run) {
		if (mode == MODE_INSPECT) {
			printf("dry-run mode=inspect tlmm_base=0x%08lx "
			       "map_size=0x%lx\n",
			       (unsigned long)TLMM_BASE,
			       (unsigned long)TLMM_MAP_SIZE);
			for (i = 0; i < (int)(sizeof(inspect_pins) /
					      sizeof(inspect_pins[0])); i++)
				printf("dry-run gpio=%d name=%s "
				       "cfg_address=0x%08lx io_address=0x%08lx\n",
				       inspect_pins[i].gpio, inspect_pins[i].name,
				       (unsigned long)(TLMM_BASE +
				       gpio_cfg_off(inspect_pins[i].gpio)),
				       (unsigned long)(TLMM_BASE +
				       gpio_io_off(inspect_pins[i].gpio)));
			return 0;
		}
		print_plan(plans, plan_count, duration_ms, min_oversampling);
		return 0;
	}

	if (open_tlmm() != 0)
		return 3;

	if (mode == MODE_INSPECT) {
		print_inspect();
		close_tlmm();
		return 0;
	}

	for (i = 0; i < (int)plan_count; i++) {
		int one = measure_one(&plans[i], (double)duration_ms / 1000.0,
				      min_oversampling);
		if (one < 0)
			rc = 6;
		else if (one > 0 && rc == 0)
			rc = 5;
	}

	close_tlmm();
	return rc;
}
