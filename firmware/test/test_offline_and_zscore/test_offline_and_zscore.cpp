#include <unity.h>
#include <string.h>
#include "offline_buffer.h"
#include "zscore_detector.h"

static OfflineBuffer buffer;
static ZScoreBaseline baseline;

void setUp(void) {
    offline_buffer_init(&buffer);
    zscore_init(&baseline);
}

void tearDown(void) {
}

// 1. Offline Buffer FIFO Order
void test_offline_buffer_push_pop_fifo(void) {
    BufferedTelemetryItem item1;
    memset(&item1, 0, sizeof(item1));
    item1.channel = 1;
    item1.voltage_v = 230.1f;
    item1.timestamp_s = 1001;

    BufferedTelemetryItem item2;
    memset(&item2, 0, sizeof(item2));
    item2.channel = 2;
    item2.voltage_v = 231.5f;
    item2.timestamp_s = 1002;

    TEST_ASSERT_TRUE(offline_buffer_push(&buffer, &item1));
    TEST_ASSERT_TRUE(offline_buffer_push(&buffer, &item2));
    TEST_ASSERT_EQUAL_UINT16(2, offline_buffer_count(&buffer));

    BufferedTelemetryItem out;
    TEST_ASSERT_TRUE(offline_buffer_pop(&buffer, &out));
    TEST_ASSERT_EQUAL_UINT8(1, out.channel);
    TEST_ASSERT_EQUAL_UINT32(1001, out.timestamp_s);

    TEST_ASSERT_TRUE(offline_buffer_pop(&buffer, &out));
    TEST_ASSERT_EQUAL_UINT8(2, out.channel);
    TEST_ASSERT_EQUAL_UINT32(1002, out.timestamp_s);

    TEST_ASSERT_TRUE(offline_buffer_is_empty(&buffer));
}

// 2. Offline Buffer Overflow: Overwrites oldest and increments dropped count
void test_offline_buffer_overflow_drop_tracking(void) {
    BufferedTelemetryItem item;
    memset(&item, 0, sizeof(item));

    for (int i = 0; i < OFFLINE_BUFFER_CAPACITY + 10; i++) {
        item.timestamp_s = i;
        offline_buffer_push(&buffer, &item);
    }

    TEST_ASSERT_EQUAL_UINT16(OFFLINE_BUFFER_CAPACITY, offline_buffer_count(&buffer));
    TEST_ASSERT_EQUAL_UINT32(10, offline_buffer_dropped_total(&buffer));

    // Oldest item should now be timestamp 10
    BufferedTelemetryItem out;
    offline_buffer_pop(&buffer, &out);
    TEST_ASSERT_EQUAL_UINT32(10, out.timestamp_s);
}

// 3. Z-Score Noise Floor: Tiny fluctuations do not trigger anomaly
void test_zscore_noise_floors_prevent_false_alarms(void) {
    // Learned baseline with perfectly zero variance on steady load
    zscore_set_baseline(&baseline, 230.0f, 0.0f, 0.82f, 0.0f, 125.0f, 0.0f, 0.65f, 0.0f);

    // Live reading with minor noise: voltage 231V (+1V), current 0.83A (+0.01A)
    ZScoreResult res = zscore_evaluate(&baseline, 231.0f, 0.83f, 126.0f, 0.65f);

    // Z-scores protected by noise floors:
    // zv = 1.0 / 2.0 = 0.5
    // zi = 0.01 / 0.05 = 0.2
    // zp = 1.0 / 5.0 = 0.2
    TEST_ASSERT_FALSE(res.is_anomaly);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.5f, res.zv);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.2f, res.zi);
}

// 4. Z-Score Deviation: Significant electrical anomaly triggers warning
void test_zscore_detects_significant_deviation(void) {
    zscore_set_baseline(&baseline, 230.0f, 1.5f, 0.82f, 0.04f, 125.0f, 4.0f, 0.65f, 0.02f);

    // Huge power jump to 200W (delta = 75W, std = 5.0W floor -> Z ~ 15.0)
    ZScoreResult res = zscore_evaluate(&baseline, 230.0f, 1.2f, 200.0f, 0.65f);

    TEST_ASSERT_TRUE(res.is_anomaly);
    TEST_ASSERT_TRUE(res.zp >= ZSCORE_WARNING_THRESHOLD);
}

int main(int argc, char **argv) {
    UNITY_BEGIN();
    RUN_TEST(test_offline_buffer_push_pop_fifo);
    RUN_TEST(test_offline_buffer_overflow_drop_tracking);
    RUN_TEST(test_zscore_noise_floors_prevent_false_alarms);
    RUN_TEST(test_zscore_detects_significant_deviation);
    return UNITY_END();
}

