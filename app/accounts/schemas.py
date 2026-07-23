from pydantic import BaseModel, Field

class UserSchema(BaseModel):
    username: str = Field(..., max_length=255, min_length=8)
    password: str = Field(..., max_length=255, min_length=8)
    role:int