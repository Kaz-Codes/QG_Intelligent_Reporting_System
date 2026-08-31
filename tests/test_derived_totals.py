"""recompute_derived — the stored money totals.

WHY THIS IS THE FIRST THING WORTH TESTING. These figures are STORED, not
recomputed on read (see the note on the function itself), precisely so that a
later rate change cannot restate a printed report. That is the right design
and it is also what makes an error here permanent: a wrong pkr_total is
written once and then read back for ever by the dashboards, the reports and
the Excel exports, all of which agree with each other because they are all
reading the same wrong number.

The tests assert on the VALUES the function leaves behind, never on how it
arrived at them.
"""

from decimal import Decimal

from conftest import consignment, item

from app.imports.helpers import recompute_derived


def d(value):
    return Decimal(str(value))


class TestForeignTotal:
    def test_sums_quantity_times_unit_price_across_lines(self):
        c = consignment(items=[
            item(quantity=d(10), unit_price=d("2.50")),
            item(quantity=d(3), unit_price=d("100.00")),
        ])
        recompute_derived(c)
        assert c.foreign_total == d("325.00")

    def test_single_item(self):
        c = consignment(items=[item(quantity=d(7), unit_price=d("1.25"))])
        recompute_derived(c)
        assert c.foreign_total == d("8.75")

    def test_many_items_accumulate_exactly(self):
        # 100 lines of 0.01 each. Decimal must land on exactly 1.00 — the same
        # sum in float is 0.9999999999999999, which is the entire reason the
        # money columns are Numeric and not Float.
        c = consignment(items=[
            item(quantity=d(1), unit_price=d("0.01")) for _ in range(100)
        ])
        recompute_derived(c)
        assert c.foreign_total == d("1.00")

    def test_zero_quantity_contributes_nothing_but_is_not_skipped(self):
        c = consignment(items=[
            item(quantity=d(0), unit_price=d("99.99")),
            item(quantity=d(2), unit_price=d("5.00")),
        ])
        recompute_derived(c)
        assert c.foreign_total == d("10.00")

    def test_line_missing_quantity_or_price_is_ignored_not_treated_as_zero(self):
        # A line that has not been priced yet must not silently count as 0 and
        # drag a total down; it simply does not contribute.
        c = consignment(items=[
            item(quantity=None, unit_price=d("50.00")),
            item(quantity=d(4), unit_price=None),
            item(quantity=d(2), unit_price=d("3.00")),
        ])
        recompute_derived(c)
        assert c.foreign_total == d("6.00")

    def test_no_items_at_all_totals_zero_not_none(self):
        c = consignment(items=[])
        recompute_derived(c)
        assert c.foreign_total == d("0")

    def test_deleted_lines_are_excluded(self):
        # Soft-deleted lines stay on the row for the audit trail, so a total
        # that counted them would keep charging for a line the user removed.
        c = consignment(items=[
            item(quantity=d(1), unit_price=d("10.00")),
            item(quantity=d(1), unit_price=d("999.00"), is_deleted=True),
        ])
        recompute_derived(c)
        assert c.foreign_total == d("10.00")


class TestPkrTotal:
    def test_multiplies_the_foreign_total_by_the_booked_rate(self):
        c = consignment(
            exchange_rate=d("280.5"),
            items=[item(quantity=d(2), unit_price=d("100.00"))],
        )
        recompute_derived(c)
        assert c.pkr_total == d("56100.0")

    def test_missing_exchange_rate_leaves_pkr_total_NONE_not_zero(self):
        # THE IMPORTANT ONE. Rs 0 is a claim that the consignment is worth
        # nothing; None is the truth, which is that nobody has booked a rate
        # yet. A zero here would be summed into every dashboard as real money.
        c = consignment(
            exchange_rate=None,
            items=[item(quantity=d(2), unit_price=d("100.00"))],
        )
        recompute_derived(c)
        assert c.foreign_total == d("200.00")
        assert c.pkr_total is None

    def test_rate_of_zero_is_honoured_rather_than_treated_as_missing(self):
        # 0 is a real (if odd) booked rate and is not the same as "unset" —
        # `if rate is not None` rather than `if rate` is what keeps them apart.
        c = consignment(
            exchange_rate=d(0),
            items=[item(quantity=d(2), unit_price=d("100.00"))],
        )
        recompute_derived(c)
        assert c.pkr_total == d("0")

    def test_rounding_at_the_boundary_is_not_lost(self):
        # 3 x 0.005 x 3 = 0.045. Nothing here rounds, so the stored value must
        # keep its full precision rather than being truncated to 2dp on the way
        # in — the column is Numeric(20,2) but that rounding is the database's
        # decision at write time, not this function's.
        c = consignment(
            exchange_rate=d(3),
            items=[item(quantity=d(3), unit_price=d("0.005"))],
        )
        recompute_derived(c)
        assert c.foreign_total == d("0.015")
        assert c.pkr_total == d("0.045")


class TestPerItemVariance:
    def test_variance_is_alc_minus_elc_with_a_percentage(self):
        line = item(quantity=d(1), unit_price=d(1), elc=d("100.00"), alc=d("125.00"))
        recompute_derived(consignment(items=[line]))
        assert line.variance_absolute == d("25.00")
        assert line.variance_percentage == d("25")

    def test_a_negative_variance_is_kept_negative(self):
        line = item(quantity=d(1), unit_price=d(1), elc=d("100.00"), alc=d("80.00"))
        recompute_derived(consignment(items=[line]))
        assert line.variance_absolute == d("-20.00")
        assert line.variance_percentage == d("-20")

    def test_only_one_of_elc_alc_present_clears_the_variance(self):
        # ELC and ALC are entered WEEKS apart (rule 11). Until both exist there
        # is no variance, and a stale one from an earlier save must be cleared
        # rather than left standing beside a changed figure.
        line = item(
            quantity=d(1), unit_price=d(1), elc=d("100.00"), alc=None,
            variance_absolute=d("999"), variance_percentage=d("999"),
        )
        recompute_derived(consignment(items=[line]))
        assert line.variance_absolute is None
        assert line.variance_percentage is None

    def test_zero_elc_gives_an_absolute_variance_but_no_percentage(self):
        # Percentage of zero is undefined, not infinite and not 0.
        line = item(quantity=d(1), unit_price=d(1), elc=d(0), alc=d("40.00"))
        recompute_derived(consignment(items=[line]))
        assert line.variance_absolute == d("40.00")
        assert line.variance_percentage is None

    def test_deleted_lines_keep_whatever_they_had(self):
        # The function only walks active lines, so a removed line is left
        # exactly as it was rather than being recomputed against nothing.
        removed = item(
            is_deleted=True, elc=d("10"), alc=d("12"),
            variance_absolute=d("2"), variance_percentage=d("20"),
        )
        recompute_derived(consignment(items=[removed]))
        assert removed.variance_absolute == d("2")


class TestRecomputeIsIdempotent:
    def test_running_twice_gives_the_same_answer(self):
        # It runs on create, on update AND on revert, so a second pass over an
        # already-computed consignment must not double anything.
        c = consignment(
            exchange_rate=d("280"),
            items=[item(quantity=d(2), unit_price=d("50.00"), elc=d("10"), alc=d("11"))],
        )
        recompute_derived(c)
        first_foreign, first_pkr = c.foreign_total, c.pkr_total
        first_variance = c.items[0].variance_absolute

        recompute_derived(c)
        assert c.foreign_total == first_foreign
        assert c.pkr_total == first_pkr
        assert c.items[0].variance_absolute == first_variance
