from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc
from typing import Optional
import json
import asyncio
import uuid

from app.db.database import get_session
from app.db.models import Chat, Message
from app.schemas import MessageCreate, ChatResponse, MessageResponse, ChatWithMessages, ChatRename
from app.auth import get_current_user
from app.graph import create_agent_graph
from app.llm_provider import llm_provider

router = APIRouter(prefix="/chat", tags=["Chat"])

# Initialize agent graph
agent_graph = create_agent_graph()


def set_user_api_keys(
    x_openai_key: Optional[str] = Header(None),
    x_openai_model: Optional[str] = Header(None),
    x_gemini_key: Optional[str] = Header(None),
    x_gemini_model: Optional[str] = Header(None),
    x_ollama_url: Optional[str] = Header(None),
    x_ollama_model: Optional[str] = Header(None),
    x_deepseek_key: Optional[str] = Header(None),
    x_deepseek_model: Optional[str] = Header(None)
):
    """Extract and set API keys and models from request headers."""
    llm_provider.set_api_keys(
        openai_key=x_openai_key,
        openai_model=x_openai_model,
        gemini_key=x_gemini_key,
        gemini_model=x_gemini_model,
        ollama_url=x_ollama_url,
        ollama_model=x_ollama_model,
        deepseek_key=x_deepseek_key,
        deepseek_model=x_deepseek_model
    )


@router.post("/message")
async def send_message_public(
    message_data: MessageCreate,
    session: AsyncSession = Depends(get_session),
    api_keys: None = Depends(set_user_api_keys)
):
    """Send a message without authentication (for testing)."""
    
    # Use a default user or create anonymous chat
    # For simplicity, we'll just use the agent without saving to DB
    thread_id = message_data.chat_id if message_data.chat_id else "anonymous-chat"
    thread_config = {"configurable": {"thread_id": thread_id}}
    
    # Invoke agent graph
    try:
        result = await agent_graph.ainvoke(
            {"messages": [("user", message_data.message)]},
            config=thread_config
        )
        
        # Extract answer from last message
        final_message = result["messages"][-1]
        content = final_message.content
        
        # Ensure content is a string (LangChain can return list of content blocks)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and 'text' in block:
                    text_parts.append(block['text'])
            answer = '\n'.join(text_parts) if text_parts else str(content)
        else:
            answer = str(content) if content else ""
        
        return {
            "success": True,
            "chat_id": thread_id,
            "message": answer,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )


@router.post("/prompt_public")
async def send_message_prompt_public(
    message_data: MessageCreate,
    session: AsyncSession = Depends(get_session),
    api_keys: None = Depends(set_user_api_keys),
):
    """Alias to the public message endpoint for compatibility with older frontends."""
    # Delegate to the public handler
    return await send_message_public(message_data, session)


