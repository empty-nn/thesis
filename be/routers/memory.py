from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.full_model import UserMemoryORM
from db.session import get_db
from schemas.memory import UserMemoryItem
from services.session_auth import require_session_user_id


router = APIRouter(tags=["memory"])


@router.get("/memories", response_model=list[UserMemoryItem])
def list_memories(
    request: Request,
    db: Session = Depends(get_db),
) -> list[UserMemoryItem]:
    user_id = require_session_user_id(request)
    items = db.scalars(
        select(UserMemoryORM)
        .where(
            UserMemoryORM.user_id == user_id,
            UserMemoryORM.is_active.is_(True),
        )
        .order_by(
            UserMemoryORM.importance.desc(),
            UserMemoryORM.updated_at.desc(),
        )
    ).all()
    return [
        UserMemoryItem(
            id=item.id,
            memory_type=item.memory_type,
            content=item.content,
            importance=item.importance or 0,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user_id = require_session_user_id(request)
    memory = db.scalar(
        select(UserMemoryORM).where(
            UserMemoryORM.id == memory_id,
            UserMemoryORM.user_id == user_id,
            UserMemoryORM.is_active.is_(True),
        )
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.is_active = False
    db.commit()
    return Response(status_code=204)
