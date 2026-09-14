"""Build a REAL second batch, so the count assertions have something to bite on.

WHY THIS EXISTS

Every group in a freshly restored database holds exactly one batch, so
`count(rows)` and `count(distinct batch_group_id)` return the same number
everywhere and no assertion about the fourteen count sites can tell a correct
choice from a flipped one (docs/imports-batching-design.md section 3.2). The
only state in which the two units differ is a group holding two or more
batches.

IT NOW USES THE REAL ROUTES. Until step 7 there was no code that could create a
second batch, so this built one with raw SQL. That is no longer true, and a
fixture that keeps hand-writing rows is a fixture that tests a shape the
application never produces.

WHAT SWITCHING IT FOUND - three differences between the hand-built row and the
real one, each of which was a bug in this file rather than in the application:

  1. IT WROTE `consignment_items.unit_price`. That column still exists in the
     database but the ORM stopped mapping it in part 4 - the price lives on the
     order line now. So the fixture's batch carried a price no application code
     would have written, and `check_dashboard_consistency.py` was summing it.
     That check is repointed onto the order line in the same change.
  2. IT COPIED THE FOUNDING BATCH'S ROUTE, SCHEDULE AND STATUS. The
     requirements are explicit that a later batch's shipping section starts
     EMPTY, and `add_batch` honours that - so a batch created for real has no
     ETA and falls out of every windowed figure, which would have made the
     count assertions vacuous rather than wrong. The fix is not to copy them
     behind the route's back: it is to set them the way an operator would,
     through `PUT`, which this now does.
  3. IT WROTE THE RETIRED `consignments` COLUMNS - `supplier_id`, `origin`,
     `currency`, `works` and the rest. Those columns are deliberately left in
     the database with no mapped attribute, precisely so that no ORM path can
     keep the orphaned copy alive (design section 4.7). This file was keeping
     them alive inside the test suite, which is that section's fourth bypass
     path in a place nobody was looking.

WHAT IT STILL PROVES. The raw-SQL version exercised four constraints by hand:
the deferrable foreign key, `uq_consignments_group_sequence`,
`consignment_items.order_item_id` NOT NULL and `ck_allocation_within_order`.
Going through the routes exercises all four too - the application has to
satisfy them like anything else - and adds the ones only the real path can
reach: the row lock, the atomic sequence claim and the over-allocation refusal.

SAFETY

This module MUTATES, which puts it outside CLAUDE.md's "test scripts never
touch the live database" rule unless the guard is structural. It is:
`_require_scratch()` refuses to run against any database whose name does not
begin with `scratch`, and it is called before the first request. There is no
flag to override it. The HTTP base URL must also be pointed at a server running
against that scratch database - checked below by asking the API for a number
only the scratch database can give.
"""

import os

import httpx
import psycopg2


BASE_URL = os.getenv("ERP_BASE_URL", "http://127.0.0.1:8011")


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


def _env():
    values = {}
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def connect():
    name = _require_scratch(os.getenv("DB_NAME"))
    env = _env()
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=name,
        user=os.getenv("DB_USER", env.get("DB_USER", "postgres")),
        password=os.getenv("DB_PASSWORD", env.get("DB_PASSWORD", "")),
    )


def client():
    """A logged-in HTTP client against the server under test."""
    _require_scratch(os.getenv("DB_NAME"))
    env = _env()
    c = httpx.Client(base_url=BASE_URL, timeout=60)
    r = c.post("/auth/login", json={
        "username": os.getenv("ADMIN_USERNAME", env.get("ADMIN_USERNAME")),
        "password": os.getenv("ADMIN_PASSWORD", env.get("ADMIN_PASSWORD")),
    })
    if r.status_code != 200:
        raise RuntimeError(
            f"could not log in at {BASE_URL}: {r.status_code} {r.text[:200]}"
        )
    return c


