from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

from app.email.models.contact import ContactRequest
from app.email.repositories.contact_repository import (
    add_contact,
    get_contacts,
    delete_contact,
)


router = APIRouter(
    prefix="/contacts",
    tags=["Contacts"],
)


@router.post("")
async def create_contact(
    req: ContactRequest,
    email: str = Depends(get_current_user),
):

    await add_contact(
        user_email=email,
        name=req.name,
        contact_email=req.email,
    )

    return {
        "message": "Contact saved successfully"
    }


@router.get("")
async def list_contacts(
    email: str = Depends(get_current_user),
):

    contacts = await get_contacts(email)

    return {
        "contacts": contacts
    }


@router.delete("/{name}")
async def remove_contact(
    name: str,
    email: str = Depends(get_current_user),
):

    await delete_contact(
        user_email=email,
        name=name,
    )

    return {
        "message": "Contact deleted"
    }