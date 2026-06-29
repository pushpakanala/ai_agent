from typing import Dict

from pydantic import BaseModel


class DefaultTemplateRequest(BaseModel):
    variables: Dict[str, str]