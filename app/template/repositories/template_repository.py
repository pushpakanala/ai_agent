from datetime import datetime
from bson import ObjectId

from app.common.db import db


async def create_template(
    user_email: str,
    name: str,
    category: str,
    prompt_template: str,
):

    templates = db.db["templates"]

    result = templates.insert_one(
        {
            "user_email": user_email,
            "name": name,
            "category": category,
            "prompt_template": prompt_template,
            "created_at": datetime.utcnow(),
        }
    )

    return str(result.inserted_id)


async def get_templates(user_email: str):

    templates = db.db["templates"]

    result = list(
        templates.find(
            {"user_email": user_email},
            {"user_email": 0},
        )
    )

    for item in result:
        item["id"] = str(item.pop("_id"))

    return result


async def get_template_by_id(template_id: str):

    templates = db.db["templates"]

    result = templates.find_one(
        {"_id": ObjectId(template_id)}
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result


async def update_template(
    template_id: str,
    name: str,
    category: str,
    prompt_template: str,
):

    templates = db.db["templates"]

    templates.update_one(
        {"_id": ObjectId(template_id)},
        {
            "$set": {
                "name": name,
                "category": category,
                "prompt_template": prompt_template,
            }
        },
    )


async def delete_template(template_id: str):

    templates = db.db["templates"]

    templates.delete_one(
        {"_id": ObjectId(template_id)}
    )

async def get_template_by_id_and_user(
    template_id: str,
    user_email: str,
):

    templates = db.db["templates"]

    result = templates.find_one(
        {
            "_id": ObjectId(template_id),
            "user_email": user_email,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result