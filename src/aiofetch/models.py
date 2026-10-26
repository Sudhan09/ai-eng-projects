from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Item(Strict):
    id: int = Field(ge=0)
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0, alias="priceCents")

    @field_validator("name")
    @classmethod
    def tidy_name(cls, name: str) -> str:
        return " ".join(name.split())


class ItemFound(Strict):
    status: Literal["ok"]
    item: Item


class ItemMissing(Strict):
    status: Literal["not_found"]
    id: int


class ApiError(Strict):
    status: Literal["error"]
    code: str
    message: str


class ItemMoved(Strict):
    status: Literal["moved"]
    id: int
    moved_to: int = Field(alias="movedTo")


class PageRequest(Strict):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, gt=0, le=500, alias="pageSize")
    max_tokens: int | None = Field(default=None, gt=0, alias="maxTokens")

    @model_validator(mode="after")
    def tokens_fit_the_page(self) -> Self:
        if self.max_tokens is not None and self.max_tokens < self.page_size:
            raise ValueError("maxTokens must be at least pageSize")
        return self

    def params(self) -> dict[str, str]:
        values = self.model_dump(by_alias=True, exclude_none=True)
        result = {}
        for name, value in values.items():
            result[name] = str(value)
        return result


ItemResponse = Annotated[
    ItemFound | ItemMissing | ApiError | ItemMoved, Field(discriminator="status")
]
ITEM_RESPONSE: TypeAdapter[ItemResponse] = TypeAdapter(ItemResponse)
