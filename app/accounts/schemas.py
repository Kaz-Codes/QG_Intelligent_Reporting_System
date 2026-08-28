import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.enums import NotificationTier

# E.164 AND NOTHING ELSE: a leading '+', a country code starting 1-9, then
# digits — no spaces, dashes or brackets. Matches the column comment on
# User.phone_number, and the reason is the same: a table holding
# "+923001234567" for some rows and "+92 300 1234567" for others cannot be
# normalised later without guessing at the country.
E164 = re.compile(r"^\+[1-9]\d{6,14}$")

_TIERS = {t.value for t in NotificationTier}


class UserSchema(BaseModel):
    username: str = Field(..., max_length=255, min_length=8)
    password: str = Field(..., max_length=255, min_length=8)

    # The account-creation checkbox: checked -> admin (passes everything), no
    # permissions needed. Unchecked -> a normal account holding exactly the
    # permission names listed (validated against the catalogue on save).
    is_admin: bool = False
    permissions: list[str] = Field(default_factory=list)

    # Whether the account can log in. Defaults to True so an account created
    # through the API is usable immediately — the column's own default is False,
    # which would otherwise make every new account fail login with "Account is
    # inactive". Deactivating is done by sending False here, or via
    # PUT /users/{id}/status.
    is_active: bool = True

    #--------------------------------
    # NOTIFICATION SETTINGS
    #
    # Defaults match the column defaults, so an older client that does not
    # send these fields leaves an account exactly as it was rather than
    # blanking it — the same reason is_active carries a default above.
    #
    # notification_tier is ADMIN-ONLY TO CHANGE. That is not enforced here —
    # a schema cannot see who is asking — but in
    # helpers.apply_notification_settings, which every write path goes
    # through. See the note there.
    #--------------------------------
    notification_tier: str = NotificationTier.OPERATIONAL.value

    phone_number: Optional[str] = None

    # Consent only. The TIMESTAMP that evidences it is set server-side and is
    # deliberately not accepted from the client — a caller must not be able to
    # backdate when somebody agreed to be messaged.
    whatsapp_opted_in: bool = False

    @field_validator("notification_tier")
    @classmethod
    def _known_tier(cls, value):
        if value not in _TIERS:
            raise ValueError(
                f"Unknown notification tier {value!r} — expected one of: "
                + ", ".join(sorted(_TIERS))
            )
        return value

    @field_validator("phone_number")
    @classmethod
    def _e164(cls, value):
        # Optional: an empty string from a cleared form field means "no
        # number", not "an invalid number", so it is normalised to NULL rather
        # than rejected.
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if not E164.match(value):
            raise ValueError(
                "Phone number must be in E.164 format — a leading '+' "
                "followed by digits only, e.g. +923001234567"
            )

        return value
