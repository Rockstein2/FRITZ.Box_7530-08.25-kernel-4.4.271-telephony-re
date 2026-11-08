/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_TLMM_PROBE_LOGIC_H
#define FON_TLMM_PROBE_LOGIC_H

/*
 * Pure timing policy shared by the kernel module and its host tests.
 *
 * No MMIO, debugfs, kernel GPIO, clock or reset API is used here.  The caller
 * is responsible for reading the input bit and incrementing samples/edges.
 *
 * Two different intervals are deliberately kept separate:
 *   - gap checkpoints: frequent, for scheduler gaps and polling rate;
 *   - frequency segments: ~2 ms, for edge-count stability.
 */

#ifdef __KERNEL__
#include <linux/math64.h>
#else
#include <stdint.h>
#endif

typedef unsigned long long probe_u64;

enum probe_trigger_state {
	PROBE_TRIGGER_IDLE = 0,
	PROBE_TRIGGER_RUNNING,
	PROBE_TRIGGER_RESULT_READY,
	PROBE_TRIGGER_ERROR_STATE,
};

static inline int probe_trigger_can_start(int state)
{
	return state == PROBE_TRIGGER_IDLE;
}

static inline int probe_trigger_next_state(int success)
{
	return success ? PROBE_TRIGGER_RESULT_READY :
			 PROBE_TRIGGER_ERROR_STATE;
}

#define PROBE_SIGNIFICANT_GAP_NS	1000000ULL
#define PROBE_SEGMENT_NS		2000000ULL
#define PROBE_MIN_SEGMENT_EDGES		8ULL
#define PROBE_MIN_VALID_SEGMENTS	3ULL

struct probe_timing {
	probe_u64 samples;
	probe_u64 edges;

	/* Frequent gap checkpoints. */
	probe_u64 start_ns;
	probe_u64 last_check_ns;
	probe_u64 last_check_samples;
	probe_u64 last_check_edges;
	probe_u64 max_gap_ns;
	probe_u64 max_gap_samples;
	probe_u64 gap_total_ns;
	probe_u64 gap_count;
	probe_u64 checkpoints;

	/* Independent frequency segments. */
	probe_u64 seg_start_ns;
	probe_u64 seg_start_samples;
	probe_u64 seg_start_edges;
	probe_u64 segments;
	probe_u64 valid_segments;
	probe_u64 zero_edge_segments;
	probe_u64 low_edge_segments;
	probe_u64 min_freq_hz;
	probe_u64 max_freq_hz;
	probe_u64 min_segment_edges;
	probe_u64 max_segment_edges;
	int started;
};

static inline probe_u64 probe_div_u64(probe_u64 n, unsigned int d)
{
#ifdef __KERNEL__
	return d ? div_u64(n, d) : 0;
#else
	return d ? n / d : 0;
#endif
}

static inline void probe_timing_start(struct probe_timing *t,
				      probe_u64 now_ns)
{
	probe_u64 saved_samples = t->samples;
	probe_u64 saved_edges = t->edges;

	*t = (struct probe_timing){0};
	t->samples = saved_samples;
	t->edges = saved_edges;
	t->start_ns = now_ns;
	t->last_check_ns = now_ns;
	t->last_check_samples = saved_samples;
	t->last_check_edges = saved_edges;
	t->seg_start_ns = now_ns;
	t->seg_start_samples = saved_samples;
	t->seg_start_edges = saved_edges;
	t->started = 1;
}

static inline void probe_timing_close_segment(struct probe_timing *t,
					      probe_u64 now_ns)
{
	probe_u64 elapsed;
	probe_u64 edges;
	probe_u64 freq;

	if (!t->started || now_ns <= t->seg_start_ns)
		return;
	elapsed = now_ns - t->seg_start_ns;
	if (elapsed < PROBE_SEGMENT_NS)
		return;

	edges = t->edges - t->seg_start_edges;
	t->segments++;
	if (edges == 0)
		t->zero_edge_segments++;
	if (edges >= PROBE_MIN_SEGMENT_EDGES) {
		freq = probe_div_u64(edges * 500000000ULL,
				     (unsigned int)elapsed);
		t->valid_segments++;
		if (t->valid_segments == 1 || freq < t->min_freq_hz)
			t->min_freq_hz = freq;
		if (t->valid_segments == 1 || freq > t->max_freq_hz)
			t->max_freq_hz = freq;
		if (t->valid_segments == 1 || edges < t->min_segment_edges)
			t->min_segment_edges = edges;
		if (t->valid_segments == 1 || edges > t->max_segment_edges)
			t->max_segment_edges = edges;
	} else if (edges > 0) {
		t->low_edge_segments++;
	}

	t->seg_start_ns = now_ns;
	t->seg_start_samples = t->samples;
	t->seg_start_edges = t->edges;
}

