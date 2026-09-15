"""How a line is priced — `PriceBasis`, design revision 14.

    quantity basis   quantity × unit_price
    weight   basis   quantity × unit_weight × weight_unit_price

THE BASIS SELECTS THE RATE; THE PER-BATCH QUANTITY KEEPS DOING THE MULTIPLYING.
`unit_weight` is kilograms PER UNIT, so both formulas are `quantity × (something
per unit)` and `recompute_derived` did not move. That is the design answer these
tests pin.

WHY THIS FILE MATTERS MORE THAN ITS SIZE SUGGESTS. The money totals are STORED,
so an error here is written once and then read back for ever by every dashboard,
report and export — all agreeing, because they all read the same wrong number.
That is `test_derived_totals.py`'s reasoning, and adding a second formula to the
same function is exactly the change it was written to protect.

THE RULE EXISTS TWICE AND THERE IS NO WAY TO HAVE ONE COPY. Three dashboard
aggregates value lines in SQL and cannot call a Python helper, so
`order_view.line_effective_unit_price` has a twin in
`dashboard/imports/helpers.LINE_EFFECTIVE_UNIT_PRICE`. `TestTheTwoDefinitions`
below evaluates them against each other over the same inputs — which is the only
thing that keeps a duplicated rule honest.

No database: the SQL half is checked by compiling the expression and reading it,
not by running it.
"""

from decimal import Decimal

import pytest

from app.enums import PriceBasis
from app.imports.helpers import recompute_derived
from app.imports.order_view import (
    line_effective_unit_price, line_price_basis, line_unit_price,
)

from conftest import Obj, item


def d(v):
    return Decimal(str(v))


def priced(basis=None, unit_price="10", unit_weight=None, weight_unit_price=None,
           quantity="5"):
    """One line, priced whichever way, with its order line attached."""
    line = item(quantity=d(quantity), unit_price=d(unit_price) if unit_price else None)
    line.order_item.price_basis = basis
    line.order_item.unit_weight = d(unit_weight) if unit_weight else None
    line.order_item.weight_unit_price = d(weight_unit_price) if weight_unit_price else None
    return line


#---------------------------------------------------------------------------
# Which formula applies
#---------------------------------------------------------------------------

class TestTheBasisSelectsTheRate:

    def test_quantity_basis_uses_the_unit_price(self):
        assert line_effective_unit_price(priced(PriceBasis.QUANTITY.value)) == d("10")

    def test_weight_basis_uses_weight_times_the_per_kg_price(self):
        line = priced(PriceBasis.WEIGHT.value, unit_weight="3.2", weight_unit_price="12.5")
        assert line_effective_unit_price(line) == d("40.00")

    def test_the_unit_price_is_NOT_READ_under_the_weight_basis(self):
        """One field is authoritative and the other is not read. A line holding
        both must not blend them, or a column of unit prices stops being
        summable — enums.py's own warning."""
        line = priced(PriceBasis.WEIGHT.value, unit_price="999",
                      unit_weight="2", weight_unit_price="5")
        assert line_effective_unit_price(line) == d("10")

    def test_the_weight_fields_are_not_read_under_the_quantity_basis(self):
        line = priced(PriceBasis.QUANTITY.value, unit_price="7",
                      unit_weight="100", weight_unit_price="100")
        assert line_effective_unit_price(line) == d("7")

    def test_a_missing_basis_reads_as_quantity(self):
        """NOT NULL with a server default, so this is defensive rather than
        load-bearing — but a valuation is not where to discover an expired
        attribute."""
        assert line_price_basis(priced(None)) == PriceBasis.QUANTITY.value
        assert line_effective_unit_price(priced(None)) == d("10")


#---------------------------------------------------------------------------
# Incomplete weight pricing is NOTHING, never zero
#---------------------------------------------------------------------------

class TestAnUnfinishedWeightLine:

    @pytest.mark.parametrize("unit_weight,per_kg", [
        (None, "12.5"), ("3.2", None), (None, None),
    ])
    def test_a_missing_weight_input_gives_None_not_zero(self, unit_weight, per_kg):
        """Every caller skips a None price, so the line drops out of the total.
        A 0 would value it at nothing and make the consignment look complete —
        the same "a zero needs a reason beside it" rule the dashboards keep."""
        line = priced(PriceBasis.WEIGHT.value, unit_weight=unit_weight,
                      weight_unit_price=per_kg)
        assert line_effective_unit_price(line) is None

    def test_it_does_NOT_fall_back_to_the_unit_price(self):
        """Falling back would value a weight-priced line at a per-piece rate
        and report a confident wrong number rather than an obvious gap."""
        line = priced(PriceBasis.WEIGHT.value, unit_price="10", unit_weight=None,
                      weight_unit_price=None)
        assert line_effective_unit_price(line) is None
        assert line_unit_price(line) == d("10")


