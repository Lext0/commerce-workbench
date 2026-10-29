from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80, strict=True)
    revision: int = Field(ge=1, strict=True)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Name cannot contain control characters")
        return value
