#include "zscore_detector.h"
#include <math.h>

void zscore_init(ZScoreBaseline* baseline) {
    if (!baseline) return;
    baseline->v_mean = 230.0f;
    baseline->v_std = ZSCORE_VOLTAGE_STD_FLOOR;
    baseline->i_mean = 0.0f;
    baseline->i_std = ZSCORE_CURRENT_STD_FLOOR;
    baseline->p_mean = 0.0f;
    baseline->p_std = ZSCORE_POWER_STD_FLOOR;
    baseline->pf_mean = 1.0f;
    baseline->pf_std = ZSCORE_PF_STD_FLOOR;
    baseline->baseline_ready = false;
}

void zscore_set_baseline(
    ZScoreBaseline* baseline,
    float v_mean, float v_std,
    float i_mean, float i_std,
    float p_mean, float p_std,
    float pf_mean, float pf_std
) {
    if (!baseline) return;
    baseline->v_mean = v_mean;
    baseline->v_std = (v_std > ZSCORE_VOLTAGE_STD_FLOOR) ? v_std : ZSCORE_VOLTAGE_STD_FLOOR;
    baseline->i_mean = i_mean;
    baseline->i_std = (i_std > ZSCORE_CURRENT_STD_FLOOR) ? i_std : ZSCORE_CURRENT_STD_FLOOR;
    baseline->p_mean = p_mean;
    baseline->p_std = (p_std > ZSCORE_POWER_STD_FLOOR) ? p_std : ZSCORE_POWER_STD_FLOOR;
    baseline->pf_mean = pf_mean;
    baseline->pf_std = (pf_std > ZSCORE_PF_STD_FLOOR) ? pf_std : ZSCORE_PF_STD_FLOOR;
    baseline->baseline_ready = true;
}

ZScoreResult zscore_evaluate(
    const ZScoreBaseline* baseline,
    float voltage_v,
    float current_a,
    float active_power_w,
    float power_factor
) {
    ZScoreResult res;
    res.is_anomaly = false;
    res.max_z = 0.0f;
    res.zv = 0.0f;
    res.zi = 0.0f;
    res.zp = 0.0f;
    res.zpf = 0.0f;

    if (!baseline || !baseline->baseline_ready) {
        return res;
    }

    float v_sigma = (baseline->v_std > ZSCORE_VOLTAGE_STD_FLOOR) ? baseline->v_std : ZSCORE_VOLTAGE_STD_FLOOR;
    float i_sigma = (baseline->i_std > ZSCORE_CURRENT_STD_FLOOR) ? baseline->i_std : ZSCORE_CURRENT_STD_FLOOR;
    float p_sigma = (baseline->p_std > ZSCORE_POWER_STD_FLOOR) ? baseline->p_std : ZSCORE_POWER_STD_FLOOR;
    float pf_sigma = (baseline->pf_std > ZSCORE_PF_STD_FLOOR) ? baseline->pf_std : ZSCORE_PF_STD_FLOOR;

    res.zv = fabsf(voltage_v - baseline->v_mean) / v_sigma;
    res.zi = fabsf(current_a - baseline->i_mean) / i_sigma;
    res.zp = fabsf(active_power_w - baseline->p_mean) / p_sigma;
    res.zpf = fabsf(power_factor - baseline->pf_mean) / pf_sigma;

    float max_z = res.zv;
    if (res.zi > max_z) max_z = res.zi;
    if (res.zp > max_z) max_z = res.zp;
    if (res.zpf > max_z) max_z = res.zpf;

    res.max_z = max_z;
    res.is_anomaly = (max_z >= ZSCORE_WARNING_THRESHOLD);

    return res;
}

