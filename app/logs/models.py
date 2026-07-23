from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Only used in the quoted "User" annotation, which SQLAlchemy
# resolves from its registry. Imported for the type checker
# only, the same way the other models reference each other.
if TYPE_CHECKING:
    from app.accounts.models import User

#-----------------------------------------------------
# ACTIVITY LOG TABLE
#
# One row every time a user does something that changes
# data, plus a row for each login and logout. This is what
# the admin's live log screen reads from, and it stays in
# the database so the history is still there after the page
# is closed.
#
# The username is copied onto the row as well as the user
# id, so an old log still reads properly even if the user is
# renamed later.
#-----------------------------------------------------

class ActivityLog(Base, TimestampMixin):
    __tablename__ = "activity_logs"

    id : Mapped[int] = mapped_column(primary_key = True)

    user_id : Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete = "SET NULL"),
        nullable = True,
        index = True
    )

    # Copied in so the log reads even if the user is renamed
    username : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    # One of the words from the LogAction list: Login, Create,
    # Update, Delete, Revert and so on.
    action : Mapped[str] = mapped_column(
        String(50),
        nullable = False
    )

    method : Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable = True
    )

    path : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    # What was acted on, pulled off the path, e.g. consignment
    # number 12. Both are optional because a login has neither.
    entity_type : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    entity_id : Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable = True
    )

    status_code : Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable = True
    )

    detail : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    user : Mapped[Optional["User"]] = relationship()
