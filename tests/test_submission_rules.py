"""submission_errors — the rule set that gates submission.

This function decides whether work can move forward, so it fails in two
directions and both are expensive. Too strict and it blocks a legitimate
consignment with no way round it; too loose and an incomplete record is
submitted, locked at "Arrived at Works" and thereafter editable by nobody but
an admin.

It is also mirrored on the front end twice over — the zod submit schema and
the wizard's outstanding-requirements banner — so a change here silently
disagrees with two other places. These tests pin the BEHAVIOUR that all three
are supposed to share.
"""

from decimal import Decimal

from conftest import consignment, item

from app.imports.helpers import submission_errors


def d(value):
    return Decimal(str(value))


def complete_item(**overrides):
    base = dict(quantity=d(5), unit_price=d("10.00"))
    base.update(overrides)
    return item(**base)


def complete(**overrides):
    base = dict(exchange_rate=d("280"), items=[complete_item()])
    base.update(overrides)
    return consignment(**base)


class TestAcceptance:
    def test_a_complete_consignment_produces_no_errors(self):
        assert submission_errors(complete()) == []

    def test_still_accepted_with_several_lines(self):
        c = complete(items=[complete_item(), complete_item(), complete_item()])
        assert submission_errors(c) == []


class TestHeaderFields:
    """Each field, on its own, so a failure names one cause rather than a set."""

    def test_branch_required(self):
        assert "Branch is required" in submission_errors(complete(branch_id=None))

    def test_supplier_required(self):
        assert "Supplier is required" in submission_errors(complete(supplier_id=None))

    def test_origin_required(self):
        assert "Country of origin is required" in submission_errors(complete(origin=None))

    def test_currency_required(self):
        assert "Currency is required" in submission_errors(complete(currency=None))

    def test_payment_instrument_required(self):
        errors = submission_errors(complete(payment_instrument=None))
        assert "Payment instrument is required" in errors

    def test_instrument_number_required(self):
        errors = submission_errors(complete(instrument_number=None))
        assert "Instrument number is required" in errors

    def test_works_required(self):
        assert "Works is required" in submission_errors(complete(works=None))

    def test_exchange_rate_required(self):
        assert "Exchange rate is required" in submission_errors(complete(exchange_rate=None))

    def test_rate_booked_date_required(self):
        errors = submission_errors(complete(rate_booked_on=None))
        assert "The date the rate was booked is required" in errors

    def test_status_required(self):
        assert "Status is required" in submission_errors(complete(current_status=None))

    def test_an_exchange_rate_of_zero_is_present_not_missing(self):
        # `is None`, not falsy — 0 is a booked rate, however strange.
        assert submission_errors(complete(exchange_rate=d(0))) == []

    def test_each_missing_field_contributes_exactly_one_error(self):
        # The wizard lists these one per line, so a field producing two entries
        # would show the user the same problem twice.
        errors = submission_errors(complete(branch_id=None))
        assert errors.count("Branch is required") == 1

    def test_several_gaps_are_all_reported_not_just_the_first(self):
        # Submit is opt-in and returns the whole list; stopping at the first
        # gap would make completing a draft a guessing game.
        errors = submission_errors(complete(branch_id=None, supplier_id=None, works=None))
        assert "Branch is required" in errors
        assert "Supplier is required" in errors
        assert "Works is required" in errors


class TestItems:
    def test_at_least_one_item_required(self):
        assert "Add at least one item" in submission_errors(complete(items=[]))

    def test_a_consignment_of_only_deleted_lines_counts_as_empty(self):
        c = complete(items=[complete_item(is_deleted=True)])
        assert "Add at least one item" in submission_errors(c)

    def test_item_name_required(self):
        errors = submission_errors(complete(items=[complete_item(item_name=None)]))
        assert "Item 1: item name is required" in errors

    def test_quantity_required(self):
        errors = submission_errors(complete(items=[complete_item(quantity=None)]))
        assert "Item 1: quantity is required" in errors

    def test_quantity_of_zero_is_present_not_missing(self):
        assert submission_errors(complete(items=[complete_item(quantity=d(0))])) == []

    def test_unit_of_measure_required(self):
        errors = submission_errors(complete(items=[complete_item(unit_of_measurement=None)]))
        assert "Item 1: unit of measure is required" in errors

    def test_requisition_type_required(self):
        errors = submission_errors(complete(items=[complete_item(requisition_type=None)]))
        assert "Item 1: requisition type is required" in errors

    def test_errors_are_numbered_by_ACTIVE_line_position(self):
        # A deleted line must not consume a number, or the message points at
        # the wrong row on screen.
        c = complete(items=[
            complete_item(is_deleted=True),
            complete_item(item_name=None),
        ])
        errors = submission_errors(c)
        assert "Item 1: item name is required" in errors
        assert "Item 2: item name is required" not in errors


