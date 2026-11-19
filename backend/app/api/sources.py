"""资料路由(M1-02/05/06/07)。"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
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


class TextImportIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)


@router.post(
    "/studies/{study_id}/sources/text",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
)
def import_text(
    study_id: int, data: TextImportIn, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """纯文本粘贴建为资料(M1-07),可参与拆解。"""
    if studies_svc.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    source = sources_svc.save_text(db, study_id, data.title, data.content)
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


class SourceRename(BaseModel):
    title: str = Field(min_length=1, max_length=300)


@router.patch("/sources/{source_id}", response_model=SourceOut)
def rename_source(source_id: int, data: SourceRename, db: Session = Depends(get_db)):
    """重命名(M1-05)。"""
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    source.title = data.title
    db.commit()
    db.refresh(source)
    return SourceOut.model_validate(source)


@router.get("/sources/{source_id}/impact")
def source_impact(source_id: int, db: Session = Depends(get_db)):
    """删除前的影响预览(M1-05:派生内容处理提示)。"""
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return sources_svc.delete_impact(db, source)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """删除资料:级联清理切片/引用,孤立知识点保留(前端已展示 impact 确认)。"""
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    sources_svc.delete_source(db, source)


@router.post("/sources/{source_id}/reparse", response_model=SourceOut)
def reparse_source(
    source_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
):
    source = sources_svc.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return SourceOut.model_validate(sources_svc.reparse_source(db, background, source))
