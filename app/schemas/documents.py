import unicodedata
from pydantic import BaseModel, Field, field_validator


class RenameDocumentRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name", mode="before")
    @classmethod
    def clean_display_name(cls, value):
        if isinstance(value, str):
            return "".join(char for char in value if unicodedata.category(char) not in {"Cc", "Cf"}).strip()
        return value
