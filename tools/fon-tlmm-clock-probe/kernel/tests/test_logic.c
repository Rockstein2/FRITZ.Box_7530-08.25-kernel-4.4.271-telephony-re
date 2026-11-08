// SPDX-License-Identifier: GPL-2.0-only
#include <stdio.h>
#include <string.h>

#include "../fon_tlmm_probe_logic.h"

static int failures;

static void check(const char *name, int condition)
{
	if (condition) {
		printf("PASS %s\n", name);
	} else {
		printf("FAIL %s\n", name);
		failures++;
	}
}

static void check_near(const char *name, unsigned long long got,
		       unsigned long long want, unsigned long long tolerance)
{
	unsigned long long delta = got > want ? got - want : want - got;

	if (delta <= tolerance) {
		printf("PASS %s (%llu)\n", name, got);
	} else {
		printf("FAIL %s: got %llu want %llu +/- %llu\n",
		       name, got, want, tolerance);
		failures++;
	}
}

/*
 * Feed a 2 ms frequency segment in four 0.5 ms checkpoints.  The sample and
 * edge counts are supplied by the caller so a deliberately bad signal can be
 * modelled without any MMIO.
 */
static void feed_segment(struct probe_timing *t, unsigned long long samples,
			 unsigned long long edges, unsigned long long start_ns)
{
	unsigned int i;

	for (i = 1; i <= 4; i++) {
		t->samples += samples;
		t->edges += edges;
		probe_timing_checkpoint(t, start_ns + i * 500000ULL);
	}
}

static void reset(struct probe_timing *t)
{
	memset(t, 0, sizeof(*t));
	probe_timing_start(t, 0);
}

static void test_stable_fsc(void)
{
	struct probe_timing t;

	reset(&t);
	for (unsigned long long i = 0; i < 10; i++)
		feed_segment(&t, 500, 8, i * 2000000ULL);
	check("stable FSC has 10 valid segments", t.valid_segments == 10);
	check("stable FSC is accepted",
	      probe_timing_evaluate(&t, 20000000ULL, 8000ULL) == 0);
	check_near("stable FSC segment minimum", t.min_freq_hz, 8000,
		   1);
	check_near("stable FSC segment maximum", t.max_freq_hz, 8000,
		   1);
}

static void test_stable_bclk(void)
{
	struct probe_timing t;

	reset(&t);
	for (unsigned long long i = 0; i < 10; i++)
		feed_segment(&t, 5000, 1024, i * 2000000ULL);
	check("stable BCLK has 10 valid segments", t.valid_segments == 10);
	check("stable BCLK is accepted",
	      probe_timing_evaluate(&t, 20000000ULL, 1024000ULL) == 0);
	check_near("stable BCLK segment minimum", t.min_freq_hz, 1024000,
		   1);
	check_near("stable BCLK segment maximum", t.max_freq_hz, 1024000,
		   1);
}

static void test_bclk_1024355(void)
{
	struct probe_timing t;

	reset(&t);
	/*
	 * 1.024355 MHz is the OEM-reported value, not the nominal 1.024 MHz.
	 * Alternate 4096/4100 edges per 2 ms segment; the average is close to
	 * the OEM value.
	 */
	for (unsigned long long i = 0; i < 10; i++)
		feed_segment(&t, 5000, (i & 1) ? 1025 : 1024,
			     i * 2000000ULL);
	check("OEM BCLK is accepted",
	      probe_timing_evaluate(&t, 20000000ULL, 1024000ULL) == 0);
	check("OEM BCLK has valid segments", t.valid_segments == 10);
}

static void test_static(void)
{
	struct probe_timing t;

	reset(&t);
	for (unsigned long long i = 0; i < 10; i++)
		feed_segment(&t, 500, 0, i * 2000000ULL);
	check("static signal has zero edges", t.edges == 0);
	check("static signal is not timing-suspicious",
	      probe_timing_evaluate(&t, 20000000ULL, 8000ULL) == 0);
}

static void test_bad_segments(void)
{
	struct probe_timing t;

	reset(&t);
	for (unsigned long long i = 0; i < 9; i++)
		feed_segment(&t, 500, 8, i * 2000000ULL);
	/* One segment has only one edge: 250 Hz, far outside 8 kHz. */
	feed_segment(&t, 500, 1, 18000000ULL);
	check("one-edge segment is rejected",
	      probe_timing_evaluate(&t, 20000000ULL, 8000ULL) != 0);

	reset(&t);
	/* Frequency changes from 8 kHz to 4 kHz halfway through. */
	for (unsigned long long i = 0; i < 5; i++)
		feed_segment(&t, 500, 8, i * 2000000ULL);
	for (unsigned long long i = 5; i < 10; i++)
		feed_segment(&t, 500, 4, i * 2000000ULL);
	check("frequency change is rejected",
	      probe_timing_evaluate(&t, 20000000ULL, 8000ULL) != 0);

	reset(&t);
	/* Too few valid segments: only two 2 ms segments in the window. */
	for (unsigned long long i = 0; i < 2; i++)
		feed_segment(&t, 500, 8, i * 2000000ULL);
	check("too few valid segments is rejected",
	      probe_timing_evaluate(&t, 4000000ULL, 8000ULL) != 0);
}

static void test_gap(void)
{
	struct probe_timing t;

	reset(&t);
	feed_segment(&t, 500, 8, 0);
	/* No samples for a 5 ms scheduler pause. */
	probe_timing_checkpoint(&t, 7000000ULL);
	feed_segment(&t, 500, 8, 7000000ULL);
	check("scheduler gap is rejected",
	      probe_timing_evaluate(&t, 9000000ULL, 8000ULL) != 0);
	check("scheduler gap is recorded", t.max_gap_ns >= 5000000ULL);
}

static void test_missing_edges(void)
{
	struct probe_timing t;

	reset(&t);
	feed_segment(&t, 500, 8, 0);
	feed_segment(&t, 500, 8, 2000000ULL);
	feed_segment(&t, 500, 0, 4000000ULL);
	check("zero-edge segment is rejected",
	      probe_timing_evaluate(&t, 6000000ULL, 8000ULL) != 0);
}

static void test_trigger_state(void)
{
	check("idle can start", probe_trigger_can_start(PROBE_TRIGGER_IDLE));
	check("running cannot start",
	      !probe_trigger_can_start(PROBE_TRIGGER_RUNNING));
	check("result cannot restart",
	      !probe_trigger_can_start(PROBE_TRIGGER_RESULT_READY));
	check("error cannot restart",
	      !probe_trigger_can_start(PROBE_TRIGGER_ERROR_STATE));
	check("success state", probe_trigger_next_state(1) ==
	      PROBE_TRIGGER_RESULT_READY);
	check("failure state", probe_trigger_next_state(0) ==
	      PROBE_TRIGGER_ERROR_STATE);
}

static void test_low_edge_density(void)
{
	struct probe_timing t;

	reset(&t);
	/* Enough time, but only a handful of transitions per segment. */
	for (unsigned long long i = 0; i < 10; i++)
		feed_segment(&t, 500, 1, i * 2000000ULL);
	check("low edge density is rejected",
	      probe_timing_evaluate(&t, 20000000ULL, 8000ULL) != 0);
}

int main(void)
{
	test_stable_fsc();
	test_stable_bclk();
	test_bclk_1024355();
	test_static();
	test_bad_segments();
	test_gap();
	test_missing_edges();
	test_low_edge_density();
	test_trigger_state();

	printf("\n%d failure(s)\n", failures);
	return failures ? 1 : 0;
}
