// SPDX-License-Identifier: GPL-2.0-only
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

static uint64_t time_at(uint64_t start_ns, uint64_t samples,
			uint64_t sample_rate_hz)
{
	return start_ns + (samples * 1000000000ULL) / sample_rate_hz;
}

static uint64_t feed_wave(struct probe_counter *counter, uint64_t freq_hz,
			  uint64_t sample_rate_hz, double duration_s,
			  uint64_t check_every, uint64_t start_ns)
{
	uint64_t samples = (uint64_t)((double)sample_rate_hz * duration_s);
	uint64_t i;
	uint64_t end_ns = time_at(start_ns, samples, sample_rate_hz);

	for (i = 0; i < samples; i++) {
		uint64_t phase = (i * freq_hz * 2u) / sample_rate_hz;
		probe_counter_sample(counter, (unsigned int)(phase & 1u));
		if ((i + 1) % check_every == 0)
			probe_counter_checkpoint(counter,
						 time_at(start_ns, i + 1,
							 sample_rate_hz));
	}
	if (samples % check_every != 0)
		probe_counter_checkpoint(counter, end_ns);
	return end_ns;
}

static uint64_t feed_static(struct probe_counter *counter,
			    unsigned int level, uint64_t sample_rate_hz,
			    double duration_s, uint64_t check_every,
			    uint64_t start_ns)
{
	uint64_t samples = (uint64_t)((double)sample_rate_hz * duration_s);
	uint64_t i;
	uint64_t end_ns = time_at(start_ns, samples, sample_rate_hz);

	for (i = 0; i < samples; i++) {
		probe_counter_sample(counter, level);
		if ((i + 1) % check_every == 0)
			probe_counter_checkpoint(counter,
						 time_at(start_ns, i + 1,
							 sample_rate_hz));
	}
	if (samples % check_every != 0)
		probe_counter_checkpoint(counter, end_ns);
	return end_ns;
}

static struct probe_result run_wave(uint64_t freq_hz,
				    uint64_t sample_rate_hz,
				    double duration_s, double expected_hz,
				    uint64_t check_every,
				    double min_duration_s)
{
	struct probe_counter counter;
	uint64_t end_ns;

	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	end_ns = feed_wave(&counter, freq_hz, sample_rate_hz, duration_s,
			   check_every, 0);
	return probe_finalize(&counter, (double)end_ns / 1000000000.0,
			      expected_hz, min_duration_s, 4.0);
}

static struct probe_result run_static(unsigned int level,
				      uint64_t sample_rate_hz,
				      double duration_s, double expected_hz,
				      uint64_t check_every,
				      double min_duration_s)
{
	struct probe_counter counter;
	uint64_t end_ns;

	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	end_ns = feed_static(&counter, level, sample_rate_hz, duration_s,
			     check_every, 0);
	return probe_finalize(&counter, (double)end_ns / 1000000000.0,
			      expected_hz, min_duration_s, 4.0);
}

static void test_reset_and_timing(void)
{
	struct probe_counter counter;

	probe_counter_reset(&counter);
	check("reset clears samples", counter.samples == 0);
	check("reset clears edges", counter.edges == 0);
	check("reset clears first-sample flag", counter.have_last == 0);
	check("reset clears timing", counter.timing_started == 0);

	probe_counter_start(&counter, 1000);
	check("start sets timing", counter.timing_started == 1);
	check("start records timestamp", counter.timing_last_ns == 1000);

	probe_counter_sample(&counter, 0);
	probe_counter_sample(&counter, 1);
	probe_counter_checkpoint(&counter, 2000);
	check("one transition counted", counter.edges == 1);
	check("checkpoint counted", counter.checkpoints == 1);
	check("segment counted", counter.segments == 1);

	probe_counter_checkpoint(&counter, 2000);
	check("non-monotonic checkpoint ignored", counter.checkpoints == 1);
}

static void test_static(void)
{
	struct probe_result result;

	result = run_static(0, 1000000, 0.1, 8000.0, 256, 0.05);
	check("static low is STATIC_OBSERVED",
	      result.status == PROBE_STATIC_OBSERVED);
	check("static low has zero edges", result.edges == 0);

	result = run_static(1, 1000000, 0.1, 8000.0, 256, 0.05);
	check("static high is STATIC_OBSERVED",
	      result.status == PROBE_STATIC_OBSERVED);
	check("static high has zero edges", result.edges == 0);

	result = run_static(0, 1000, 1.0, 8000.0, 64, 0.05);
	check("slow static read is INCONCLUSIVE",
	      result.status == PROBE_INCONCLUSIVE);
}

