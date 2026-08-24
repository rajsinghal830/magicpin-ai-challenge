import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, wait

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import conversation
import router
import validators
from config import TEAM
from models import (
    VALID_SCOPES,
    Action,
    ContextAck,
    ContextPush,
    ContextReject,
    Healthz,
    ReplyRequest,
    ReplyResponse,
    TickRequest,
    TickResponse,
)
from store import store

app = FastAPI(title="Vera 2.0")

# Judge drops anything past 30s. Leave headroom for serialization + network.
TICK_BUDGET_S = 24.0
TICK_WORKERS = 8

# Protects conversation-state writes in tick() from concurrent futures.
_conv_lock = threading.Lock()

# Long-lived: exiting a `with ThreadPoolExecutor` would block on stragglers we mean to abandon.
_pool = ThreadPoolExecutor(max_workers=TICK_WORKERS, thread_name_prefix="compose")


@app.exception_handler(RequestValidationError)
async def malformed(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"accepted": False, "reason": "malformed", "details": str(exc.errors()[:3])})


@app.get("/v1/healthz", response_model=Healthz)
def healthz() -> Healthz:
    return Healthz(
        status="ok",
        uptime_seconds=store.uptime_seconds(),
        contexts_loaded=store.counts(),
    )


@app.get("/v1/metadata")
def metadata() -> dict:
    return TEAM


@app.post("/v1/context")
def push_context(req: ContextPush):
    if req.scope not in VALID_SCOPES:
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_scope", "details": f"scope must be one of {list(VALID_SCOPES)}"},
        )
    result = store.push(req.scope, req.context_id, req.version, req.payload)
    if not result["ok"]:
        reject = ContextReject(reason=result["reason"], current_version=result["current_version"])
        return JSONResponse(status_code=409, content=reject.model_dump())
    return ContextAck(ack_id=result["ack_id"], stored_at=result["stored_at"])


@app.post("/v1/teardown")
def teardown():
    store.reset()
    return {"accepted": True, "state": "wiped"}


def _compose_one(trigger: dict):
    try:
        return router.build_action(store, trigger)
    except Exception:
        logging.error("tick build_action failed for %s: %s", trigger.get("id"), traceback.format_exc())
        return None


@app.post("/v1/tick", response_model=TickResponse)
def tick(req: TickRequest) -> TickResponse:
    deadline = time.monotonic() + TICK_BUDGET_S
    triggers = router.select(store, req.available_triggers)
    if not triggers:
        return TickResponse(actions=[])

    futures = [_pool.submit(_compose_one, t) for t in triggers]
    wait(futures, timeout=max(0.0, deadline - time.monotonic()))

    actions: list[Action] = []
    for fut in futures:  # trigger order = urgency order
        if not fut.done():
            fut.cancel()  # unstarted work is dropped; started work is abandoned, never awaited
            continue
        action = fut.result()
        if not action:
            continue
        with _conv_lock:
            conv_id = action["conversation_id"]
            if validators.is_repeat(store, conv_id, action["body"]):
                continue
            conv = store.conversations.setdefault(conv_id, {
                "merchant_id": action["merchant_id"],
                "customer_id": action["customer_id"],
                "trigger_id": action["trigger_id"],
                "sent_bodies": [],
                "unanswered": 0,
            })
            conv["sent_bodies"].append(action["body"])
            conv["unanswered"] = conv.get("unanswered", 0) + 1
            if action["suppression_key"]:
                store.suppressed_keys.add(action["suppression_key"])
        actions.append(Action(**action))
    return TickResponse(actions=actions)


@app.post("/v1/reply", response_model=ReplyResponse, response_model_exclude_none=True)
def reply(req: ReplyRequest) -> ReplyResponse:
    conv = store.conversations.setdefault(req.conversation_id, {"sent_bodies": [], "unanswered": 0})
    if req.merchant_id and not conv.get("merchant_id"):
        conv["merchant_id"] = req.merchant_id
    if req.customer_id and not conv.get("customer_id"):
        conv["customer_id"] = req.customer_id

    try:
        result = conversation.respond(store, req.conversation_id, req.message, from_role=req.from_role)
    except Exception:
        logging.error("reply failed for %s: %s", req.conversation_id, traceback.format_exc())
        result = {"action": "wait", "wait_seconds": 300, "rationale": "Transient composition error; backing off briefly."}
    return ReplyResponse(**result)


if __name__ == "__main__":
    import uvicorn

    from config import PORT

    uvicorn.run(app, host="0.0.0.0", port=PORT)
