from app.template.data.default_templates import (
    DEFAULT_TEMPLATES,
)


async def get_default_templates():

    return DEFAULT_TEMPLATES


async def get_default_template_by_id(
    template_id: str,
):

    for template in DEFAULT_TEMPLATES:

        if template["id"] == template_id:
            return template

    return None