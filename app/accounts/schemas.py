from pydantic import BaseModel, Field


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
