// SPDX-License-Identifier: GPL-2.0-only
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "fon-tlmm-clock-probe-core.h"

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

static void check_near(const char *name, double got, double want,
		       double tolerance)
{
	double delta = got - want;

	if (delta < 0.0)
		delta = -delta;
	if (delta <= tolerance) {
		printf("PASS %s (%.3f)\n", name, got);
	} else {
		printf("FAIL %s: got %.3f want %.3f +/- %.3f\n",
		       name, got, want, tolerance);
		failures++;
	}
}

static void feed_static(struct probe_counter *counter, unsigned int level,
			uint64_t samples)
{
	uint64_t i;

	for (i = 0; i < samples; i++)
		probe_counter_sample(counter, level);
}

static uint64_t feed_wave(struct probe_counter *counter, uint64_t freq_hz,
			  uint64_t sample_rate_hz, double duration_s)
{
	uint64_t samples = (uint64_t)((double)sample_rate_hz * duration_s);
	uint64_t i;

	for (i = 0; i < samples; i++) {
		/*
		 * Integer square wave: two half-periods make one period.  This
		 * intentionally produces a small quantisation error, just like
		 * a real sampled signal.
		 */
		uint64_t phase = (i * freq_hz * 2u) / sample_rate_hz;
		probe_counter_sample(counter, (unsigned int)(phase & 1u));
	}

	return samples;
}

static struct probe_result result_for(const struct probe_counter *counter,
				      uint64_t samples, uint64_t sample_rate_hz,
				      double duration_s, double expected_hz,
				      double min_duration_s,
				      double min_oversampling)
{
	(void)samples;
	(void)sample_rate_hz;
	return probe_finalize(counter, duration_s, expected_hz,
			      min_duration_s, min_oversampling);
}

