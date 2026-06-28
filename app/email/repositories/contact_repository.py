from app.common.db import db


async def add_contact(
    user_email: str,
    name: str,
    contact_email: str,
):
    contacts = db.db["contacts"]

    return contacts.update_one(
        {
            "user_email": user_email,
            "name": name.lower(),
        },
        {
            "$set": {
                "name": name.lower(),
                "email": contact_email,
            }
        },
        upsert=True,
    )


async def get_contacts(user_email: str):

    contacts = db.db["contacts"]

    return list(
        contacts.find(
            {"user_email": user_email},
            {"_id": 0},
        )
    )


async def get_contact_by_name(
    user_email: str,
    name: str,
):

    contacts = db.db["contacts"]

    return contacts.find_one(
        {
            "user_email": user_email,
            "name": name.lower(),
        },
        {"_id": 0},
    )


async def get_contact_by_email(
    user_email: str,
    contact_email: str,
):

    contacts = db.db["contacts"]

    return contacts.find_one(
        {
            "user_email": user_email,
            "email": contact_email,
        },
        {"_id": 0},
    )


async def delete_contact(
    user_email: str,
    name: str,
):

    contacts = db.db["contacts"]

    return contacts.delete_one(
        {
            "user_email": user_email,
            "name": name.lower(),
        }
    )