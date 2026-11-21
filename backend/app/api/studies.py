"""学习项目与导入 API（B1、接口设计 §2）。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import (
    DeleteImpact,
    PipelineProgress,
    StudyDetail,
    StudyItem,
    StudyPatch,
)
from app.services import pipeline
from app.services import studies as studies_service

router = APIRouter(tags=["studies"])
sources_router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", status_code=201, response_model=StudyDetail, responses={200: {"model": StudyDetail}})
async def create_study(
    background: BackgroundTasks,
    name: str = Form(...),
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> object:
    content = await file.read()
    study, created = studies_service.create_study(
        db, name=name, filename=file.filename or "book", content=content,
        idempotency_key=idempotency_key,
    )
    if created and study.primary_source_id is not None:
        background.add_task(pipeline.run_parse, study.primary_source_id, defer_followups=True)
    detail = studies_service.get_study(db, study.id)
    return detail


@router.get("", response_model=list[StudyItem])
def list_studies(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return studies_service.list_studies(db)


@router.get("/{study_id}", response_model=StudyDetail)
def get_study(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return studies_service.get_study(db, study_id)


@router.patch("/{study_id}", response_model=StudyDetail)
def patch_study(
    study_id: int, body: StudyPatch, db: Session = Depends(get_db)
) -> dict[str, object]:
    studies_service.patch_study(db, study_id, name=body.name, scheme=body.scheme)
    return studies_service.get_study(db, study_id)


@router.get("/{study_id}/delete-impact", response_model=DeleteImpact)
def delete_impact(study_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    return studies_service.delete_impact(db, study_id)


@router.delete("/{study_id}", status_code=204)
def delete_study(study_id: int, db: Session = Depends(get_db)) -> None:
    studies_service.delete_study(db, study_id)


@router.post("/{study_id}/source/replace", response_model=StudyDetail)
async def replace_source(
    study_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    content = await file.read()
    source = studies_service.replace_source(
        db, study_id, filename=file.filename or "book", content=content
    )
    background.add_task(pipeline.run_parse, source.id, defer_followups=True)
    return studies_service.get_study(db, study_id)


@router.get("/{study_id}/progress", response_model=PipelineProgress)
def study_progress(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return pipeline.pipeline_progress(db, study_id)


@sources_router.post("/{source_id}/reparse", status_code=202)
def reparse_source(
    source_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
) -> dict[str, str]:
    pipeline.reparse(db, source_id)
    background.add_task(pipeline.run_parse, source_id, defer_followups=True)
    return {"status": "reparse_started"}


@sources_router.post("/{source_id}/reembed", status_code=202)
def reembed_source(source_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    pipeline.reembed(db, source_id)
    return {"status": "reembed_started"}
