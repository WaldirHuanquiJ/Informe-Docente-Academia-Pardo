from app.services.attendance_engine import (
    AnalysisPolicy,
    extra_block_metrics,
    normalized_event_minutes,
)


def test_normalized_event_minutes_collapses_duplicates():
    text = "07:58\n08:01\n10:55\n11:00"
    out = normalized_event_minutes(text, duplicate_window_minutes=5)
    assert out == [478, 660]


def test_extra_block_metrics_rounds_expected_window():
    seconds, tardy = extra_block_metrics(
        "13:40\n16:10",
        duplicate_window_minutes=20,
        extra_early_rounding_minutes=30,
        extra_block_minutes=120,
    )
    assert seconds == (16 * 60 - 14 * 60) * 60
    assert tardy == 0


def test_policy_seconds_conversion():
    policy = AnalysisPolicy(min_valid_attendance_minutes=45)
    assert policy.min_valid_attendance_seconds == 2700
