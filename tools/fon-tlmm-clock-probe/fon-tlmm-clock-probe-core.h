/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_TLMM_CLOCK_PROBE_CORE_H
#define FON_TLMM_CLOCK_PROBE_CORE_H

#include <stdint.h>

/*
 * Pure edge-counter core shared by the hardware loop and the offline tests.
 * It never touches memory-mapped I/O; the caller supplies one input level per
 * sample.  One complete period is two transitions.
 */

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
};

struct probe_result {
	uint64_t samples;
	uint64_t edges;
	double elapsed_s;
	double sample_rate_hz;
	double frequency_hz;
	enum probe_status status;
};

void probe_counter_reset(struct probe_counter *counter);
void probe_counter_sample(struct probe_counter *counter, unsigned int level);

/*
 * expected_hz       nominal signal frequency, used only to judge sampling
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
