from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_IMPORTS
from app.imports.helpers import fetch_consignment, fetch_consignment_history, fetch_latest_consignment_history, revert, recompute_derived, RETIRED_HISTORY_KEYS, reconcile_allocation, AllocationError
from app.imports.serializers import serialize_consignment
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

@router.put("/revert-update/{consignment_id}/{change_history_id}")
def revert_update(
        consignment_id : int,
        change_history_id : int, 
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, CAN_EDIT_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        consignment_history = fetch_consignment_history(db, consignment.id, change_history_id)
        latest_consignment_history = fetch_latest_consignment_history(db, consignment.id)

        if not consignment_history or not latest_consignment_history:
            raise HTTPException(
                status_code=404,
                detail="Consignment history not found"
            )


        if consignment_history.is_reverted:
            raise HTTPException(
                status_code=200,
                detail="Changes have already been reverted"
            )
        
        if consignment_history.id != latest_consignment_history.id:
            raise HTTPException(
                status_code=400,
                detail="Revert latest changes first"
            )                     

        # Make the consignment history reverted so that user cannot revert it again
        consignment_history.is_reverted = True
        consignment_history.reverted_by_id = user.id
        consignment_history.reverted_at = datetime.now(timezone.utc)

        # Revert updates. `skipped` names any field the history recorded whose
        # column has since been retired - see RETIRED_HISTORY_KEYS.
        skipped = revert(consignment_history, consignment, db)

        # A REVERT IS AN ALLOCATION CHANGE TOO, AND IT IS THE ONE THAT CAN GO
        # OVER FROM BELOW.
        #
        # Two ways this path moves the invariant, and the second is the reason
        # it needs the check rather than merely deserving it:
        #
        #   * it restores line quantities, re-adds lines an update soft-deleted
        #     and removes lines an update added - all of which change the sum;
        #   * `ordered_quantity` is on the ORDER LINE, shared by every batch, so
        #     reverting an edit made on batch 2 can put the ORDER back to a
        #     smaller figure while batch 1's allocation stays where it is.
        #     Nothing about that involves an over-large allocation being typed -
        #     the limit comes DOWN to meet a sum that was legal when it was
        #     written.
        #
        # The same locked function every other write path ends at, so a revert
        # cannot be governed by a different rule from the save it is undoing.
        reconcile_allocation(db, consignment.batch_group_id)

        # Derived totals are not part of the change history (they are never
        # sent by the client), so recompute them from the reverted state.
        recompute_derived(consignment)

        db.commit()
        db.refresh(consignment)

        # THE USER IS TOLD WHAT DID NOT COME BACK.
        #
        # A revert that restores most of a change and says "Consignment
        # reverted" is the original bug with better manners: the caller cannot
        # tell a complete undo from a partial one. Where a recorded field names
        # a column that has since been retired, the revert still succeeds - the
        # rest genuinely is restored - and the response says which fields it
        # could not put back and why.
        detail = "Consignment reverted"
        if skipped:
            reasons = "; ".join(
                f"{key} ({RETIRED_HISTORY_KEYS[key]})" for key in skipped
            )
            detail = (
                f"Consignment reverted, except: {reasons}. "
                f"Everything else was restored."
            )

        return {
            "status_code":200,
            "detail":detail,
            "data":serialize_consignment(consignment, db),
            # Machine-readable alongside the sentence, so the front end can
            # surface it without parsing prose.
            "skipped_fields":skipped,
        }

    except AllocationError as e:
        # Nothing is reverted. A revert that restored half a change and left
        # the order over-allocated would be worse than one that refused and
        # said why - which is the same principle the `skipped_fields` reporting
        # below is built on.
        db.rollback()
        raise HTTPException(
            status_code=e.status_code,
            detail=(f"This change cannot be undone: {e} Adjust the batches "
                    f"that hold this quantity first."),
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.revert_update")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 