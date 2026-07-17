from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .game import GameError, GameRoom

BASE = Path(__file__).parent
STATIC = BASE / "static"
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=24)

class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, GameRoom] = {}
        self.connections: dict[str, dict[str, WebSocket]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def make_code(self) -> str:
        import secrets
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if code not in self.rooms: return code

    def create(self, name: str) -> tuple[GameRoom, Any]:
        code = self.make_code(); room = GameRoom(code)
        player = room.add_player(clean_name(name))
        self.rooms[code] = room; self.connections[code] = {}; self.locks[code] = asyncio.Lock()
        return room, player

    def get(self, code: str) -> GameRoom:
        room = self.rooms.get(code.upper())
        if not room: raise GameError("Spielraum nicht gefunden.")
        return room

    async def broadcast(self, code: str) -> None:
        room = self.rooms.get(code)
        if not room: return
        stale=[]
        for player_id, ws in list(self.connections.get(code, {}).items()):
            if player_id not in room.players: stale.append(player_id); continue
            try: await ws.send_json({"type":"state", "state":room.public_state(player_id)})
            except Exception: stale.append(player_id)
        for pid in stale: self.connections.get(code, {}).pop(pid, None)

manager = RoomManager()

def clean_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    if not cleaned: raise GameError("Bitte gib einen Namen ein.")
    return cleaned[:24]

async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(300)
        cutoff=time.time()-3*60*60
        for code, room in list(manager.rooms.items()):
            if room.updated_at < cutoff and not manager.connections.get(code):
                manager.rooms.pop(code,None); manager.connections.pop(code,None); manager.locks.pop(code,None)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task=asyncio.create_task(cleanup_loop())
    yield
    task.cancel()

app=FastAPI(title="PSE-Quartett", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
async def index(): return FileResponse(STATIC/"index.html")

@app.get("/manifest.webmanifest")
async def manifest(): return FileResponse(STATIC/"manifest.webmanifest", media_type="application/manifest+json")

@app.get("/health")
async def health(): return {"status":"ok", "rooms":len(manager.rooms)}

@app.post("/api/rooms")
async def create_room(body: NameBody):
    try: room, player = manager.create(body.name)
    except GameError as exc: raise HTTPException(400,str(exc))
    return session_payload(room, player)

@app.post("/api/rooms/{code}/join")
async def join_room(code: str, body: NameBody):
    try:
        room=manager.get(code)
        role="player" if room.phase=="lobby" and len(room.active_players)<5 else "spectator"
        player=room.add_player(clean_name(body.name), role=role)
        return session_payload(room,player)
    except GameError as exc: raise HTTPException(400,str(exc))

def session_payload(room: GameRoom, player: Any) -> dict[str,Any]:
    return {"roomCode":room.code,"playerId":player.id,"token":player.token,"role":player.role,"name":player.name}

async def schedule_auto_resolution(code: str, resolution_id: int, deadline: float | None) -> None:
    if deadline is None: return
    await asyncio.sleep(max(0, deadline-time.time()))
    room=manager.rooms.get(code)
    if not room: return
    lock=manager.locks[code]
    async with lock:
        if room.phase=="awaiting_confirmations" and room.resolution_id==resolution_id:
            room.finalize_round()
    await manager.broadcast(code)

@app.websocket("/ws/{code}/{player_id}")
async def websocket_endpoint(ws: WebSocket, code: str, player_id: str):
    code=code.upper(); token=ws.query_params.get("token","")
    await ws.accept()
    try:
        room=manager.get(code); room.authenticate(player_id,token)
    except GameError as exc:
        await ws.send_json({"type":"error","message":str(exc),"fatal":True}); await ws.close(code=4401); return

    old=manager.connections[code].get(player_id)
    if old and old is not ws:
        try: await old.close(code=4000)
        except Exception: pass
    manager.connections[code][player_id]=ws
    room.mark_connected(player_id,True)
    await manager.broadcast(code)
    try:
        while True:
            message=await ws.receive_json()
            action=message.get("type")
            lock=manager.locks[code]
            timer=None
            async with lock:
                room=manager.get(code)
                try:
                    if action=="start": room.start_game(player_id)
                    elif action=="abort": room.abort_game(player_id)
                    elif action=="play_again": room.start_game(player_id)
                    elif action=="kick": room.kick_player(player_id,str(message.get("playerId","")))
                    elif action=="choose": room.choose_category(player_id,str(message.get("category","")))
                    elif action=="confirm": room.confirm_transfer(player_id,str(message.get("direction","")))
                    elif action=="ping": pass
                    else: raise GameError("Unbekannte Aktion.")
                    if room.phase=="awaiting_confirmations":
                        timer=(room.resolution_id,room.confirmation_deadline)
                except GameError as exc:
                    await ws.send_json({"type":"error","message":str(exc),"fatal":False})
            await manager.broadcast(code)
            if timer: asyncio.create_task(schedule_auto_resolution(code,*timer))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if manager.connections.get(code,{}).get(player_id) is ws:
            manager.connections[code].pop(player_id,None)
            if code in manager.rooms and player_id in manager.rooms[code].players:
                manager.rooms[code].mark_connected(player_id,False)
                await manager.broadcast(code)
