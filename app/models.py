from typing import Literal
from pydantic import BaseModel, Field, field_validator


class QueryInput(BaseModel):
    keyword: str = Field(min_length=2, max_length=80)
    region: str = Field(default='江西', max_length=40)
    freshness: Literal['', 'y1', 'y2', 'y3', 'm6'] = 'y2'
    site: Literal['', 'ccgp.gov.cn', 'jxsggzy.cn'] = ''
    target: int = Field(default=3, ge=1, le=10)
    mode: Literal['live', 'demo'] = 'live'
    expand_search: bool = True

    @field_validator('keyword', 'region', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value