class TestItemCodeByRequisitionType:
    """The Round 1 change: 'Others' lines are exempt from the item-code rule.

    'Others' items are not drawn from the item master, so there is frequently
    no code to give. Store and Engineering lines still require one, because
    those ARE master items and a missing code breaks item-wise reporting.

    The backend keys this off the Title Case value ('Others'); the frontend
    draft holds the lowercase one. Both sides were changed together and these
    tests pin the backend half.
    """

    def test_others_does_NOT_require_an_item_code(self):
        c = complete(items=[complete_item(
            requisition_type="Others", item_code=None, description="Spare gasket",
        )])
        assert submission_errors(c) == []

    def test_store_still_requires_an_item_code(self):
        c = complete(items=[complete_item(requisition_type="Store", item_code=None)])
        assert "Item 1: item code is required" in submission_errors(c)

    def test_engineering_still_requires_an_item_code(self):
        c = complete(items=[complete_item(
            requisition_type="Engineering", item_code=None,
            reference_number="R", job_number="J", mo_number="M",
        )])
        assert "Item 1: item code is required" in submission_errors(c)

    def test_an_others_line_with_a_code_is_still_fine(self):
        # Exempt means "not required", not "not allowed".
        c = complete(items=[complete_item(
            requisition_type="Others", item_code="3218-60", description="x",
        )])
        assert submission_errors(c) == []


class TestConditionalRequisitionFields:
    def test_store_requires_a_reference_number(self):
        c = complete(items=[complete_item(requisition_type="Store", reference_number=None)])
        errors = submission_errors(c)
        assert any("Reference no." in e for e in errors)

    def test_engineering_requires_reference_job_and_mo(self):
        c = complete(items=[complete_item(
            requisition_type="Engineering",
            reference_number=None, job_number=None, mo_number=None,
        )])
        errors = submission_errors(c)
        assert any("Reference no." in e for e in errors)
        assert any("Job no." in e for e in errors)
        assert any("MO no." in e for e in errors)

    def test_others_requires_a_description(self):
        c = complete(items=[complete_item(
            requisition_type="Others", item_code=None, description=None,
        )])
        assert any("Description" in e for e in submission_errors(c))

    def test_store_does_not_require_job_or_mo(self):
        c = complete(items=[complete_item(
            requisition_type="Store", reference_number="R",
            job_number=None, mo_number=None,
        )])
        assert submission_errors(c) == []


class TestDateOrdering:
    def test_eta_before_etd_is_refused(self):
        c = complete(etd="2026-05-10", eta="2026-05-01")
        assert "ETA cannot be before ETD" in submission_errors(c)

    def test_eta_after_etd_is_fine(self):
        assert submission_errors(complete(etd="2026-05-01", eta="2026-05-10")) == []

    def test_same_day_is_fine(self):
        assert submission_errors(complete(etd="2026-05-01", eta="2026-05-01")) == []

    def test_neither_date_set_is_not_an_error(self):
        # Shipping dates belong to a later step; submit does not require them.
        assert submission_errors(complete(etd=None, eta=None)) == []

    def test_only_one_date_set_is_not_an_error(self):
        assert submission_errors(complete(etd="2026-05-01", eta=None)) == []
        assert submission_errors(complete(etd=None, eta="2026-05-01")) == []


class TestLaterStepsAreNotRequired:
    """Steps 3+ are deliberately outside the rule set.

    A consignment is logged before prices, ETAs, GD numbers or landed costs
    exist. Requiring any of them at submit would make the record unenterable
    until it had already arrived, which is the opposite of what it is for.
    """

    def test_no_landed_cost_is_required(self):
        c = complete(items=[complete_item(elc=None, alc=None)])
        assert submission_errors(c) == []

    def test_no_unit_price_is_required(self):
        c = complete(items=[complete_item(unit_price=None)])
        assert submission_errors(c) == []
