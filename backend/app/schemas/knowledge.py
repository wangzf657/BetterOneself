"""知识点 API 契约(M2-01)。"""

from typing import Literal

from pydantic import BaseModel

KpType = Literal["concept", "fact", "procedure"]
MasteryStatus = Literal["new", "learning", "passed", "weak"]


class KpRef(BaseModel):
    chunk_id: int
    source_id: int
    heading_path: str


class KpNode(BaseModel):
    id: int
    name: str
    summary: str
    kp_type: KpType
    ai_inferred: bool
    mastery_status: MasteryStatus
    self_reported: str
    refs: list[KpRef]
    children: list["KpNode"]
