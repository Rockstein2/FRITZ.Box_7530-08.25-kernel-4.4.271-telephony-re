/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_TLMM_CLOCK_PROBE_CORE_H
#define FON_TLMM_CLOCK_PROBE_CORE_H

#include <stdint.h>

/*
 * Pure edge-counter core shared by the hardware loop and the offline tests.
 * It never touches memory-mapped I/O; the caller supplies one input level per
 * sample.  One complete period is two transitions.
 *
 * The caller must also call probe_counter_start() before the first sample and
 * probe_counter_checkpoint() at a bounded interval.  Checkpoints provide the
 * timing evidence used to reject a measurement interrupted by the scheduler.
 */

#define PROBE_SIGNIFICANT_GAP_NS 1000000ULL

enum probe_status {
	PROBE_ERROR = 0,
	PROBE_STATIC_OBSERVED,
	PROBE_DETECTED,
	PROBE_FREQUENCY_ESTIMATED,
	PROBE_INCONCLUSIVE,
};

struct probe_counter {
	uint64_t samples;
	uint64_t edges;
	int last_level;
	int have_last;

	/* Timing checkpoints; all fields are zero until the first start. */
	uint64_t timing_last_ns;
	uint64_t timing_last_samples;
	uint64_t timing_last_edges;
	uint64_t max_gap_ns;
	uint64_t max_gap_samples;
	uint64_t gap_total_ns;
	double timing_avg_ns_per_sample;
	uint64_t gap_count;
	uint64_t checkpoints;
	uint64_t segments;
	uint64_t zero_edge_segments;
	uint64_t min_segment_edges;
	uint64_t max_segment_edges;
	double min_segment_rate;
	double max_segment_rate;
	int have_segment_rate;
	int timing_started;
};

struct probe_result {
	uint64_t samples;
	uint64_t edges;
	double elapsed_s;
	double sample_rate_hz;
	double frequency_hz;
	enum probe_status status;
	uint64_t max_gap_ns;
	uint64_t gap_total_ns;
	uint64_t gap_count;
	uint64_t segments;
	uint64_t zero_edge_segments;
	uint64_t min_segment_edges;
	uint64_t max_segment_edges;
	double min_segment_rate;
	double max_segment_rate;
	int timing_suspect;
};

void probe_counter_reset(struct probe_counter *counter);
void probe_counter_start(struct probe_counter *counter, uint64_t start_ns);
void probe_counter_sample(struct probe_counter *counter, unsigned int level);
void probe_counter_checkpoint(struct probe_counter *counter, uint64_t now_ns);

/*
 * expected_hz       nominal signal frequency; also used for plausibility
 * min_duration_s    minimum observation time for a confident static result
 * min_oversampling  required sample_rate / expected_hz for a frequency
 *                   estimate; below it, detected edges are reported as
 *                   DETECTED rather than FREQUENCY_ESTIMATED.
 */
struct probe_result probe_finalize(const struct probe_counter *counter,
				   double elapsed_s,
				   double expected_hz,
				   double min_duration_s,
				   double min_oversampling);

const char *probe_status_name(enum probe_status status);

#endif /* FON_TLMM_CLOCK_PROBE_CORE_H */
