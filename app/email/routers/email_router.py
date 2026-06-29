from fastapi import APIRouter, HTTPException, Depends

from app.auth.dependencies import get_current_user
from app.auth.repositories.user_repository import get_user

from app.email.repositories.contact_repository import (
    get_contact_by_name,
)

from app.email.models.email_request import EmailRequest
from app.email.models.search_request import SearchRequest

from app.email.services.openai_service import (
    generate_email,
    generate_gmail_query,
)

from app.email.services.mcp_client import (
    send_email_via_mcp,
    list_sent_via_mcp,
    search_emails_via_mcp,
)

from app.email.repositories.email_history_repository import (
    save_email_history,
    get_email_history,
)

from app.email.models.send_template_request import (
    SendTemplateRequest,
)

from app.template.repositories.template_repository import (
    get_template_by_id_and_user,
)

router = APIRouter(
    prefix="/email",
    tags=["Email"],
)


# ==================================================
# Send Email
# ==================================================
@router.post("/send")
async def send_email(
    req: EmailRequest,
    email: str = Depends(get_current_user),
):

    user = await get_user(email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    # Generate email using OpenAI
    email_data = generate_email(req.prompt)

    recipient = email_data.get(
        "to_email",
        "",
    ).strip()

    # ---------------------------------------------
    # If recipient is NOT an actual email,
    # treat it as a saved contact
    # ---------------------------------------------
    if "@" not in recipient:

        contact = await get_contact_by_name(
            user_email=email,
            name=recipient,
        )

        if not contact:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Contact '{recipient}' not found. "
                    "Please add it first."
                ),
            )

        email_data["to_email"] = contact["email"]

    # Send via Gmail MCP
    result = await send_email_via_mcp(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
        to_email=email_data["to_email"],
        subject=email_data["subject"],
        body=email_data["body"],
    )

    # Extract Gmail message ID
    gmail_message_id = ""

    if isinstance(result, dict):
        gmail_message_id = result.get(
            "id",
            "",
        )

    # Save history
    await save_email_history(
        user_email=email,
        prompt=req.prompt,
        to_email=email_data["to_email"],
        subject=email_data["subject"],
        body=email_data["body"],
        gmail_message_id=gmail_message_id,
    )

    return {
        "generated_email": email_data,
        "mcp_response": result,
    }


# ==================================================
# List Sent Emails
# ==================================================
@router.get("/sent")
async def get_sent_emails(
    email: str = Depends(get_current_user),
):

    user = await get_user(email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    result = await list_sent_via_mcp(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
    )

    return {
        "emails": result,
    }


# ==================================================
# Email History (MongoDB)
# ==================================================
@router.get("/history")
async def history(
    email: str = Depends(get_current_user),
):

    result = await get_email_history(email)

    return {
        "history": result,
    }


# ==================================================
# Natural Language Gmail Search
# ==================================================
@router.post("/search")
async def search_emails(
    req: SearchRequest,
    email: str = Depends(get_current_user),
):

    user = await get_user(email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    # Convert English -> Gmail Query
    gmail_query = generate_gmail_query(
        req.query
    )

    result = await search_emails_via_mcp(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
        query=gmail_query,
    )

    return {
        "original_query": req.query,
        "gmail_query": gmail_query,
        "results": result,
    }

@router.post("/send-template")
async def send_template_email(
    req: SendTemplateRequest,
    email: str = Depends(get_current_user),
):

    # Get logged-in user
    user = await get_user(email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    # Get template
    template = await get_template_by_id_and_user(
        req.template_id,
        email,
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Template not found",
        )

    # Replace variables
    try:

        final_prompt = template[
            "prompt_template"
        ].format(**req.variables)

    except KeyError as e:

        raise HTTPException(
            status_code=400,
            detail=f"Missing variable: {e.args[0]}",
        )

    # Generate email
    email_data = generate_email(
        final_prompt
    )

    # Resolve contacts
    recipient = email_data.get(
        "to_email",
        "",
    ).strip()

    if "@" not in recipient and recipient:

        contact = await get_contact_by_name(
            user_email=email,
            name=recipient,
        )

        if not contact:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Contact '{recipient}' "
                    "not found."
                ),
            )

        email_data["to_email"] = contact["email"]

    # Send email
    result = await send_email_via_mcp(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
        to_email=email_data["to_email"],
        subject=email_data["subject"],
        body=email_data["body"],
    )

    gmail_message_id = ""

    if isinstance(result, dict):
        gmail_message_id = result.get(
            "id",
            "",
        )

    # Save history
    await save_email_history(
        user_email=email,
        prompt=final_prompt,
        to_email=email_data["to_email"],
        subject=email_data["subject"],
        body=email_data["body"],
        gmail_message_id=gmail_message_id,
    )

    return {
        "template": template["name"],
        "final_prompt": final_prompt,
        "generated_email": email_data,
        "mcp_response": result,
    }