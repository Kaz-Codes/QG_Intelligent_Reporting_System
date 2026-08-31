"""packing_cost_kpis — quoted vs actual packing cost, and the savings between.

THE RULE THIS PINS: a missing cost is not a zero cost.

No package in the loaded data carries an actual_packing_cost and only a
handful carry a quoted one. A rollup that treated NULL as 0 would report a
confident "Rs 0 spent" and "Rs X saved" from a column that is entirely empty —
a number that looks like a finding and is an artefact. So each figure reports
the count it was measured over, and savings stay None until BOTH sides of the
subtraction exist ON THE SAME PACKAGE.

The partial case is the one that matters and it is tested hardest below:
summing a well-populated quoted column against a sparse actual one and
subtracting would invent a saving out of the difference in coverage.
"""

from decimal import Decimal

from conftest import package

from app.dashboard.logistics.calculations import packing_cost_kpis


def d(value):
    return Decimal(str(value))


class TestFullyCosted:
    def test_totals_and_savings_when_every_package_has_both(self):
        result = packing_cost_kpis([
            package(gross_weight=d(100), quoted_packing_cost=d(500), actual_packing_cost=d(400)),
            package(gross_weight=d(50), quoted_packing_cost=d(300), actual_packing_cost=d(250)),
        ])
        assert result["total_quoted_cost"] == d(800)   # 500 + 300
        assert result["total_actual_cost"] == d(650)   # 400 + 250
        assert result["total_savings"] == d(150)       # (500-400) + (300-250)
        assert result["savings_basis"] == 2

    def test_saving_per_kg_divides_by_the_COMPARABLE_weight_only(self):
        result = packing_cost_kpis([
            package(gross_weight=d(100), quoted_packing_cost=d(500), actual_packing_cost=d(400)),
        ])
        assert result["avg_saving_per_kg"] == d(1)

    def test_an_overspend_is_a_negative_saving_not_a_floor_at_zero(self):
        result = packing_cost_kpis([
            package(gross_weight=d(10), quoted_packing_cost=d(100), actual_packing_cost=d(150)),
        ])
        assert result["total_savings"] == d(-50)


class TestNullIsNotZero:
    """The core of it."""

    def test_no_costs_at_all_leaves_savings_NONE(self):
        result = packing_cost_kpis([
            package(gross_weight=d(100)),
            package(gross_weight=d(50)),
        ])
        assert result["total_savings"] is None
        assert result["avg_saving_per_kg"] is None
        assert result["savings_basis"] == 0

    def test_no_costs_reports_ZERO_COVERAGE_not_a_zero_measurement(self):
        # The totals being 0 is fine only because the counts say 0 packages
        # were measured. Without those counts, "Rs 0 quoted" is a lie.
        result = packing_cost_kpis([package(gross_weight=d(100))])
        assert result["packages_with_quoted_cost"] == 0
        assert result["packages_with_actual_cost"] == 0
        assert result["total_packages"] == 1

    def test_quoted_present_actual_missing_yields_NO_saving(self):
        # THE TRAP. quoted 500, actual absent — subtracting would report a
        # Rs 500 saving on a package nobody has costed yet.
        result = packing_cost_kpis([
            package(gross_weight=d(100), quoted_packing_cost=d(500)),
        ])
        assert result["total_quoted_cost"] == d(500)
        assert result["total_actual_cost"] == d(0)
        assert result["packages_with_actual_cost"] == 0
        assert result["total_savings"] is None

    def test_actual_present_quoted_missing_yields_NO_saving(self):
        result = packing_cost_kpis([
            package(gross_weight=d(100), actual_packing_cost=d(400)),
        ])
        assert result["total_savings"] is None

    def test_a_cost_of_zero_is_a_measurement_and_IS_counted(self):
        # 0 and None are different: somebody costed this at nothing.
        result = packing_cost_kpis([
            package(gross_weight=d(10), quoted_packing_cost=d(0), actual_packing_cost=d(0)),
        ])
        assert result["packages_with_quoted_cost"] == 1
        assert result["packages_with_actual_cost"] == 1
        assert result["total_savings"] == d(0)
        assert result["savings_basis"] == 1


class TestPartialCoverage:
    """Some packages costed, some not — the real shape of the data."""

    def test_savings_are_measured_only_over_packages_with_BOTH(self):
        result = packing_cost_kpis([
            # comparable: saves 100
            package(gross_weight=d(100), quoted_packing_cost=d(500), actual_packing_cost=d(400)),
            # quoted only — must not contribute a phantom 300 saving
            package(gross_weight=d(80), quoted_packing_cost=d(300)),
            # actual only
            package(gross_weight=d(60), actual_packing_cost=d(200)),
            # neither
            package(gross_weight=d(40)),
        ])
        assert result["total_savings"] == d(100)
        assert result["savings_basis"] == 1

    def test_the_column_totals_still_report_everything_they_saw(self):
        # The totals are honest sums of what exists; the BASIS is what stops
        # them being read as complete.
        result = packing_cost_kpis([
            package(gross_weight=d(100), quoted_packing_cost=d(500), actual_packing_cost=d(400)),
            package(gross_weight=d(80), quoted_packing_cost=d(300)),
            package(gross_weight=d(60), actual_packing_cost=d(200)),
        ])
        assert result["total_quoted_cost"] == d(800)
        assert result["packages_with_quoted_cost"] == 2
        assert result["total_actual_cost"] == d(600)
        assert result["packages_with_actual_cost"] == 2
        assert result["total_packages"] == 3

    def test_saving_per_kg_ignores_the_weight_of_uncomparable_packages(self):
        # Dividing a 100 saving by all 180kg would understate it by nearly
        # half; only the 100kg that produced the saving belongs on the bottom.
        result = packing_cost_kpis([
            package(gross_weight=d(100), quoted_packing_cost=d(500), actual_packing_cost=d(400)),
            package(gross_weight=d(80), quoted_packing_cost=d(300)),
        ])
        assert result["avg_saving_per_kg"] == d(1)

    def test_a_comparable_package_with_no_weight_gives_a_saving_but_no_rate(self):
        result = packing_cost_kpis([
            package(gross_weight=None, quoted_packing_cost=d(500), actual_packing_cost=d(400)),
        ])
        assert result["total_savings"] == d(100)
        assert result["avg_saving_per_kg"] is None


class TestWeight:
    def test_weight_reports_its_own_coverage(self):
        result = packing_cost_kpis([
            package(gross_weight=d(100)),
            package(gross_weight=None),
        ])
        assert result["total_weight_kg"] == d(100)
        assert result["packages_with_weight"] == 1
        assert result["total_packages"] == 2


class TestEmptyInput:
    def test_no_packages_at_all(self):
        result = packing_cost_kpis([])
        assert result["total_packages"] == 0
        assert result["total_weight_kg"] == d(0)
        assert result["total_savings"] is None
        assert result["avg_saving_per_kg"] is None
        assert result["savings_basis"] == 0
