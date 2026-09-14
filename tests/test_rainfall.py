"""
Test for rainfall.py's aggregation logic — proves the annual/seasonal math is correct,
using a realistic sample Open-Meteo-shaped response (since the live API is blocked
in this sandbox). Swap in a real fetch_historical_rainfall() call once you have
network access to test against the actual API.

Run: python3 tests/test_rainfall.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.rainfall import aggregate_rainfall, RainfallDataError


def make_sample_response():
    """
    Builds a fake but realistic 2-year daily precipitation dataset:
    - Monsoon months (Jun-Sep): heavy rain, ~8mm/day average
    - Non-monsoon months: light rain, ~1mm/day average
    This lets us predict the expected aggregated totals and check the math against them.
    """
    dates = []
    values = []
    for year in [2022, 2023]:
        for month in range(1, 13):
            days_in_month = 30  # simplified, doesn't need real calendar precision for this test
            for day in range(1, days_in_month + 1):
                dates.append(f"{year}-{month:02d}-{day:02d}")
                if month in (6, 7, 8, 9):
                    values.append(8.0)
                else:
                    values.append(1.0)
    return {"daily": {"time": dates, "precipitation_sum": values}}


def test_aggregation_math():
    raw = make_sample_response()
    result = aggregate_rainfall(raw)

    # Expected per year: monsoon = 4 months * 30 days * 8mm = 960mm
    #                     non-monsoon = 8 months * 30 days * 1mm = 240mm
    #                     annual total = 1200mm
    assert result.data_years == 2, f"Expected 2 years, got {result.data_years}"
    assert abs(result.seasonal["monsoon_mm"] - 960.0) < 1, f"Monsoon total off: {result.seasonal['monsoon_mm']}"
    assert abs(result.seasonal["non_monsoon_mm"] - 240.0) < 1, f"Non-monsoon total off: {result.seasonal['non_monsoon_mm']}"
    assert abs(result.annual_avg_mm - 1200.0) < 1, f"Annual avg off: {result.annual_avg_mm}"

    print(f"✓ Annual average: {result.annual_avg_mm} mm")
    print(f"✓ Monsoon: {result.seasonal['monsoon_mm']} mm, Non-monsoon: {result.seasonal['non_monsoon_mm']} mm")
    print(f"✓ Years of data: {result.data_years}")


def test_handles_null_values():
    """Open-Meteo can return null for missing days — make sure we don't crash on that."""
    raw = {"daily": {"time": ["2023-06-01", "2023-06-02"], "precipitation_sum": [5.0, None]}}
    result = aggregate_rainfall(raw)
    assert result.seasonal["monsoon_mm"] == 5.0
    print("✓ Handles null precipitation values without crashing")


def test_malformed_response_raises():
    """Empty/malformed API response should raise, not silently return garbage."""
    try:
        aggregate_rainfall({"daily": {"time": [], "precipitation_sum": []}})
        assert False, "Should have raised RainfallDataError"
    except RainfallDataError:
        print("✓ Malformed response correctly raises RainfallDataError")


if __name__ == "__main__":
    test_aggregation_math()
    test_handles_null_values()
    test_malformed_response_raises()
    print("\nALL CHECKS PASSED — rainfall aggregation logic works.")
