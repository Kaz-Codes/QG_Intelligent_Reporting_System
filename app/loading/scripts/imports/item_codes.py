"""Fill in the imports sheet's missing Item Codes.

WHY THIS EXISTS
    The consignment loader groups the sheet into imports and keeps only rows
    that carry an Item Code — a row without one is dropped outright. In the
    current workbook 294 of 451 rows have no code, so loading it untouched would
    silently discard 65% of the import lines.

HOW A CODE IS CHOSEN  (first rule that fires wins)
    1. the sheet's own Item Code
    2. a code already on another row for the SAME item in this sheet
    3. the items master, matched on (name, spec) — unique matches only
    4. a generated code, derived from the item itself

WHAT MAKES TWO ROWS "THE SAME ITEM"
    The item NAME plus its SPECIFICATION. Name alone is not enough and the data
    proves it: in the items master "servo drive" carries four different codes
    that differ only by spec, so matching on name would hand a 3kW drive the
    code of a 7.5kW one. Where the spec is blank the name alone identifies the
    item, as agreed.

WHY THE GENERATED CODE IS A HASH, NOT A COUNTER
    It has to be STABLE: the same item must get the same code on every reload,
    or the codes churn each time the sheet is loaded and nothing downstream can
    rely on them. A counter renumbers everything the moment an item is inserted
    earlier in the sheet; a hash of the item's own identity does not move.

    Every code in the items master matches `<digits>-<digits>`, so the `IMP-`
    prefix cannot collide with a real one.
"""

import hashlib

from app.loading.scripts.etl_common import clean_text

GENERATED_PREFIX = "IMP-"

# Long enough that a collision across a few hundred items is negligible, short
# enough to stay readable in a table cell. Extended automatically on the (very
# unlikely) chance two items hash to the same prefix.
_HASH_LENGTH = 8


def item_key(name, spec):
    """The identity of an item: normalised name + spec.

    Returns None when there is no name — a row with no item name is not a line,
    and giving it a code would invent one.
    """
    clean_name = clean_text(name)
    if not clean_name:
        return None

    clean_spec = clean_text(spec) or ""
    return (clean_name.strip().lower(), clean_spec.strip().lower())


def generated_code(key, taken=()):
    """A stable code for an item that exists nowhere else."""
    digest = hashlib.sha1("||".join(key).encode("utf-8")).hexdigest()

    length = _HASH_LENGTH
    while length <= len(digest):
        code = GENERATED_PREFIX + digest[:length].upper()
        if code not in taken:
            return code
        length += 4

    # Unreachable in practice; a full 40-char digest collision would be needed.
    raise RuntimeError(f"could not generate a unique code for {key!r}")


def build_master_index(conn):
    """(name, spec) -> item_code, for pairs the master maps unambiguously.

    A pair that carries several codes in the master is deliberately LEFT OUT:
    the sheet gives us nothing to choose between them, so the row falls through
    to a generated code rather than being assigned one of them at random.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT lower(btrim(name)),
                   lower(btrim(coalesce(default_specification, ''))),
                   item_code
            FROM items
            WHERE item_code IS NOT NULL AND btrim(name) <> ''
        """)
        rows = cur.fetchall()

    codes_by_key = {}
    for name, spec, code in rows:
        codes_by_key.setdefault((name, spec), set()).add(code)

    return {k: next(iter(v)) for k, v in codes_by_key.items() if len(v) == 1}


def assign_item_codes(df, conn, name_column="Item Name",
                      spec_column="Specs/Standard", code_column="Item Code"):
    """Fill `code_column` in place. Returns a small report dict.

    Rows with no item name are left alone — the loader drops them, which is the
    right outcome for a row that names no item.
    """
    master = build_master_index(conn)

    # Pass 1: what code does each item already have somewhere in this sheet?
    in_sheet = {}
    conflicts = set()

    for _, row in df.iterrows():
        key = item_key(row.get(name_column), row.get(spec_column))
        code = clean_text(row.get(code_column))

        if key is None or code is None:
            continue

        if key in in_sheet and in_sheet[key] != code:
            conflicts.add(key)
            continue

        in_sheet[key] = code

    taken = set(in_sheet.values()) | set(master.values())

    # Pass 2: fill the gaps.
    report = {
        "rows": len(df),
        "already_coded": 0,
        "from_sheet_sibling": 0,
        "from_master": 0,
        "generated": 0,
        "no_item_name": 0,
        "conflicting_pairs": len(conflicts),
        "generated_items": 0,
    }

    generated_by_key = {}

    for index, row in df.iterrows():
        key = item_key(row.get(name_column), row.get(spec_column))

        if key is None:
            report["no_item_name"] += 1
            continue

        if clean_text(row.get(code_column)) is not None:
            report["already_coded"] += 1
            continue

        if key in in_sheet:
            df.at[index, code_column] = in_sheet[key]
            report["from_sheet_sibling"] += 1
            continue

        if key in master:
            code = master[key]
            df.at[index, code_column] = code
            in_sheet[key] = code
            report["from_master"] += 1
            continue

        if key not in generated_by_key:
            code = generated_code(key, taken)
            generated_by_key[key] = code
            taken.add(code)

        df.at[index, code_column] = generated_by_key[key]
        report["generated"] += 1

    report["generated_items"] = len(generated_by_key)
    return report
