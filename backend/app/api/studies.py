"""路由薄层:只做参数校验与调用 service。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.study import StudyCreate, StudyOut, StudyUpdate
from app.services import studies

router = APIRouter(prefix="/api/studies", tags=["studies"])


@router.post("", response_model=StudyOut, status_code=status.HTTP_201_CREATED)
def create_study(data: StudyCreate, db: Session = Depends(get_db)) -> StudyOut:
    return StudyOut.model_validate(studies.create_study(db, data))


@router.get("", response_model=list[StudyOut])
def list_studies(
    include_archived: bool = False, db: Session = Depends(get_db)
) -> list[StudyOut]:
    return [StudyOut.model_validate(s) for s in studies.list_studies(db, include_archived)]


@router.get("/{study_id}", response_model=StudyOut)
def get_study(study_id: int, db: Session = Depends(get_db)) -> StudyOut:
    study = studies.get_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="study not found")
    return StudyOut.model_validate(study)


@router.patch("/{study_id}", response_model=StudyOut)
def update_study(study_id: int, data: StudyUpdate, db: Session = Depends(get_db)) -> StudyOut:
    study = studies.get_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="study not found")
    return StudyOut.model_validate(studies.update_study(db, study, data))


@router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study(study_id: int, db: Session = Depends(get_db)) -> None:
    study = studies.get_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="study not found")
    studies.delete_study(db, study)
