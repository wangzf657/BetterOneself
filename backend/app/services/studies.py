"""学习项目 CRUD(M1-01):创建、列表、归档、删除。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Study
from app.schemas.study import StudyCreate, StudyUpdate


def create_study(db: Session, data: StudyCreate) -> Study:
    study = Study(name=data.name, goal=data.goal)
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def list_studies(db: Session, include_archived: bool = False) -> Sequence[Study]:
    stmt = select(Study).order_by(Study.updated_at.desc())
    if not include_archived:
        stmt = stmt.where(Study.status != "archived")
    return list(db.scalars(stmt))


def get_study(db: Session, study_id: int) -> Study | None:
    return db.get(Study, study_id)


def update_study(db: Session, study: Study, data: StudyUpdate) -> Study:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(study, field, value)
    db.commit()
    db.refresh(study)
    return study


def delete_study(db: Session, study: Study) -> None:
    # 子表 FK 均 ondelete=CASCADE,关联数据随删(删除前由前端确认交互提示)
    db.delete(study)
    db.commit()
