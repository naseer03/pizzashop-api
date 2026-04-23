from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.kitchen_hub import kitchen_hub

router = APIRouter()


@router.websocket("/ws/kitchen")
async def kitchen_socket(websocket: WebSocket):
    await kitchen_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await kitchen_hub.disconnect(websocket)
