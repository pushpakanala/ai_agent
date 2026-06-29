from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.auth.dependencies import get_current_user

from app.template.models.template_model import (
    TemplateCreate,
)
from app.template.models.use_template_model import (
    UseTemplateRequest,
)

from app.email.services.openai_service import (
    generate_email,
)

from app.template.repositories.template_repository import (
    get_template_by_id_and_user,
)
from app.template.repositories.default_template_repository import (
    get_default_templates,
    get_default_template_by_id,
)

from app.template.models.default_template_request import (
    DefaultTemplateRequest,
)

from app.email.services.openai_service import (
    generate_email,
)

from app.template.repositories.template_repository import (
    create_template,
    get_templates,
    get_template_by_id,
    update_template,
    delete_template,
)


router = APIRouter(
    prefix="/templates",
    tags=["Templates"],
)


@router.post("")
async def add_template(
    req: TemplateCreate,
    email: str = Depends(get_current_user),
):

    template_id = await create_template(
        user_email=email,
        name=req.name,
        category=req.category,
        prompt_template=req.prompt_template,
    )

    return {
        "message": "Template created successfully",
        "id": template_id,
    }


@router.get("")
async def list_templates(
    email: str = Depends(get_current_user),
):

    result = await get_templates(email)

    return {
        "templates": result
    }


@router.put("/{template_id}")
async def edit_template(
    template_id: str,
    req: TemplateCreate,
    email: str = Depends(get_current_user),
):

    template = await get_template_by_id(
        template_id
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Template not found",
        )

    await update_template(
        template_id,
        req.name,
        req.category,
        req.prompt_template,
    )

    return {
        "message": "Template updated successfully"
    }


@router.delete("/{template_id}")
async def remove_template(
    template_id: str,
    email: str = Depends(get_current_user),
):

    template = await get_template_by_id(
        template_id
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Template not found",
        )

    await delete_template(template_id)

    return {
        "message": "Template deleted successfully"
    }

@router.post("/use")
async def use_template(
    req: UseTemplateRequest,
    email: str = Depends(get_current_user),
):

    template = await get_template_by_id_and_user(
        req.template_id,
        email,
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Template not found",
        )

    try:

        final_prompt = template[
            "prompt_template"
        ].format(**req.variables)

    except KeyError as e:

        raise HTTPException(
            status_code=400,
            detail=f"Missing variable: {e.args[0]}",
        )

    email_data = generate_email(
        final_prompt
    )

    return {
        "template_name": template["name"],
        "final_prompt": final_prompt,
        "generated_email": email_data,
    }

@router.get("/defaults")
async def list_default_templates():

    templates = await get_default_templates()

    return {
        "templates": templates
    }

@router.post("/defaults/{template_id}/use")
async def use_default_template(
    template_id: str,
    req: DefaultTemplateRequest,
):

    template = await get_default_template_by_id(
        template_id
    )

    if not template:

        raise HTTPException(
            status_code=404,
            detail="Template not found",
        )

    try:

        final_prompt = template[
            "prompt_template"
        ].format(**req.variables)

    except KeyError as e:

        raise HTTPException(
            status_code=400,
            detail=f"Missing variable: {e.args[0]}",
        )

    email_data = generate_email(
        final_prompt
    )

    return {
        "template": template["name"],
        "prompt": final_prompt,
        "generated_email": email_data,
    }