from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base model that serializes to camelCase for the Angular client."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Book(ApiModel):
    book_id: str = Field(..., description="Stable id, e.g. 'gibbon-vol1'")
    title: str
    author: str
    year: int | None = None
    page_count: int = Field(..., ge=0)
    gcs_uri: str
