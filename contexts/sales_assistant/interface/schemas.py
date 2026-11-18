from pydantic import BaseModel


class SalesChatRequest(BaseModel):
    conversationId: str | None = None
    message: str
    source: str = "web"
