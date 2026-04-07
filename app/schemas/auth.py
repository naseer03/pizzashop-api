from pydantic import BaseModel, EmailStr, Field


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str
