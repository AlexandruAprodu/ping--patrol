import httpx
from fastapi import Request

from common.constants import USERS_BASE_URL


async def verify_auth_user_middleware(request: Request):
    async with httpx.AsyncClient() as client:
        headers = request.headers
        access_token = headers.get('access_token')
        response = await client.get(
            USERS_BASE_URL + "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    user = response.json()
    return user
