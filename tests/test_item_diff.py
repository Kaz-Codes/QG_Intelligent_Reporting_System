"""`updated_items` — what an ABSENT payload key means.

WHY THIS FILE EXISTS. At c8a450f, saving any existing consignment through the
imports wizard returned a 500 and stored nothing:

    UPDATE consignment_order_items SET item_id=NULL, ordered_quantity=NULL
    NotNullViolation: null value in column "ordered_quantity"

The wizard does not send `ordered_quantity` or `order_item_id` — it has no
control for either, and the server owns both (`resolve_ordered_quantity`,
`resolve_order_line`). `ConsignmentItemSchema` defaults every optional field to
None and `model_dump()` cannot tell a null the client sent from a key it never
mentioned, so the diff below read the absence as "set it to null", wrote the
NULL, and the next autoflush hit the constraint.

THE ASYMMETRY IS THE WHOLE POINT, and it is why `exclude_unset=True` across the
payload would be the wrong fix. For an ORDINARY field an absent key really does
mean "clear it": `draftToPayload` omits an emptied input rather than sending an
empty string, so clearing a specification in the wizard works precisely because
the key disappears. Only the server-resolved NOT NULL columns must survive
their own absence.

Both halves are asserted here. A change that makes absence mean "leave it"
everywhere breaks the first group; a change that makes it mean "clear it"
everywhere brings the 500 back.

No database: `item_current_values` is the one thing in `updated_items` that
needs a mapper, and it is replaced with a plain dict of what is stored.
"""

from decimal import Decimal

import pytest

from app.imports import helpers
from app.imports.schemas import ConsignmentItemSchema

from conftest import Obj


#---------------------------------------------------------------------------
# The stand-ins
#---------------------------------------------------------------------------

STORED = {
    "id": 401,
    "ordered_quantity": Decimal("500"),
    "order_item_id": 401,
    "item_id": 77,
    "quantity": Decimal("500"),
    "specification": "cast, grade B",
    "unit_price": Decimal("440"),
}


@pytest.fixture
def diff(monkeypatch):
    """`updated_items` over one stored line, given one posted payload dict.

    Returns the per-field diff for line 401, or {} when nothing changed.
    """
    monkeypatch.setattr(helpers, "item_current_values", lambda item: dict(STORED))

    def run(posted):
        consignment = Obj(items=[Obj(id=401)])
        data = Obj(items=[ConsignmentItemSchema(**posted)])
        changes = helpers.updated_items(consignment, data, db=None)
        return changes[0] if changes else {}

    return run


#---------------------------------------------------------------------------
# The server-resolved columns
#---------------------------------------------------------------------------

class TestAnAbsentServerResolvedKeyIsNotAChange:

    def test_a_payload_without_ordered_quantity_does_not_clear_it(self, diff):
        """The exact 500. The wizard sends id, name, code, quantity, price."""
        assert "ordered_quantity" not in diff({
            "id": 401, "quantity": Decimal("500"), "unit_price": Decimal("440"),
        })

    def test_a_payload_without_order_item_id_does_not_clear_it(self, diff):
        assert "order_item_id" not in diff({
            "id": 401, "quantity": Decimal("500"), "unit_price": Decimal("440"),
        })

    def test_neither_survives_being_left_out_of_a_full_wizard_save(self, diff):
        """The whole payload the wizard actually posts for an untouched line."""
        changed = diff({
            "id": 401, "quantity": Decimal("500"), "unit_price": Decimal("440"),
            "specification": "cast, grade B",
        })
        assert "ordered_quantity" not in changed
        assert "order_item_id" not in changed

    def test_an_EXPLICIT_ordered_quantity_is_still_a_change(self, diff):
        """Absence is what is ignored, not the field. A client that means to
        raise the order quantity — which is the only way to do it after a
        split — must still be heard."""
        changed = diff({"id": 401, "ordered_quantity": Decimal("800")})
        assert changed["ordered_quantity"]["new_value"] == Decimal("800")
        assert changed["ordered_quantity"]["old_value"] == Decimal("500")

    def test_an_EXPLICIT_order_item_id_is_still_a_change(self, diff):
        changed = diff({"id": 401, "order_item_id": 9})
        assert changed["order_item_id"]["new_value"] == 9


class TestTheRESIDUE_reported_not_fixed:
    """`item_id` IS still cleared by an untouched save, and that is a real
    defect — just not this one's, and not one to resolve unilaterally.

    It is the line's link to the `items` master. Nulling it does not 500,
    because the column is nullable, but it loses which master row the line
    came from, which `order_view.line_item_master` reads and the imports
    dashboard's category-delay chart is built on. 20 of 102 lines on the
    scratch clone still carry one.

    IT IS NOT IN `SERVER_RESOLVED_ITEM_FIELDS` on purpose. Unlike the two
    above, no server function owns it: the wizard picks items through the
    master search and simply never posts the id back. Whether a save should
    re-link the line to the master, or leave whatever link it has, is a
    business call about rule 12 ("the line stores its own copy"), and
    CLAUDE.md says to raise that rather than settle it in a diff. Pinned here
    so the behaviour is stated rather than discovered again.
    """

    def test_item_id_is_still_cleared_by_an_absent_key(self, diff):
        changed = diff({"id": 401, "quantity": Decimal("500")})
        assert changed["item_id"] == {"old_value": 77, "new_value": None}

#---------------------------------------------------------------------------
# …and the ordinary fields, which must keep behaving the opposite way
#---------------------------------------------------------------------------

class TestAnAbsentORDINARYKeyStillClears:

    def test_dropping_the_specification_clears_it(self, diff):
        """This is how the wizard empties a text field: draftToPayload omits
        it. If absence ever came to mean "leave it" across the board, clearing
        a field would silently stop working."""
        changed = diff({"id": 401, "quantity": Decimal("500"),
                        "unit_price": Decimal("440")})
        assert changed["specification"] == {
            "old_value": "cast, grade B", "new_value": None,
        }

    def test_dropping_the_unit_price_clears_it(self, diff):
        changed = diff({"id": 401, "quantity": Decimal("500")})
        assert changed["unit_price"]["new_value"] is None


class TestTheSetIsDeclaredRatherThanInferred:

    def test_it_names_exactly_the_columns_an_absent_key_must_not_clear(self):
        """The membership rule is NOT NULL *and* resolved by the server.

        `price_basis` joined when it joined `ConsignmentItemSchema`: it is NOT
        NULL with a server default, so a payload omitting it would write NULL
        and 500 on the constraint - the `ordered_quantity` bug one column
        along. Its two companions, `weight_unit_price` and `unit_weight`, are
        NULLABLE and are deliberately absent: an absent key clearing them is
        the ordinary "the operator emptied the field" behaviour.

        Pinned as an exact set rather than a subset, because the failure this
        guards is the set growing by habit until clearing a field stops
        working somewhere nobody tested."""
        assert set(helpers.SERVER_RESOLVED_ITEM_FIELDS) == {
            "ordered_quantity", "order_item_id", "price_basis",
        }

    def test_the_nullable_weight_columns_are_NOT_in_it(self):
        for nullable in ("weight_unit_price", "unit_weight"):
            assert nullable not in helpers.SERVER_RESOLVED_ITEM_FIELDS
