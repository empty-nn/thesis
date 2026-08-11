from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.full_model import ConversationORM, MessageORM
from schemas.chat import ConversationDetail, ConversationSummary, SavedMessage


def list_user_conversations(
    db: Session,
    user_id: str,
) -> list[ConversationSummary]:
    items = db.scalars(
        select(ConversationORM)
        .where(ConversationORM.user_id == user_id)
        .order_by(ConversationORM.updated_at.desc())
        .limit(50)
    ).all()
    return [
        ConversationSummary(
            id=item.id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


def get_user_conversation(
    db: Session,
    user_id: str,
    conversation_id: str,
) -> ConversationDetail | None:
    conversation = db.scalar(
        select(ConversationORM).where(
            ConversationORM.id == conversation_id,
            ConversationORM.user_id == user_id,
        )
    )
    if conversation is None:
        return None
    messages = db.scalars(
        select(MessageORM)
        .where(MessageORM.conversation_id == conversation.id)
        .order_by(MessageORM.created_at.asc(), MessageORM.id.asc())
    ).all()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        messages=[
            SavedMessage(
                id=item.id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
            )
            for item in messages
        ],
    )


def save_chat_exchange(
    db: Session,
    user_id: str,
    user_message: str,
    assistant_message: str,
    conversation_id: str | None = None,
) -> str:
    conversation = None
    if conversation_id:
        conversation = db.scalar(
            select(ConversationORM).where(
                ConversationORM.id == conversation_id,
                ConversationORM.user_id == user_id,
            )
        )
    if conversation is None:
        conversation = ConversationORM(
            user_id=user_id,
            title=user_message[:120],
        )
        db.add(conversation)
        db.flush()
    else:
        conversation.updated_at = datetime.utcnow()
    db.add_all(
        [
            MessageORM(
                conversation_id=conversation.id,
                role="user",
                content=user_message,
            ),
            MessageORM(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
            ),
        ]
    )
    db.commit()
    return conversation.id
