"""Build a REAL second batch, so the count assertions have something to bite on.

WHY THIS EXISTS

Every group in every database today holds exactly one batch, so `count(rows)`
and `count(distinct batch_group_id)` return the same number everywhere and no
assertion about the fourteen count sites can tell a correct choice from a
flipped one (docs/imports-batching-design.md §3.2). The only state in which the
two units differ is a group holding two or more batches, and nothing creates one
until §9 step 7. This builds one by hand so step 6's decisions can be checked
before step 7 exists.

WHY RAW SQL AND NOT ORM OBJECTS

Because a fixture that cannot fail on the schema proves nothing about the
figures it is there to discriminate. Building this through the ORM would let
SQLAlchemy sequence the inserts and would never touch:

  - `fk_consignments_batch_group`, which is DEFERRABLE INITIALLY DEFERRED — the
    only reason a consignment and its group can be inserted at all (§4.1);
  - `uq_consignments_group_sequence`, which is what makes 177-2 mean one
    shipment for ever;
  - `consignment_items.order_item_id` NOT NULL, which is what ties a batch line
    to the order line above it;
  - `ck_allocation_within_order`, the backstop on over-allocation (§6 B3).

Every one of those is exercised here. The split re-allocates an existing
quantity rather than inventing one, so `allocated_quantity` is unchanged and
the CHECK is satisfied for the right reason rather than by avoiding it.

SAFETY

This module MUTATES, which puts it outside CLAUDE.md's "test scripts never
touch the live database" rule unless the guard is structural. It is:
`_require_scratch()` refuses to run against any database whose name does not
begin with `scratch`, and it is called before the first statement. There is no
flag to override it.
"""

import os

import psycopg2


class NotAScratchDatabase(RuntimeError):
    pass


def _require_scratch(name):
    """The guard. A comment saying 'scratch only' is not one."""
    if not name or not name.lower().startswith("scratch"):
        raise NotAScratchDatabase(
            f"batch_fixture writes rows and refuses to run against {name!r}. "
            "Point DB_NAME at a database whose name starts with 'scratch'."
        )
    return name


def connect():
    name = _require_scratch(os.getenv("DB_NAME"))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=name,
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def _pick_group(cur):
    """A live, single-batch group whose founding batch has priced lines.

    Priced, because the split has to move VALUE as well as rows — a group whose
    lines carry no quantity or no price would produce two batches that both
    contribute zero, and every value assertion would pass trivially.

    AND PREFERRING ONE WITH A CLEARING AGENT, SUPPLIER AND BRANCH, because those
    three masters are where the count decision actually goes two ways: supplier
    and branch count orders, the clearing agent counts batches (design section
    3.2, #14). A group with no agent still splits fine and the check simply
    skips that assertion — which means the one decision most likely to be got
    wrong would be the one never exercised. Ordered rather than filtered, so a
    database with no such group still produces a usable fixture.
    """
    cur.execute("""
        SELECT g.id, c.id
          FROM consignment_batch_groups g
          JOIN consignments c ON c.id = g.founding_consignment_id
         WHERE g.is_deleted = false
           AND c.is_deleted = false
           AND c.is_locked  = false
           AND (SELECT count(*) FROM consignments b
                 WHERE b.batch_group_id = g.id) = 1
           AND (SELECT count(*) FROM consignment_items i
                 WHERE i.consignment_id = c.id
                   AND i.is_deleted = false
                   AND i.quantity IS NOT NULL
                   AND i.quantity > 1) >= 1
         ORDER BY
           (c.clearing_agent_id IS NOT NULL) DESC,
           (g.supplier_id IS NOT NULL) DESC,
           (g.works_branch_id IS NOT NULL) DESC,
           g.id
         LIMIT 1
    """)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "no single-batch group with a splittable priced line — the fixture "
            "cannot build a meaningful second batch from this database"
        )
    return row


