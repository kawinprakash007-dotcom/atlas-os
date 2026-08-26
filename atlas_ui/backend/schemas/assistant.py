from pydantic import BaseModel, Field

class AssistantChatRequest(BaseModel):
    message: str = Field(..., description="The user's input message")
