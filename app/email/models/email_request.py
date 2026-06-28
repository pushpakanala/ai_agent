from pydantic import BaseModel


class EmailRequest(BaseModel):
    prompt: str