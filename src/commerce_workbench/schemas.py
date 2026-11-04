from pydantic import BaseModel, ConfigDict, Field, field_validator
import unicodedata


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


class ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, strict=True)
    model: str = Field(min_length=1, max_length=64, strict=True)
    category: str = Field(default="", max_length=80, strict=True)
    description: str = Field(default="", max_length=4000, strict=True)
    price_cents: int | None = Field(default=None, ge=0, le=999999999, strict=True)

    @field_validator("name", "model", "category", mode="before")
    @classmethod
    def clean_short_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(unicodedata.category(char).startswith("C") for char in value):
                raise ValueError("Text cannot contain control characters")
        return value

    @field_validator("model", mode="after")
    @classmethod
    def normalize_model(cls, value):
        value = unicodedata.normalize("NFKC", value).strip()
        if not 1 <= len(value) <= 64:
            raise ValueError("Model must contain 1 to 64 characters")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value):
        if isinstance(value, str):
            value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
            if any(unicodedata.category(char).startswith("C") and char not in "\n\t" for char in value):
                raise ValueError("Description contains control characters")
        return value


class ProductUpdate(ProductFields):
    revision: int = Field(ge=1, strict=True)


class ProductRead(ProductFields):
    id: int
    created_at: str
    updated_at: str
    revision: int


class ProductList(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
