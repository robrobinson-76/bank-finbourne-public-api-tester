from __future__ import annotations
from fastapi import APIRouter, Request, Response, UploadFile, File, Form, HTTPException

from lusid_mock.services import drive_service

router = APIRouter(prefix="/drive/api/files", tags=["drive"])


@router.post("", status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
):
    content = await file.read()
    result = await drive_service.upload_file(
        store=request.app.state.drive_store,
        config=request.app.state.config,
        path=path,
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    return result


@router.get("/{file_id}/contents")
async def get_file_contents(file_id: str, request: Request):
    result = drive_service.get_file_contents(request.app.state.drive_store, file_id)
    if result == 404:
        raise HTTPException(status_code=404, detail="File not found")
    if result == 423:
        raise HTTPException(status_code=423, detail="File is being scanned — retry shortly")
    if result == 410:
        raise HTTPException(status_code=410, detail="File permanently unavailable (malware detected)")
    content_type, content = result
    return Response(content=content, media_type=content_type)


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: str, request: Request):
    deleted = drive_service.delete_file(request.app.state.drive_store, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
