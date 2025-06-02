from datetime import date

from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, field_validator, HttpUrl

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date,
)


class ProfileRequestSchema(BaseModel):
    first_name: str
    last_name: str
    avatar: UploadFile
    gender: str
    date_of_birth: date
    info: str

    @classmethod
    def from_form(
            cls,
            first_name: str = Form(...),
            last_name: str = Form(...),
            avatar: UploadFile = File(...),
            gender: str = Form(...),
            date_of_birth: date = Form(...),
            info: str = Form(...),
    ):
        return cls(
            first_name=first_name,
            last_name=last_name,
            avatar=avatar,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
        )

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_string_fields(cls, field: str):
        validate_name(field)
        return field.lower()

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, avatar: UploadFile):
        try:
            validate_image(avatar)
            return avatar
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @field_validator("gender")
    @classmethod
    def validate_gender_field(cls, gender: str):
        validate_gender(gender)
        return gender

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth_field(cls, date_of_birth: date):
        validate_birth_date(date_of_birth)
        return date_of_birth

    @field_validator("info")
    def validate_info(cls, info: str):
        if not info or not info.strip():
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return info


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    avatar: str
    gender: str
    date_of_birth: date
    info: str
