#ifndef ZSCORE_DETECTOR_H
#define ZSCORE_DETECTOR_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Practical noise floors from docs & specification
#define ZSCORE_VOLTAGE_STD_FLOOR 2.0f
#define ZSCORE_CURRENT_STD_FLOOR 0.05f
#define ZSCORE_POWER_STD_FLOOR 5.0f
#define ZSCORE_PF_STD_FLOOR 0.03f

#define ZSCORE_WARNING_THRESHOLD 2.5f

typedef struct {
    float v_mean;
    float v_std;
    float i_mean;
    float i_std;
    float p_mean;
    float p_std;
    float pf_mean;
    float pf_std;
    bool baseline_ready;
} ZScoreBaseline;

typedef struct {
    bool is_anomaly;
    float max_z;
    float zv;
    float zi;
    float zp;
    float zpf;
} ZScoreResult;

/**
 * Initializes a Z-score baseline.
 */
void zscore_init(ZScoreBaseline* baseline);

/**
 * Updates or sets learned baseline statistics.
 */
void zscore_set_baseline(
    ZScoreBaseline* baseline,
    float v_mean, float v_std,
    float i_mean, float i_std,
    float p_mean, float p_std,
    float pf_mean, float pf_std
);

/**
 * Evaluates live sample against learned baseline using noise floors.
 * Note: Z-Score detector ONLY emits advisory warnings; it NEVER trips hardware!
 */
ZScoreResult zscore_evaluate(
    const ZScoreBaseline* baseline,
    float voltage_v,
    float current_a,
    float active_power_w,
    float power_factor
);

#ifdef __cplusplus
}
#endif

#endif // ZSCORE_DETECTOR_H

