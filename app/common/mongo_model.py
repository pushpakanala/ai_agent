from pydantic import BaseModel, Field
from bson import ObjectId
from pydantic.functional_validators import BeforeValidator
from typing import Annotated, Optional, List


class MongoIDModel(BaseModel):
    id: Annotated[str, BeforeValidator(str)] = Field(alias="_id")


class UpsertedID(BaseModel):
    upserted_id: Optional[Annotated[str, BeforeValidator(str)]]


class UpsertResponse(UpsertedID):
    modified_count: Optional[int]
    matched_count: Optional[int]
    sucess: bool
    updated: Optional[bool]
    inserted: Optional[bool]
