from typing import Optional

from pydantic import BaseModel, Field


#-----------------------------------------------------
# SAVED-REPORT REQUEST BODY
#
# The recipe the front end saves: a name, the data types it spans, the columns
# to show, and the filter values (no date range). `filters` is a free-form dict
# so a new filter key never needs a schema change here — the report builder only
# reads the keys it knows.
#-----------------------------------------------------

class SavedReportSchema(BaseModel):
    name: str
    types: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
