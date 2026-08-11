from sqlalchemy import select
from sqlalchemy.orm import Session

from db.full_model import ConversationORM, MessageORM


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
