from typing import Dict

from pydantic import BaseModel


class UseTemplateRequest(BaseModel):
    template_id: str
    variables: Dict[str, str]