int main(void)
{
	struct probe_counter counter;
	struct probe_result result;
	uint64_t samples;

	probe_counter_reset(&counter);
	check("reset clears samples", counter.samples == 0);
	check("reset clears edges", counter.edges == 0);
	check("reset clears first-sample flag", counter.have_last == 0);

	probe_counter_reset(&counter);
	feed_static(&counter, 0, 100000);
	result = result_for(&counter, 100000, 1000000, 0.1, 8000.0, 0.05, 4.0);
	check("static low is STATIC_OBSERVED",
	      result.status == PROBE_STATIC_OBSERVED);
	check("static low has zero edges", result.edges == 0);

	probe_counter_reset(&counter);
	feed_static(&counter, 1, 100000);
	result = result_for(&counter, 100000, 1000000, 0.1, 8000.0, 0.05, 4.0);
	check("static high is STATIC_OBSERVED",
	      result.status == PROBE_STATIC_OBSERVED);
	check("static high has zero edges", result.edges == 0);

	probe_counter_reset(&counter);
	samples = feed_wave(&counter, 8000, 1000000, 0.2);
	result = result_for(&counter, samples, 1000000, 0.2, 8000.0, 0.05, 4.0);
	check("8 kHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("8 kHz estimate", result.frequency_hz, 8000.0, 80.0);
	check("8 kHz sample rate is reported",
	      result.sample_rate_hz > 990000.0 &&
	      result.sample_rate_hz < 1010000.0);

	probe_counter_reset(&counter);
	samples = feed_wave(&counter, 1024000, 10000000, 0.1);
	result = result_for(&counter, samples, 10000000, 0.1,
			    1024000.0, 0.05, 4.0);
	check("1.024 MHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("1.024 MHz estimate", result.frequency_hz, 1024000.0,
		   20000.0);

	probe_counter_reset(&counter);
	samples = feed_wave(&counter, 1025000, 10000000, 0.1);
	result = result_for(&counter, samples, 10000000, 0.1,
			    1024000.0, 0.05, 4.0);
	check("1.025 MHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("1.025 MHz estimate", result.frequency_hz, 1025000.0,
		   20000.0);

	/*
	 * 2 MS/s is below the 4x oversampling requirement for 1.024 MHz.
	 * Edges are visible, but the frequency must not be presented as a
	 * reliable estimate.
	 */
	probe_counter_reset(&counter);
	samples = feed_wave(&counter, 1024000, 2000000, 0.2);
	result = result_for(&counter, samples, 2000000, 0.2,
			    1024000.0, 0.05, 4.0);
	check("undersampled BCLK is DETECTED, not estimated",
	      result.status == PROBE_DETECTED);
	check("undersampled BCLK still has edges", result.edges > 0);

	probe_counter_reset(&counter);
	feed_static(&counter, 0, 1000);
	result = result_for(&counter, 1000, 1000, 1.0, 8000.0, 0.05, 4.0);
	check("slow static read is INCONCLUSIVE",
	      result.status == PROBE_INCONCLUSIVE);

	/*
	 * A sampling gap makes the frequency estimate low.  The core cannot
	 * know that the gap happened; it must not silently turn this into a
	 * confident estimate.  This test documents the arithmetic.
	 */
	probe_counter_reset(&counter);
	feed_wave(&counter, 8000, 1000000, 0.1);
	result = probe_finalize(&counter, 0.15, 8000.0, 0.05, 4.0);
	check("sampling gap still yields a frequency estimate",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check("sampling gap lowers the frequency estimate",
	      result.frequency_hz < 7000.0);

	/*
	 * Alternating samples are noise, not a clock.  The estimator will
	 * report a high frequency; the runbook requires a waveform/context
	 * check before treating it as TDM.
	 */
	probe_counter_reset(&counter);
	feed_wave(&counter, 500000, 1000000, 0.1);
	result = result_for(&counter, 100000, 1000000, 0.1,
			    8000.0, 0.05, 4.0);
	check("noise-like toggling is detected",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check("noise-like toggling produces a high estimate",
	      result.frequency_hz > 400000.0);

	probe_counter_reset(&counter);
	probe_counter_sample(&counter, 0);
	probe_counter_sample(&counter, 1);
	feed_static(&counter, 1, 1000);
	result = probe_finalize(&counter, 0.1, 8000.0, 0.05, 4.0);
	check("a single edge is DETECTED, not estimated",
	      result.status == PROBE_DETECTED);

	probe_counter_reset(&counter);
	probe_counter_sample(&counter, 1);
	result = probe_finalize(&counter, 0.1, 8000.0, 0.05, 4.0);
	check("fewer than two samples is ERROR",
	      result.status == PROBE_ERROR);

	probe_counter_reset(&counter);
	samples = feed_wave(&counter, 8000, 1000000, 0.01);
	result = result_for(&counter, samples, 1000000, 0.01, 8000.0, 0.05, 4.0);
	check("short 8 kHz observation is DETECTED, not estimated",
	      result.status == PROBE_DETECTED);

	probe_counter_reset(&counter);
	result = probe_finalize(&counter, 0.0, 8000.0, 0.05, 4.0);
	check("zero elapsed is ERROR", result.status == PROBE_ERROR);

	probe_counter_reset(&counter);
	feed_static(&counter, 1, 100);
	result = probe_finalize(&counter, 0.1, 0.0, 0.05, 4.0);
	check("zero expected frequency is ERROR", result.status == PROBE_ERROR);

	check("status name STATIC_OBSERVED",
	      strcmp(probe_status_name(PROBE_STATIC_OBSERVED),
		     "STATIC_OBSERVED") == 0);
	check("status name DETECTED",
	      strcmp(probe_status_name(PROBE_DETECTED), "DETECTED") == 0);
	check("status name FREQUENCY_ESTIMATED",
	      strcmp(probe_status_name(PROBE_FREQUENCY_ESTIMATED),
		     "FREQUENCY_ESTIMATED") == 0);
	check("status name INCONCLUSIVE",
	      strcmp(probe_status_name(PROBE_INCONCLUSIVE),
		     "INCONCLUSIVE") == 0);
	check("status name ERROR",
	      strcmp(probe_status_name(PROBE_ERROR), "ERROR") == 0);

	printf("\n%d failure(s)\n", failures);
	return failures ? 1 : 0;
}
