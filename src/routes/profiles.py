import os
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import HttpUrl
from sqlalchemy import select
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config import get_jwt_auth_manager, get_s3_storage_client
from database import get_db, UserModel, UserProfileModel, UserGroupEnum, UserGroupModel
from exceptions import TokenExpiredError, BaseSecurityError, S3FileUploadError

from schemas.profiles import ProfileResponseSchema, ProfileRequestSchema
from security.http import get_token
from security.interfaces import JWTAuthManagerInterface
from storages import S3StorageInterface

router = APIRouter()


@router.post(
    "/users/{user_id}/profile/", response_model=ProfileResponseSchema, status_code=201
)
async def create_user_profile(
        user_id: int,
        db: AsyncSession = Depends(get_db),
        jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
        token: str = Depends(get_token),
        data: ProfileRequestSchema = Depends(ProfileRequestSchema.from_form),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    # робимо переврку токена на відповідність, ця перевірка зроблена у ф-ції get_token

    # token = get_token(request)
    #
    # if token is None:
    #     raise HTTPException(status_code=401, detail="Authorization header is missing")
    try:
        payload = jwt_manager.decode_access_token(token)
        current_user_id = payload.get("user_id")
    except BaseSecurityError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    # тут перевіряємо на термін придатності, він автоматично перевіриться при декодуванні
    # try:
    #     jwt_manager.verify_access_token_or_raise(token)
    # except TokenExpiredError:
    #     raise HTTPException(status_code=401, detail="Token has expired.")

    # витягуємо ID юзера, тобто того хто робить запит, з токена
    # decode_token = jwt_manager.decode_access_token(token)
    # current_user_id = decode_token.get("user_id")
    # if current_user_id is None:
    #     raise HTTPException(status_code=401, detail="Authorization header is missing")

    # і відповідно витягуємо його з БД
    # current_user_result = await db.execute(
    #     select(UserModel).where(UserModel.id == current_user_id)
    # )
    # current_user = current_user_result.scalars().first()
    # # перевіряємо чи це один і той же юзер і його дозвола
    # if not current_user:
    #     raise HTTPException(status_code=401, detail="User not found or not active.")

    # if current_user.id != user_id and not current_user.has_group(UserGroupEnum.USER):
    #     raise HTTPException(
    #         status_code=403, detail="You don't have permission to edit this profile."
    #     )

    if user_id != current_user_id:
        smt = (select(UserGroupModel)
               .join(UserModel)
               .where(UserModel.id == current_user_id)
               )
        result = await db.execute(smt)
        user_group = result.scalars().first()
        if not user_group or user_group.name == UserGroupEnum.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile."
            )

    # витягуємо з БД юзера для якого хочемо створити профіль, його ID ми маємо в ендпоїнті
    target_user_result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    target_user = target_user_result.scalars().first()

    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=401, detail="User not found or not active.")

    existing_profile = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    if existing_profile.scalars().first():
        raise HTTPException(status_code=400, detail="User already has a profile.")

    file_data = await data.avatar.read()
    # file_format = os.path.splitext(data.avatar.filename)[1]
    file_name = f"avatars/{user_id}_avatar"
    try:
        await s3_client.upload_file(file_name=file_name, file_data=file_data)
    except S3FileUploadError as e:
        print(f"Error uploading avatar to S3: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )
    # try:
    #     avatar = await s3_client.upload_file(
    #         file_name=file_name, file_data=file_data
    #     )
    #
    # except Exception:
    #     raise HTTPException(
    #         status_code=500, detail="Failed to upload avatar. Please try again later."
    #     )

    # avatar_url = await s3_client.get_file_url(file_name)

    new_user_profile = UserProfileModel(
        user_id=target_user.id,
        first_name=data.first_name,
        last_name=data.last_name,
        avatar=file_name,
        gender=data.gender,
        date_of_birth=data.date_of_birth,
        info=data.info,
    )

    db.add(new_user_profile)
    await db.commit()
    await db.refresh(new_user_profile)

    avatar_url = await s3_client.get_file_url(new_user_profile.avatar)

    return ProfileResponseSchema(
        id=new_user_profile.id,
        user_id=target_user.id,
        first_name=new_user_profile.first_name,
        last_name=new_user_profile.last_name,
        gender=new_user_profile.gender,
        date_of_birth=new_user_profile.date_of_birth,
        info=new_user_profile.info,
        avatar=cast(HttpUrl, avatar_url),
    )
