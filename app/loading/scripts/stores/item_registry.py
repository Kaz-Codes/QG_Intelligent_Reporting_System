"""Register item codes that the transactional sheets use but the catalogue lacks.

WHY
    `purchases_data.item_code` and `issuance.item_code` are foreign keys onto
    `items`. The items catalogue is exported separately and lags behind: the
    current purchases workbook references 30 codes the catalogue has never heard
    of, and issuance references 3. Loading either one untouched fails outright on
    the foreign key and takes the whole reload with it.

WHY NOT JUST NULL THE CODE
    Nulling an unknown code would let the row load, but it would also cut it off
    from its item — and the category comes from `items`, so those rows would
    silently vanish from every category chart. The rows are real purchases; the
    catalogue is simply stale.

WHY THIS IS SAFE
    The transactional rows carry everything a minimal catalogue row needs (name,
    specification, category), so nothing is invented. The rows land
    `is_verified = False`: they were harvested from a transaction, not from the
    catalogue export, so they show up in the Masters review queue for somebody
    to confirm — the same treatment seeded customers get.

    Affects 0.1% of rows, so this is a gap-filler, not a second import path.
"""

from app.loading.scripts.etl_common import clean_text


def _existing_codes(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT item_code FROM items WHERE item_code IS NOT NULL")
        return {row[0] for row in cur.fetchall()}


def register_missing_items(conn, df, code_column, name_column,
                           spec_column=None, category_column=None, label=""):
    """Insert a minimal catalogue row for every unknown code in `df`."""
    existing = _existing_codes(conn)

    new_rows = {}

    for _, row in df.iterrows():
        code = clean_text(row.get(code_column))

        if not code or code in existing or code in new_rows:
            continue

        name = clean_text(row.get(name_column))
        if not name:
            # A code with no name is not enough to make a catalogue entry from.
            continue

        new_rows[code] = (
            code,
            name,
            clean_text(row.get(spec_column)) if spec_column else None,
            clean_text(row.get(category_column)) if category_column else None,
        )

    if not new_rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO items
                   (item_code, name, default_specification, category,
                    is_active, is_verified)
               VALUES (%s, %s, %s, %s, true, false)
               ON CONFLICT (item_code) DO NOTHING""",
            list(new_rows.values()),
        )
    conn.commit()

    print(f"  {label}: added {len(new_rows)} item(s) the catalogue was missing "
          f"(unverified, for review)")

    return len(new_rows)
