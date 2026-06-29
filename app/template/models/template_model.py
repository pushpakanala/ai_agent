from pydantic import BaseModel


class TemplateCreate(BaseModel):
    name: str
    category: str
    prompt_template: str