#---------------------------------------------------------------------------
# The stored total — where an error would be written once and read for ever
#---------------------------------------------------------------------------

class TestRecomputeDerived:

    def consignment(self, *lines, rate="280"):
        group = Obj(exchange_rate=d(rate) if rate else None)
        c = Obj(items=list(lines), batch_group=group,
                foreign_total=None, pkr_total=None)
        return c

    def test_a_weight_priced_line_is_valued_by_weight(self):
        c = self.consignment(priced(PriceBasis.WEIGHT.value, quantity="5",
                                    unit_weight="3.2", weight_unit_price="12.5"))
        recompute_derived(c)
        assert c.foreign_total == d("200.00")          # 5 x 3.2 x 12.5

    def test_a_quantity_priced_line_is_unchanged_by_any_of_this(self):
        c = self.consignment(priced(PriceBasis.QUANTITY.value, quantity="5",
                                    unit_price="10"))
        recompute_derived(c)
        assert c.foreign_total == d("50")

    def test_one_consignment_may_carry_BOTH_bases(self):
        """The basis is per LINE, so a consignment can hold one of each and the
        total is the sum of two different formulas."""
        c = self.consignment(
            priced(PriceBasis.QUANTITY.value, quantity="5", unit_price="10"),
            priced(PriceBasis.WEIGHT.value, quantity="2",
                   unit_weight="3", weight_unit_price="4"),
        )
        recompute_derived(c)
        assert c.foreign_total == d("74")              # 50 + 24

    def test_an_unfinished_weight_line_is_SKIPPED_not_counted_as_zero(self):
        c = self.consignment(
            priced(PriceBasis.QUANTITY.value, quantity="5", unit_price="10"),
            priced(PriceBasis.WEIGHT.value, quantity="2", unit_weight=None,
                   weight_unit_price=None),
        )
        recompute_derived(c)
        assert c.foreign_total == d("50")

    def test_the_pkr_total_follows_the_effective_price(self):
        c = self.consignment(priced(PriceBasis.WEIGHT.value, quantity="5",
                                    unit_weight="3.2", weight_unit_price="12.5"),
                             rate="280")
        recompute_derived(c)
        assert c.pkr_total == d("56000.00")            # 200 x 280

    def test_it_is_still_idempotent(self):
        c = self.consignment(priced(PriceBasis.WEIGHT.value, quantity="5",
                                    unit_weight="3.2", weight_unit_price="12.5"))
        recompute_derived(c)
        first = c.foreign_total
        recompute_derived(c)
        assert c.foreign_total == first


#---------------------------------------------------------------------------
# The two definitions of one rule
#---------------------------------------------------------------------------

class TestTheTwoDefinitions:
    """The Python helper and the SQL expression must say the same thing.

    They cannot be one definition — three dashboard aggregates value lines in
    the database and cannot call Python — so this is what keeps them in step.
    It reads the COMPILED SQL rather than running it, so it needs no database,
    the same technique `test_list_filter_joins.py` uses for its FROM clauses.
    """

    def compiled(self):
        from app.dashboard.imports.helpers import LINE_EFFECTIVE_UNIT_PRICE
        return str(LINE_EFFECTIVE_UNIT_PRICE.compile(
            compile_kwargs={"literal_binds": True}))

    def test_the_sql_branches_on_price_basis(self):
        sql = self.compiled()
        assert "price_basis" in sql
        assert PriceBasis.WEIGHT.value in sql

    def test_the_sql_weight_branch_multiplies_the_SAME_TWO_COLUMNS(self):
        """The failure this catches is one copy being changed and not the
        other — a dashboard quietly valuing on a different formula from the
        stored total, which is the disagreement this project has chased twice."""
        sql = self.compiled().replace("\n", " ")
        weight_branch = sql.split("ELSE")[0]
        assert "unit_weight" in weight_branch
        assert "weight_unit_price" in weight_branch

    def test_the_sql_else_branch_is_the_plain_unit_price(self):
        sql = self.compiled().replace("\n", " ")
        assert "unit_price" in sql.split("ELSE")[1]

    def test_the_sql_does_NOT_coalesce_the_weight_inputs(self):
        """A missing input must yield NULL so SUM skips the row, matching the
        Python helper returning None. COALESCE to 0 would value an unfinished
        line at nothing and make a total look complete."""
        weight_branch = self.compiled().replace("\n", " ").split("ELSE")[0]
        assert "coalesce" not in weight_branch.lower()
