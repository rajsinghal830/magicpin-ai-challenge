from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

Scope = Literal["category", "merchant", "customer", "trigger"]
SendAs = Literal["vera", "merchant_on_behalf"]
Cta = Literal["open_ended", "binary_yes_no", "binary_confirm_cancel", "multi_choice_slot", "none"]
ReplyAction = Literal["send", "wait", "end"]


VALID_SCOPES = ("category", "merchant", "customer", "trigger")


class ContextPush(BaseModel):
    # Validated in the route so an unknown scope yields 400/invalid_scope, not 422.
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: Optional[str] = None


class ContextAck(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str


class ContextReject(BaseModel):
    accepted: bool = False
    reason: str
    current_version: int


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class Action(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: SendAs
    trigger_id: str
    template_name: Optional[str] = None
    template_params: Optional[list[str]] = None
    body: str
    cta: Cta
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[Action] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


class ReplyResponse(BaseModel):
    action: ReplyAction
    body: Optional[str] = None
    cta: Optional[Cta] = None
    wait_seconds: Optional[int] = None
    rationale: str


class Healthz(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: dict[str, int]
