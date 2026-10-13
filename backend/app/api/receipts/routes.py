from fastapi import APIRouter, BackgroundTasks, Depends, Response, UploadFile, status

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.api.receipts.schemas import ConfirmBody, ReceiptOut, ReceiptSummaryOut
from app.application.receipts.dtos import UploadReceiptRequest

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ReceiptSummaryOut)
def upload(
    file: UploadFile,
    background: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> ReceiptSummaryOut:
    """Store the file and return straight away. The receipt is read in the background:
    poll `GET /receipts/{id}` until its status is `needs_review` or `failed`."""
    view = container.receipts.upload(
        user_id, UploadReceiptRequest(content=file.file.read(), content_type=file.content_type)
    )
    background.add_task(container.receipts.process, user_id, view.receipt.id)
    return ReceiptSummaryOut.from_receipt(view.receipt)


@router.post("/manual", status_code=status.HTTP_201_CREATED, response_model=ReceiptOut)
def create_manual(
    body: ConfirmBody,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> ReceiptOut:
    return ReceiptOut.from_view(container.receipts.create_manual(user_id, body.to_request()))


@router.get("", response_model=list[ReceiptSummaryOut])
def list_receipts(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> list[ReceiptSummaryOut]:
    return [ReceiptSummaryOut.from_receipt(receipt) for receipt in container.receipts.list_all(user_id)]


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> ReceiptOut:
    return ReceiptOut.from_view(container.receipts.get(user_id, receipt_id))


@router.post("/{receipt_id}/confirm", response_model=ReceiptOut)
def confirm(
    receipt_id: int,
    body: ConfirmBody,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> ReceiptOut:
    """Save the reviewed values. Also used to correct a receipt that is already confirmed."""
    return ReceiptOut.from_view(container.receipts.confirm(user_id, receipt_id, body.to_request()))


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    receipt_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    container.receipts.delete(user_id, receipt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