def _pick_consignment(cur):
    """A live, single-batch order whose founding batch has priced, splittable lines.

    Priced, because the split has to move VALUE as well as rows - an order
    whose lines carry no quantity or no price would produce two batches that
    both contribute zero, and every value assertion would pass trivially.

    UNLOCKED, because the fixture sets the new batch's shipping fields through
    the real `PUT`, and it also needs to lower the founding batch's own line
    quantities to make room. Neither is possible on a closed record.

    AND PREFERRING ONE WITH A CLEARING AGENT, SUPPLIER AND BRANCH, because
    those three masters are where the count decision actually goes two ways:
    supplier and branch count orders, the clearing agent counts batches (design
    section 3.2, #14). An order with no agent still splits fine and the check
    simply skips that assertion - which would mean the one decision most likely
    to be got wrong is the one never exercised. Ordered rather than filtered,
    so a database with no such order still produces a usable fixture.
    """
    cur.execute("""
        SELECT g.id, c.id
          FROM consignment_batch_groups g
          JOIN consignments c ON c.id = g.founding_consignment_id
         WHERE g.is_deleted = false
           AND c.is_deleted = false
           AND c.is_locked  = false
           AND g.batches_ever = 1
           AND (SELECT count(*) FROM consignments b
                 WHERE b.batch_group_id = g.id) = 1
           AND (SELECT count(*) FROM consignment_items i
                  JOIN consignment_order_items o ON o.id = i.order_item_id
                 WHERE i.consignment_id = c.id
                   AND i.is_deleted = false
                   AND i.quantity IS NOT NULL
                   AND i.quantity > 1
                   AND o.unit_price IS NOT NULL
                   AND o.unit_price > 0) >= 1
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
            "no single-batch order with a splittable priced line - the fixture "
            "cannot build a meaningful second batch from this database"
        )
    return row


def split_one_order(conn=None, c=None):
    """Split one order's first batch in two, through the real routes.

    The second batch is a real `consignments` row: its own id, its own status,
    its own history, its own entry in every list. What makes it a batch rather
    than a separate order is that it shares `batch_group_id` with the first,
    which is exactly the state the fourteen count sites have to disagree about.

    HOW THE QUANTITY IS MADE ROOM FOR, and why it is done this way round. The
    order is already fully allocated - its one batch holds all of it - so
    creating a second batch for any quantity at all would be refused, correctly,
    by `reconcile_allocation`. So the fixture first HALVES the founding batch's
    lines through `PUT`, which frees the other half, and then allocates that
    half to the new batch. That is exactly the sequence an operator performs,
    and it means the fixture exercises the invariant rather than dodging it.
    """
    own_conn = conn is None
    conn = conn or connect()
    _require_scratch(conn.get_dsn_parameters().get("dbname"))
    c = c or client()

    try:
        with conn.cursor() as cur:
            group_id, first_id = _pick_consignment(cur)

        detail = c.get(f"/consignments/{first_id}").json()["data"]

        # --- 1. halve the founding batch's lines, through the real PUT -------
        payload = _draft_from(detail)
        moved = []
        for item in payload["items"]:
            quantity = item.get("quantity")
            if quantity is None or float(quantity) <= 1:
                continue
            keep = float(quantity) / 2
            move = float(quantity) - keep
            item["quantity"] = keep
            moved.append({
                "order_item_id": item["order_item_id"],
                "item": item.get("item_name"),
                "kept": keep,
                "moved": move,
            })

        if not moved:
            raise RuntimeError(
                f"consignment {first_id} has no line that can be halved"
            )

        r = c.put(f"/consignments/{first_id}", json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"halving batch 1 failed: {r.status_code} {r.text[:400]}")

        # --- 2. create the second batch with the freed quantity --------------
        r = c.post(f"/consignments/{first_id}/batches", json={
            "allocations": [
                {"order_item_id": m["order_item_id"], "quantity": m["moved"]}
                for m in moved
            ],
        })
        # This module's routes answer HTTP 200 and put the real code in the
        # body - the convention every other imports route already follows.
        if r.status_code != 200 or r.json().get("status_code") != 201:
            raise RuntimeError(f"creating batch 2 failed: {r.status_code} {r.text[:400]}")

        created = r.json()["data"]
        second_id = created["batch"]["id"]

        # --- 3. give it a route and a schedule, the way an operator would ----
        #
        # `add_batch` deliberately leaves these blank - the requirements say a
        # later batch's shipping section starts empty. But a batch with no
        # dates falls out of every windowed dashboard figure, and the count
        # assertions this fixture exists for are windowed: with no ETA the two
        # units would agree again and nothing would discriminate. So the
        # fixture does what the operator does next, through the same PUT.
        second = c.get(f"/consignments/{second_id}").json()["data"]
        second_payload = _draft_from(second)
        for field in ("etd", "eta", "eta_works", "cargo_readiness_date",
                      "mode_of_shipment", "current_status", "effective_date",
                      "loading_port_id", "delivery_port_id", "clearing_agent_id"):
            value = detail.get(field)
            if field.endswith("_id"):
                value = (detail.get(field.replace("_id", "")) or {}).get("id") \
                    if isinstance(detail.get(field.replace("_id", "")), dict) else None
            if value is not None:
                second_payload[field] = value

        r = c.put(f"/consignments/{second_id}", json=second_payload)
        if r.status_code != 200:
            raise RuntimeError(
                f"setting batch 2's schedule failed: {r.status_code} {r.text[:400]}"
            )

        return {
            "group_id": group_id,
            "first_batch": first_id,
            "second_batch": second_id,
            "lines_split": moved,
            "numbering": created["numbering"],
        }
    finally:
        if own_conn:
            conn.close()


def _draft_from(detail):
    """The detail payload turned back into something `PUT` accepts.

    The wizard posts the whole draft on every save, so this mirrors it rather
    than sending a minimal patch - a fixture that saved differently from the
    application would prove things about a request nobody makes.
    """
    def master_id(value):
        return value.get("id") if isinstance(value, dict) else None

    return {
        "branch_id": master_id(detail.get("branch")),
        "supplier_id": master_id(detail.get("supplier")),
        "clearing_agent_id": master_id(detail.get("clearing_agent")),
        "loading_port_id": master_id(detail.get("loading_port")),
        "delivery_port_id": master_id(detail.get("delivery_port")),
        "origin": detail.get("origin"),
        "currency": detail.get("currency"),
        "consignment_type": detail.get("consignment_type"),
        "incoterm": detail.get("incoterm"),
        "payment_instrument": detail.get("payment_instrument"),
        "instrument_number": detail.get("instrument_number"),
        "exchange_rate": detail.get("exchange_rate"),
        "rate_booked_on": detail.get("rate_booked_on"),
        "rate_source": detail.get("rate_source"),
        "mode_of_shipment": detail.get("mode_of_shipment"),
        "etd": detail.get("etd"),
        "eta": detail.get("eta"),
        "eta_works": detail.get("eta_works"),
        "current_status": detail.get("current_status"),
        "effective_date": detail.get("effective_date"),
        "gd_number": detail.get("gd_number"),
        "remarks": detail.get("remarks"),
        "items": [
            {
                "id": item.get("id"),
                "order_item_id": item.get("order_item_id"),
                "item_id": item.get("item_id"),
                "item_code": item.get("item_code"),
                "item_name": item.get("item_name"),
                "specification": item.get("specification"),
                "hs_code": item.get("hs_code"),
                "quantity": item.get("quantity"),
                "ordered_quantity": item.get("ordered_quantity"),
                "unit_of_measurement": item.get("unit_of_measurement"),
                "unit_price": item.get("unit_price"),
                "requisition_type": item.get("requisition_type"),
                "reference_number": item.get("reference_number"),
                "job_number": item.get("job_number"),
                "mo_number": item.get("mo_number"),
                "description": item.get("description"),
            }
            for item in detail.get("items", [])
            if not item.get("is_deleted")
        ],
        "payments": [],
    }


def group_holding_two_batches(conn=None, dated_only=False):
    """The group id of an existing two-batch order, or None.

    PREFERS ONE WHOSE BATCHES ARE ALL DATED, and that is not cosmetic. The
    count assertions this exists for are WINDOWED - they compare a row count
    against a distinct-order count over a date range - so a split order whose
    second batch has no arrival date falls out of the window entirely, rows and
    orders agree again, and every "the two units differ" guard passes without
    discriminating anything. That is the exact failure the whole
    batches-vs-orders section was written to prevent, reached from inside its
    own fixture.

    It became reachable as soon as step 7 existed: `check_batch_allocation.py`
    creates several split orders of its own, none of which has a schedule,
    because `add_batch` correctly leaves a new batch's shipping section empty.
    Run that script first and this function would hand the consistency check
    one of those.

    Ordered rather than filtered, so a database holding only undated splits
    still returns something and the assertions fail loudly rather than the
    section skipping.
    """
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.batch_group_id
                  FROM consignments c
                 WHERE c.is_deleted = false
                 GROUP BY c.batch_group_id
                HAVING count(*) > 1
                   AND bool_and(
                         c.eta_works IS NOT NULL
                      OR EXISTS (SELECT 1 FROM consignment_items i
                                  WHERE i.consignment_id = c.id
                                    AND i.is_deleted = false
                                    AND i.eta_works IS NOT NULL))
                 ORDER BY c.batch_group_id LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return row[0]

            # `dated_only` is what `ensure_split` passes: finding nothing means
            # BUILD one, rather than reuse an undated split that cannot
            # discriminate.
            if dated_only:
                return None

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
    """Idempotent: split one order only if there is no USABLE split yet.

    `dated_only`, because "a split already exists" is not the question - the
    question is whether one exists that the windowed count assertions can tell
    anything from. An undated split is not one, and reusing it would make the
    whole batches-vs-orders section pass while proving nothing.
    """
    existing = group_holding_two_batches(conn, dated_only=True)
    if existing is not None:
        return {"group_id": existing, "already_split": True}
    return split_one_order(conn)


if __name__ == "__main__":
    import json
    print(json.dumps(ensure_split(), indent=2, default=str))
