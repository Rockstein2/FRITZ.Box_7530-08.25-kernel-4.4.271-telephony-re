// SPDX-License-Identifier: GPL-2.0-only
#include "fon-tlmm-clock-probe-core.h"

void probe_counter_reset(struct probe_counter *counter)
{
	*counter = (struct probe_counter){0};
}

void probe_counter_start(struct probe_counter *counter, uint64_t start_ns)
{
	if (!counter)
		return;
	counter->timing_last_ns = start_ns;
	counter->timing_last_samples = counter->samples;
	counter->timing_last_edges = counter->edges;
	counter->timing_started = 1;
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

void probe_counter_checkpoint(struct probe_counter *counter, uint64_t now_ns)
{
	uint64_t gap_ns;
	uint64_t samples_since;
	uint64_t edges_since;

	if (!counter || !counter->timing_started)
		return;
	if (now_ns <= counter->timing_last_ns)
		return;

	gap_ns = now_ns - counter->timing_last_ns;
	samples_since = counter->samples - counter->timing_last_samples;
	edges_since = counter->edges - counter->timing_last_edges;
	counter->checkpoints++;

	if (gap_ns > counter->max_gap_ns) {
		counter->max_gap_ns = gap_ns;
		counter->max_gap_samples = samples_since;
	}
	/*
	 * Count a gap only when it is disproportionate to the samples that
	 * were collected in it.  The running average keeps normal checkpoint
	 * intervals (which differ with the achievable sample rate) from being
	 * mistaken for scheduler stalls.
	 */
	if (samples_since == 0) {
		if (gap_ns >= PROBE_SIGNIFICANT_GAP_NS) {
			counter->gap_total_ns += gap_ns;
			counter->gap_count++;
		}
	} else {
		double instantaneous = (double)gap_ns /
				       (double)samples_since;

		if (counter->timing_avg_ns_per_sample == 0.0)
			counter->timing_avg_ns_per_sample = instantaneous;
		else
			counter->timing_avg_ns_per_sample =
				0.9 * counter->timing_avg_ns_per_sample +
				0.1 * instantaneous;

		if (counter->timing_avg_ns_per_sample > 0.0 &&
		    (double)gap_ns >
			    8.0 * (double)samples_since *
				    counter->timing_avg_ns_per_sample) {
			counter->gap_total_ns += gap_ns;
			counter->gap_count++;
		}
	}

	if (samples_since > 0) {
		double segment_rate = (double)edges_since /
				      (double)samples_since;

		counter->segments++;
		if (edges_since == 0)
			counter->zero_edge_segments++;
		if (counter->min_segment_edges == 0 ||
		    edges_since < counter->min_segment_edges)
			counter->min_segment_edges = edges_since;
		if (edges_since > counter->max_segment_edges)
			counter->max_segment_edges = edges_since;
		if (!counter->have_segment_rate ||
		    segment_rate < counter->min_segment_rate)
			counter->min_segment_rate = segment_rate;
		if (!counter->have_segment_rate ||
		    segment_rate > counter->max_segment_rate)
			counter->max_segment_rate = segment_rate;
		counter->have_segment_rate = 1;
	}

	counter->timing_last_ns = now_ns;
	counter->timing_last_samples = counter->samples;
	counter->timing_last_edges = counter->edges;
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

static int timing_is_suspicious(const struct probe_counter *counter,
				double elapsed_s, double expected_hz)
{
	double elapsed_ns = elapsed_s * 1000000000.0;
	double average_interval_ns;
	double expected_edges_per_segment;

	if (counter->checkpoints == 0 || counter->samples < 2)
		return 0;

	average_interval_ns = elapsed_ns / (double)counter->samples;

	/*
	 * A long gap is suspicious when it is much longer than the time that
	 * the samples seen during that gap could explain.  A gap with zero
	 * samples is always suspicious once it exceeds 1 ms.
	 */
	if (counter->max_gap_ns >= PROBE_SIGNIFICANT_GAP_NS) {
		if (counter->max_gap_samples == 0)
			return 1;
		if ((double)counter->max_gap_ns >
		    4.0 * (double)counter->max_gap_samples *
			    average_interval_ns)
			return 1;
	}

	if ((double)counter->gap_total_ns * 100.0 > elapsed_ns * 5.0)
		return 1;

	/* Segment stability is meaningful only when transitions exist. */
	if (counter->edges == 0)
		return 0;

	/*
	 * Only judge zero-edge segments when a segment spans enough periods
	 * to expect several edges; otherwise phase alone can produce a zero.
	 */
	if (counter->segments >= 4) {
		expected_edges_per_segment =
			2.0 * expected_hz * (elapsed_s /
					     (double)counter->segments);
		if (expected_edges_per_segment >= 4.0 &&
		    counter->zero_edge_segments > 0)
			return 1;
	}

	/*
	 * A frequency change or a long dropout makes the edge density uneven.
	 * Density, not raw count, is used so a short final checkpoint segment
	 * does not look like a dropout.
	 */
	if (counter->segments >= 4 && counter->have_segment_rate &&
	    counter->min_segment_rate > 0.0 &&
	    counter->max_segment_rate > counter->min_segment_rate * 1.5)
		return 1;

	return 0;
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
		.max_gap_ns = counter ? counter->max_gap_ns : 0,
		.gap_total_ns = counter ? counter->gap_total_ns : 0,
		.gap_count = counter ? counter->gap_count : 0,
		.segments = counter ? counter->segments : 0,
		.zero_edge_segments = counter ? counter->zero_edge_segments : 0,
		.min_segment_edges = counter ? counter->min_segment_edges : 0,
		.max_segment_edges = counter ? counter->max_segment_edges : 0,
		.min_segment_rate = counter ? counter->min_segment_rate : 0.0,
		.max_segment_rate = counter ? counter->max_segment_rate : 0.0,
		.timing_suspect = 0,
	};

	if (!counter || elapsed_s <= 0.0 || counter->samples < 2)
		return result;

	result.sample_rate_hz = (double)counter->samples / elapsed_s;
	result.frequency_hz = (double)counter->edges / (2.0 * elapsed_s);

	if (expected_hz <= 0.0 || min_oversampling <= 0.0) {
		result.status = PROBE_ERROR;
		return result;
	}

	result.timing_suspect = timing_is_suspicious(counter, elapsed_s,
						     expected_hz);
	if (result.timing_suspect) {
		result.status = PROBE_INCONCLUSIVE;
		return result;
	}

	if (counter->edges == 0) {
		if (result.sample_rate_hz >= expected_hz * min_oversampling &&
		    elapsed_s >= min_duration_s)
			result.status = PROBE_STATIC_OBSERVED;
		else
			result.status = PROBE_INCONCLUSIVE;
		return result;
	}

	if (counter->edges < 2 ||
	    result.sample_rate_hz < expected_hz * min_oversampling ||
	    elapsed_s < min_duration_s) {
		result.status = PROBE_DETECTED;
		return result;
	}

	/*
	 * A transition stream outside the plausible range is not a reliable
	 * TDM clock.  Keep it as DETECTED and let the operator inspect the
	 * edges; do not print a confident frequency.
	 */
	if (result.frequency_hz < expected_hz * 0.5 ||
	    result.frequency_hz > expected_hz * 2.0) {
		result.status = PROBE_DETECTED;
		return result;
	}

	result.status = PROBE_FREQUENCY_ESTIMATED;
	return result;
}
