// SPDX-License-Identifier: GPL-2.0-only
#include "fon-tlmm-clock-probe-core.h"

void probe_counter_reset(struct probe_counter *counter)
{
	counter->samples = 0;
	counter->edges = 0;
	counter->last_level = 0;
	counter->have_last = 0;
}

void probe_counter_sample(struct probe_counter *counter, unsigned int level)
{
	level &= 1u;

	if (counter->have_last && level != (unsigned int)counter->last_level)
		counter->edges++;

	counter->last_level = (int)level;
	counter->have_last = 1;
	counter->samples++;
}

const char *probe_status_name(enum probe_status status)
{
	switch (status) {
	case PROBE_STATIC_OBSERVED:
		return "STATIC_OBSERVED";
	case PROBE_DETECTED:
		return "DETECTED";
	case PROBE_FREQUENCY_ESTIMATED:
		return "FREQUENCY_ESTIMATED";
	case PROBE_INCONCLUSIVE:
		return "INCONCLUSIVE";
	case PROBE_ERROR:
	default:
		return "ERROR";
	}
}

struct probe_result probe_finalize(const struct probe_counter *counter,
				   double elapsed_s,
				   double expected_hz,
				   double min_duration_s,
				   double min_oversampling)
{
	struct probe_result result = {
		.samples = counter ? counter->samples : 0,
		.edges = counter ? counter->edges : 0,
		.elapsed_s = elapsed_s,
		.sample_rate_hz = 0.0,
		.frequency_hz = 0.0,
		.status = PROBE_ERROR,
	};

	if (!counter || elapsed_s <= 0.0 || counter->samples < 2)
		return result;

	result.sample_rate_hz = (double)counter->samples / elapsed_s;
	result.frequency_hz = (double)counter->edges / (2.0 * elapsed_s);

	if (expected_hz <= 0.0 || min_oversampling <= 0.0) {
		result.status = PROBE_ERROR;
		return result;
	}

	/*
	 * A zero-edge result is only meaningful when the sampling rate is
	 * comfortably above the expected signal.  Below that limit it is
	 * impossible to distinguish "no clock" from aliasing or a signal that
	 * falls between samples.
	 */
	if (counter->edges == 0) {
		if (result.sample_rate_hz >= expected_hz * min_oversampling &&
		    elapsed_s >= min_duration_s)
			result.status = PROBE_STATIC_OBSERVED;
		else
			result.status = PROBE_INCONCLUSIVE;
		return result;
	}

	if (counter->edges >= 2 &&
	    result.sample_rate_hz >= expected_hz * min_oversampling &&
	    elapsed_s >= min_duration_s)
		result.status = PROBE_FREQUENCY_ESTIMATED;
	else
		result.status = PROBE_DETECTED;

	return result;
}