def split_one_group(conn=None):
    """Split one order's first batch in two. Returns a description of what moved.

    The second batch is a REAL `consignments` row: its own id, its own status,
    its own history, its own entry in every list. What makes it a batch rather
    than a separate order is that it shares `batch_group_id` with the first,
    which is exactly the state the fourteen count sites have to disagree about.
    """
    own = conn is None
    conn = conn or connect()
    else_name = conn.get_dsn_parameters().get("dbname")
    _require_scratch(else_name)

    try:
        with conn:
            with conn.cursor() as cur:
                # The deferred foreign key is only deferred INSIDE a
                # transaction, and only if asked. Without this the insert order
                # below fails exactly as §4.1 measured.
                cur.execute("SET CONSTRAINTS ALL DEFERRED")

                group_id, first_id = _pick_group(cur)

                cur.execute("""
                    SELECT id, order_item_id, quantity, item_name, eta_works
                      FROM consignment_items
                     WHERE consignment_id = %s AND is_deleted = false
                       AND quantity IS NOT NULL AND quantity > 1
                     ORDER BY id
                """, (first_id,))
                lines = cur.fetchall()

                # The new batch copies the founding batch's own per-shipment
                # fields. It is a second ARRIVAL of the same order, so the
                # commercial half already lives on the group and is not copied.
                cur.execute("""
                    INSERT INTO consignments (
                        batch_group_id, batch_sequence,
                        current_status, record_state, is_locked, is_deleted,
                        created_by_id, created_at, updated_at,
                        branch_id, supplier_id, works, clearing_agent_id,
                        origin, currency, consignment_type, incoterm,
                        requisition_date, required_date,
                        mode_of_shipment, etd, eta, eta_works,
                        payment_instrument, instrument_number,
                        exchange_rate, rate_booked_on, rate_source,
                        loading_port_id, delivery_port_id
                    )
                    SELECT
                        c.batch_group_id, 2,
                        c.current_status, c.record_state, false, false,
                        c.created_by_id, now(), now(),
                        c.branch_id, c.supplier_id, c.works, c.clearing_agent_id,
                        c.origin, c.currency, c.consignment_type, c.incoterm,
                        c.requisition_date, c.required_date,
                        c.mode_of_shipment, c.etd, c.eta, c.eta_works,
                        c.payment_instrument, c.instrument_number,
                        c.exchange_rate, c.rate_booked_on, c.rate_source,
                        c.loading_port_id, c.delivery_port_id
                      FROM consignments c
                     WHERE c.id = %s
                 RETURNING id
                """, (first_id,))
                second_id = cur.fetchone()[0]

                # batches_ever is never decremented and drives the display
                # suffix, so it moves with the batch that caused it.
                cur.execute(
                    "UPDATE consignment_batch_groups SET batches_ever = 2 "
                    "WHERE id = %s", (group_id,)
                )

                moved = []
                for line_id, order_item_id, qty, item_name, line_eta in lines:
                    # HALF EACH, and the halves must ADD BACK to what was
                    # ordered: allocated_quantity is unchanged, so
                    # ck_allocation_within_order is satisfied because the sum is
                    # right, not because the constraint was dodged.
                    keep = qty / 2
                    move = qty - keep

                    cur.execute(
                        "UPDATE consignment_items SET quantity = %s WHERE id = %s",
                        (keep, line_id),
                    )
                    cur.execute("""
                        INSERT INTO consignment_items (
                            consignment_id, order_item_id, is_deleted,
                            created_at, updated_at,
                            item_id, item_code, item_name, placeholder_name,
                            specification, hs_code,
                            quantity, unit_price, unit_of_measurement,
                            eta_works, requisition_type,
                            reference_number, job_number, mo_number, description
                        )
                        SELECT
                            %s, i.order_item_id, false, now(), now(),
                            i.item_id, i.item_code, i.item_name, i.placeholder_name,
                            i.specification, i.hs_code,
                            %s, i.unit_price, i.unit_of_measurement,
                            i.eta_works, i.requisition_type,
                            i.reference_number, i.job_number, i.mo_number, i.description
                          FROM consignment_items i
                         WHERE i.id = %s
                    """, (second_id, move, line_id))

                    moved.append({
                        "order_item_id": order_item_id,
                        "item": item_name,
                        "kept": keep,
                        "moved": move,
                        "eta": line_eta,
                    })

                # The stored money totals are recomputed on every save, so a
                # fixture that splits the lines and leaves the totals alone
                # would put the two batches' headline value at DOUBLE the
                # order's — and every value assertion would then be checking
                # arithmetic the fixture got wrong rather than the code.
                for cid in (first_id, second_id):
                    cur.execute("""
                        UPDATE consignments c
                           SET foreign_total = t.ft,
                               pkr_total = CASE WHEN c.exchange_rate IS NULL
                                                THEN NULL
                                                ELSE t.ft * c.exchange_rate END
                          FROM (SELECT COALESCE(SUM(i.quantity * i.unit_price), 0) AS ft
                                  FROM consignment_items i
                                 WHERE i.consignment_id = %s
                                   AND i.is_deleted = false) t
                         WHERE c.id = %s
                    """, (cid, cid))

                # The sequences were bumped past these ids by the loaders, but a
                # hand-written insert is exactly the case CLAUDE.md records as
                # having broken "Add Supplier" — so leave nothing to chance.
                cur.execute("SELECT setval(pg_get_serial_sequence('consignments','id'), "
                            "(SELECT max(id) FROM consignments))")
                cur.execute("SELECT setval(pg_get_serial_sequence('consignment_items','id'), "
                            "(SELECT max(id) FROM consignment_items))")

        return {
            "group_id": group_id,
            "first_batch": first_id,
            "second_batch": second_id,
            "lines_split": moved,
        }
    finally:
        if own:
            conn.close()


def group_holding_two_batches(conn=None):
    """The group id of an existing two-batch group, or None."""
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT batch_group_id FROM consignments
                 WHERE is_deleted = false
                 GROUP BY batch_group_id HAVING count(*) > 1
                 ORDER BY batch_group_id LIMIT 1
            """)
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        if own:
            conn.close()


def ensure_split(conn=None):
    """Idempotent: split one group only if nothing is split yet."""
    existing = group_holding_two_batches(conn)
    if existing is not None:
        return {"group_id": existing, "already_split": True}
    return split_one_group(conn)


if __name__ == "__main__":
    import json
    print(json.dumps(ensure_split(), indent=2, default=str))
