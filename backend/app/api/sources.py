"""资料路由(M1-02/05/06)。"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.source import SourceDetail, SourceOut
from app.services import sources as sources_svc
from app.services import studies as studies_svc

router = APIRouter(prefix="/api", tags=["sources"])


@router.post(
    "/studies/{study_id}/sources",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    study_id: int,
    file: UploadFile,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if studies_svc.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    data = await file.read()
    try:
        source = sources_svc.save_upload(db, study_id, file.filename or "untitled", data)
    except ValueError as err:
        raise HTTPException(status_code=415, detail=str(err)) from err
    sources_svc.schedule_parse(background, source.id)
    return SourceOut.model_validate(source)


@router.get("/studies/{study_id}/sources", response_model=list[SourceOut])
def list_sources(study_id: int, db: Session = Depends(get_db)):
    return [
        SourceOut.model_validate(s)
        for s in sources_svc.list_study_sources(db, study_id)
    ]


@router.get("/sources/{source_id}", response_model=SourceDetail)
def get_source(source_id: int, db: Session = Depends(get_db)):
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return sources_svc.get_source_detail(db, source)


@router.post("/sources/{source_id}/reparse", response_model=SourceOut)
def reparse_source(
    source_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
):
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return SourceOut.model_validate(sources_svc.reparse_source(db, background, source))
