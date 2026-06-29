from typing import Dict

from pydantic import BaseModel


class SendTemplateRequest(BaseModel):
    template_id: str
    variables: Dict[str, str]