static void test_frequency_estimates(void)
{
	struct probe_result result;

	result = run_wave(8000, 1000000, 0.2, 8000.0, 256, 0.05);
	check("8 kHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("8 kHz estimate", result.frequency_hz, 8000.0, 80.0);
	check("8 kHz sample rate is reported",
	      result.sample_rate_hz > 990000.0 &&
	      result.sample_rate_hz < 1010000.0);

	result = run_wave(1024000, 10000000, 0.1, 1024000.0, 256, 0.05);
	check("1.024 MHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("1.024 MHz estimate", result.frequency_hz, 1024000.0,
		   20000.0);

	result = run_wave(1025000, 10000000, 0.1, 1024000.0, 256, 0.05);
	check("1.025 MHz is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("1.025 MHz estimate", result.frequency_hz, 1025000.0,
		   20000.0);
}

static void test_oversampling(void)
{
	struct probe_result result;

	result = run_wave(8000, 32000, 0.2, 8000.0, 32, 0.05);
	check("8 kHz at 4x is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("8 kHz at 4x estimate", result.frequency_hz, 8000.0, 80.0);

	result = run_wave(8000, 64000, 0.2, 8000.0, 64, 0.05);
	check("8 kHz at 8x is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("8 kHz at 8x estimate", result.frequency_hz, 8000.0, 80.0);

	result = run_wave(8000, 128000, 0.2, 8000.0, 128, 0.05);
	check("8 kHz at 16x is FREQUENCY_ESTIMATED",
	      result.status == PROBE_FREQUENCY_ESTIMATED);
	check_near("8 kHz at 16x estimate", result.frequency_hz, 8000.0, 80.0);
}

static void test_undersampling_and_aliasing(void)
{
	struct probe_result result;

	result = run_wave(1024000, 2000000, 0.2, 1024000.0, 256, 0.05);
	check("undersampled BCLK is DETECTED, not estimated",
	      result.status == PROBE_DETECTED);
	check("undersampled BCLK still has edges", result.edges > 0);
	check("undersampled BCLK is not timing-suspicious by itself",
	      result.timing_suspect == 0);

	result = run_wave(1024000, 3000000, 0.2, 1024000.0, 256, 0.05);
	check("aliased BCLK is not a confident estimate",
	      result.status != PROBE_FREQUENCY_ESTIMATED);
}

static void test_gaps_and_instability(void)
{
	struct probe_counter counter;
	struct probe_result result;
	uint64_t end_ns;

	/* A 50 ms scheduler gap after 100 ms of a clean 8 kHz signal. */
	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	end_ns = feed_wave(&counter, 8000, 1000000, 0.1, 256, 0);
	probe_counter_checkpoint(&counter, end_ns + 50000000ULL);
	result = probe_finalize(&counter, 0.15, 8000.0, 0.05, 4.0);
	check("scheduler gap is INCONCLUSIVE",
	      result.status == PROBE_INCONCLUSIVE);
	check("scheduler gap is timing-suspect",
	      result.timing_suspect == 1);
	check("scheduler gap records max gap",
	      result.max_gap_ns >= 50000000ULL);
	check("scheduler gap records a gap event", result.gap_count >= 1);

	/* High average rate, but one large local gap. */
	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	end_ns = feed_wave(&counter, 8000, 1000000, 0.09, 256, 0);
	probe_counter_checkpoint(&counter, end_ns + 50000000ULL);
	end_ns = feed_wave(&counter, 8000, 1000000, 0.01, 256,
			   end_ns + 50000000ULL);
	result = probe_finalize(&counter, 0.15, 8000.0, 0.05, 4.0);
	check("high average with local gap is INCONCLUSIVE",
	      result.status == PROBE_INCONCLUSIVE);
	check("high average with local gap is timing-suspect",
	      result.timing_suspect == 1);

	/* A clean 8 kHz signal changing to 4 kHz halfway through. */
	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	end_ns = feed_wave(&counter, 8000, 1000000, 0.1, 256, 0);
	end_ns = feed_wave(&counter, 4000, 1000000, 0.1, 256, end_ns);
	result = probe_finalize(&counter, 0.2, 8000.0, 0.05, 4.0);
	check("frequency change is INCONCLUSIVE",
	      result.status == PROBE_INCONCLUSIVE);
	check("frequency change is timing-suspect",
	      result.timing_suspect == 1);

	/* Isolated short pulses are transitions, but not a TDM clock. */
	probe_counter_reset(&counter);
	probe_counter_start(&counter, 0);
	{
		uint64_t i;
		for (i = 0; i < 200000; i++) {
			probe_counter_sample(&counter,
					     (i % 1000 == 0) ? 1u : 0u);
			if ((i + 1) % 256 == 0)
				probe_counter_checkpoint(&counter,
							 ((i + 1) * 1000ULL));
		}
	}
	result = probe_finalize(&counter, 0.2, 8000.0, 0.05, 4.0);
	check("short pulses are not a confident TDM clock",
	      result.status != PROBE_FREQUENCY_ESTIMATED);
}

static void test_noise_and_short_window(void)
{
	struct probe_result result;

	/* Alternating samples look like 500 kHz, far from the 8 kHz target. */
	result = run_wave(500000, 1000000, 0.1, 8000.0, 256, 0.05);
	check("noise-like toggling is DETECTED",
	      result.status == PROBE_DETECTED);
	check("noise-like toggling is outside the plausible range",
	      result.frequency_hz > 400000.0);

	result = run_wave(8000, 1000000, 0.01, 8000.0, 64, 0.05);
	check("short 8 kHz observation is DETECTED, not estimated",
	      result.status == PROBE_DETECTED);
}

static void test_invalid(void)
{
	struct probe_counter counter;
	struct probe_result result;

	probe_counter_reset(&counter);
	result = probe_finalize(&counter, 0.0, 8000.0, 0.05, 4.0);
	check("zero elapsed is ERROR", result.status == PROBE_ERROR);

	probe_counter_start(&counter, 0);
	probe_counter_sample(&counter, 0);
	probe_counter_sample(&counter, 1);
	probe_counter_checkpoint(&counter, 1000000);
	result = probe_finalize(&counter, 0.001, 0.0, 0.05, 4.0);
	check("zero expected frequency is ERROR", result.status == PROBE_ERROR);

	probe_counter_reset(&counter);
	probe_counter_sample(&counter, 0);
	result = probe_finalize(&counter, 0.1, 8000.0, 0.05, 4.0);
	check("fewer than two samples is ERROR", result.status == PROBE_ERROR);

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
}

int main(void)
{
	test_reset_and_timing();
	test_static();
	test_frequency_estimates();
	test_oversampling();
	test_undersampling_and_aliasing();
	test_gaps_and_instability();
	test_noise_and_short_window();
	test_invalid();

	printf("\n%d failure(s)\n", failures);
	return failures ? 1 : 0;
}