@router.get("/", response_model=list[ChatResponse])
async def get_user_chats(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    """Get chats for the authenticated user with pagination."""
    
    result = await session.execute(
        select(Chat)
        .where(Chat.user_id == uuid.UUID(current_user["user_id"]))
        .where(Chat.archived_at.is_(None))
        .order_by(Chat.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    chats = result.scalars().all()
    
    return [ChatResponse.model_validate(chat) for chat in chats]


@router.post("/prompt")
async def send_message(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    api_keys: None = Depends(set_user_api_keys)
):
    """Send a message and get response (non-streaming)."""
    
    # Get or create chat
    if message_data.chat_id:
        result = await session.execute(
            select(Chat).where(
                Chat.id == message_data.chat_id,
                Chat.user_id == uuid.UUID(current_user["user_id"]),
                Chat.archived_at.is_(None)
            )
        )
        chat = result.scalar_one_or_none()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
    else:
        # Create new chat with auto-generated title from first message
        title = message_data.message.strip()[:50]
        if len(message_data.message.strip()) > 50:
            title += "..."
        chat = Chat(user_id=uuid.UUID(current_user["user_id"]), title=title)
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
    
    # Prepare thread config for conversation memory
    thread_config = {"configurable": {"thread_id": str(chat.id)}}
    
    # Invoke agent graph
    try:
        result = await agent_graph.ainvoke(
            {"messages": [("user", message_data.message)]},
            config=thread_config
        )
        
        # Extract answer from last message
        final_message = result["messages"][-1]
        content = final_message.content
        
        # Ensure content is a string (LangChain can return list of content blocks)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and 'text' in block:
                    text_parts.append(block['text'])
            answer = '\n'.join(text_parts) if text_parts else str(content)
        else:
            answer = str(content) if content else ""
        
        # Save message to database
        new_message = Message(
            chat_id=chat.id,
            human=message_data.message,
            bot=answer,
        )
        session.add(new_message)
        await session.commit()
        
        return {
            "success": True,
            "chat_id": str(chat.id),
            "message": answer,
        }
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )


@router.post("/prompt/stream")
async def send_message_stream(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    api_keys: None = Depends(set_user_api_keys)
):
    """Send a message and get streaming response."""
    
    # Get or create chat
    if message_data.chat_id:
        result = await session.execute(
            select(Chat).where(
                Chat.id == message_data.chat_id,
                Chat.user_id == uuid.UUID(current_user["user_id"]),
                Chat.archived_at.is_(None)
            )
        )
        chat = result.scalar_one_or_none()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
    else:
        # Create new chat with auto-generated title from first message
        title = message_data.message.strip()[:50]
        if len(message_data.message.strip()) > 50:
            title += "..."
        chat = Chat(user_id=uuid.UUID(current_user["user_id"]), title=title)
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
    
    chat_id = str(chat.id)
    thread_config = {"configurable": {"thread_id": chat_id}}
    
    async def stream_response():
        """Generator for streaming responses."""
        accumulated_answer = ""
        
        try:
            # Stream from agent graph
            async for event in agent_graph.astream_events(
                {"messages": [("user", message_data.message)]},
                config=thread_config,
                version="v2"
            ):
                kind = event["event"]
                
                # Stream status updates
                if kind == "on_chat_model_stream":
                    chunk_content = event["data"]["chunk"].content
                    # Ensure content is a string
                    if isinstance(chunk_content, list):
                        text_parts = []
                        for block in chunk_content:
                            if isinstance(block, str):
                                text_parts.append(block)
                            elif isinstance(block, dict) and 'text' in block:
                                text_parts.append(block['text'])
                        content = ''.join(text_parts)
                    else:
                        content = str(chunk_content) if chunk_content else ""
                    if content:
                        accumulated_answer += content
                        yield f"data: {json.dumps({'type': 'content', 'data': content})}\n\n"
                
                # Tool calls
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'status', 'data': f'Searching {tool_name}...'})}\n\n"
                
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'chat_id': chat_id})}\n\n"
            
            # Save message to database
            new_message = Message(
                chat_id=chat.id,
                human=message_data.message,
                bot=accumulated_answer,
            )
            session.add(new_message)
            await session.commit()
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/messages/{chat_id}", response_model=ChatWithMessages)
async def get_chat_messages(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get all messages for a specific chat."""
    
    # Verify chat exists and belongs to user
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == uuid.UUID(current_user["user_id"]),
            Chat.archived_at.is_(None)
        )
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Get messages
    messages_result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(asc(Message.created_at))
    )
    messages = messages_result.scalars().all()
    
    return ChatWithMessages(
        id=str(chat.id),
        title=chat.title,
        updated_at=chat.updated_at,
        messages=[MessageResponse.model_validate(msg) for msg in messages]
    )


@router.put("/rename/{chat_id}")
async def rename_chat(
    chat_id: str,
    rename_data: ChatRename,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rename a chat."""
    
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == uuid.UUID(current_user["user_id"])
        )
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.title = rename_data.title
    await session.commit()
    
    return {"success": True, "message": "Chat renamed successfully"}


@router.delete("/archive/{chat_id}")
async def archive_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Archive a chat."""
    
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == uuid.UUID(current_user["user_id"])
        )
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    from datetime import datetime, timezone
    chat.archived_at = datetime.now(timezone.utc)
    await session.commit()
    
    return {"success": True, "message": "Chat archived successfully"}
