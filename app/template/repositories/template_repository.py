from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId

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

    try:
        object_id = ObjectId(template_id)

    except InvalidId:
        return None

    templates = db.db["templates"]

    result = templates.find_one(
        {"_id": object_id}
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

    try:
        object_id = ObjectId(template_id)

    except InvalidId:
        return False

    templates = db.db["templates"]

    templates.update_one(
        {"_id": object_id},
        {
            "$set": {
                "name": name,
                "category": category,
                "prompt_template": prompt_template,
            }
        },
    )

    return True


async def delete_template(template_id: str):

    try:
        object_id = ObjectId(template_id)

    except InvalidId:
        return False

    templates = db.db["templates"]

    templates.delete_one(
        {"_id": object_id}
    )

    return True


async def get_template_by_id_and_user(
    template_id: str,
    user_email: str,
):

    # Default template IDs like:
    # meeting_request
    # work_from_home
    # are NOT Mongo ObjectIds
    try:
        object_id = ObjectId(template_id)

    except InvalidId:
        return None

    templates = db.db["templates"]

    result = templates.find_one(
        {
            "_id": object_id,
            "user_email": user_email,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result