static inline void probe_timing_checkpoint(struct probe_timing *t,
					   probe_u64 now_ns)
{
	probe_u64 gap_ns;
	probe_u64 samples_since;
	probe_u64 average_interval_ns;

	if (!t->started || now_ns <= t->last_check_ns)
		return;

	gap_ns = now_ns - t->last_check_ns;
	samples_since = t->samples - t->last_check_samples;
	t->checkpoints++;

	if (gap_ns > t->max_gap_ns) {
		t->max_gap_ns = gap_ns;
		t->max_gap_samples = samples_since;
	}

	average_interval_ns = t->samples ?
		probe_div_u64(t->last_check_ns - t->start_ns,
			      (unsigned int)t->samples) : 0;
	if (samples_since == 0) {
		if (gap_ns >= PROBE_SIGNIFICANT_GAP_NS) {
			t->gap_total_ns += gap_ns;
			t->gap_count++;
		}
	} else if (average_interval_ns > 0 &&
		   gap_ns > 8ULL * samples_since * average_interval_ns) {
		t->gap_total_ns += gap_ns;
		t->gap_count++;
	}

	probe_timing_close_segment(t, now_ns);

	t->last_check_ns = now_ns;
	t->last_check_samples = t->samples;
	t->last_check_edges = t->edges;
}

static inline int probe_timing_evaluate(const struct probe_timing *t,
					probe_u64 elapsed_ns,
					probe_u64 expected_hz)
{
	probe_u64 average_interval_ns;
	probe_u64 tolerance;
	probe_u64 ratio_tolerance;
	probe_u64 expected_edges;

	if (!t->checkpoints || t->samples < 2)
		return 0;

	average_interval_ns = probe_div_u64(elapsed_ns,
					    (unsigned int)t->samples);

	if (t->max_gap_ns >= PROBE_SIGNIFICANT_GAP_NS) {
		if (t->max_gap_samples == 0)
			return 1;
		if (t->max_gap_ns >
		    4ULL * t->max_gap_samples * average_interval_ns)
			return 1;
	}

	if (t->gap_total_ns * 100ULL > elapsed_ns * 5ULL)
		return 1;

	if (t->edges == 0)
		return 0;

	expected_edges = expected_hz / 250ULL; /* 2 ms segment */
	if (t->zero_edge_segments > 0 && expected_edges >= 4ULL)
		return 1;
	if (t->low_edge_segments > 0)
		return 1;

	if (t->valid_segments < PROBE_MIN_VALID_SEGMENTS)
		return 1;
	if (t->segments > 0 && t->valid_segments * 2ULL < t->segments)
		return 1;

	/*
	 * FSC and BCLK get different tolerances.  The numbers are policy, not
	 * a measurement; a segment outside them is deliberately inconclusive.
	 */
	if (expected_hz > 100000ULL) {
		tolerance = expected_hz / 50ULL;      /* 2 % */
		ratio_tolerance = 4ULL;               /* 4 % */
	} else {
		tolerance = expected_hz / 10ULL;      /* 10 % */
		ratio_tolerance = 20ULL;              /* 20 % */
	}

	if (t->min_freq_hz + tolerance < expected_hz ||
	    t->max_freq_hz > expected_hz + tolerance)
		return 1;

	if (t->min_freq_hz > 0 &&
	    t->max_freq_hz * 100ULL >
		    t->min_freq_hz * (100ULL + ratio_tolerance))
		return 1;

	return 0;
}

#endif /* FON_TLMM_PROBE_LOGIC_H */
