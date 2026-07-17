from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

DATA_PATH = Path(__file__).parent / "data" / "elements.json"
ELEMENTS: list[dict[str, Any]] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
CARD_BY_ID = {card["id"]: card for card in ELEMENTS}

CATEGORY_META: dict[str, dict[str, str]] = {
    "molarMass": {"label": "Molare Masse", "unit": "g/mol", "help": "Masse eines Mols des Elements."},
    "meltingPoint": {"label": "Schmelztemperatur", "unit": "°C", "help": "Temperatur des Übergangs von fest zu flüssig."},
    "boilingPoint": {"label": "Siede-/Sublimationstemperatur", "unit": "°C", "help": "Temperatur des Übergangs in die Gasphase."},
    "density": {"label": "Dichte", "unit": "kartenabhängig", "help": "Masse pro Volumen. Im Spiel werden die Zahlenwerte verglichen; die Einheit steht auf der Karte."},
    "protonCount": {"label": "Protonenzahl", "unit": "", "help": "Entspricht der Ordnungszahl."},
    "valenceElectrons": {"label": "Valenzelektronen", "unit": "", "help": "Elektronen in der äußersten besetzten Schale."},
    "occupiedShells": {"label": "Besetzte Energiestufen", "unit": "", "help": "Entspricht bei diesen Elementen der Periodennummer."},
    "firstIonizationEnergy": {"label": "1. Ionisierungsenergie", "unit": "kJ/mol", "help": "Energie zum Entfernen des ersten Elektrons aus einem gasförmigen Atom."},
    "atomicRadius": {"label": "Atomradius", "unit": "pm", "help": "Hier wird ein einheitlicher empirischer Atomradius verwendet."},
}

ACTIVE_CARD_COUNTS = {2: 34, 3: 33, 4: 32, 5: 30}

class GameError(ValueError):
    pass

@dataclass
class Player:
    id: str
    token: str
    name: str
    role: str = "player"
    is_host: bool = False
    connected: bool = False
    deck: list[str] = field(default_factory=list)
    joined_at: float = field(default_factory=time.time)
    confirmed_direction: str | None = None

@dataclass
class GameRoom:
    code: str
    rng: random.Random = field(default_factory=random.Random)
    players: dict[str, Player] = field(default_factory=dict)
    phase: str = "lobby"
    round_number: int = 0
    round_step: int = 0
    active_player_id: str | None = None
    current_category: str | None = None
    revealed: dict[str, str] = field(default_factory=dict)
    pot: list[str] = field(default_factory=list)
    reserve: list[str] = field(default_factory=list)
    contenders: list[str] = field(default_factory=list)
    round_participants: set[str] = field(default_factory=set)
    winner_id: str | None = None
    pending_confirmations: set[str] = field(default_factory=set)
    confirmation_deadline: float | None = None
    resolution_id: int = 0
    resolution_note: str = ""
    last_result: dict[str, Any] | None = None
    total_active_cards: int = 0
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.role == "player"]

    def add_player(self, name: str, *, role: str = "player") -> Player:
        if role == "player" and self.phase != "lobby":
            role = "spectator"
        if role == "player" and len(self.active_players) >= 5:
            raise GameError("Der Spielraum ist bereits voll.")
        player = Player(
            id=secrets.token_urlsafe(8), token=secrets.token_urlsafe(24),
            name=name, role=role, is_host=not self.players,
        )
        self.players[player.id] = player
        self.touch()
        return player

    def authenticate(self, player_id: str, token: str) -> Player:
        player = self.players.get(player_id)
        if not player or not secrets.compare_digest(player.token, token):
            raise GameError("Ungültige oder abgelaufene Spielsitzung.")
        return player

    def mark_connected(self, player_id: str, connected: bool) -> None:
        player = self.players[player_id]
        player.connected = connected
        if not connected and player.is_host:
            replacement = next((p for p in self.active_players if p.connected and p.id != player_id), None)
            if replacement:
                player.is_host = False
                replacement.is_host = True
        if connected and not any(p.is_host for p in self.players.values()):
            player.is_host = True
        if not connected and self.active_player_id == player_id and self.phase in {"choosing", "tie_choose"}:
            if self.phase == "tie_choose":
                candidates = [pid for pid in self.contenders if self.players[pid].connected and self.players[pid].deck]
            else:
                candidates = [p.id for p in self.active_players if p.connected and p.deck]
            if candidates:
                self.active_player_id = candidates[0]
        self.touch()

    def _require_host(self, player_id: str) -> Player:
        player = self.players.get(player_id)
        if not player or not player.is_host:
            raise GameError("Nur der Gastgeber darf diese Aktion ausführen.")
        return player

    def start_game(self, player_id: str) -> None:
        self._require_host(player_id)
        roster = self.active_players
        if not 2 <= len(roster) <= 5:
            raise GameError("Zum Start werden 2 bis 5 Spieler benötigt.")
        if sum(p.connected for p in roster) < 2:
            raise GameError("Mindestens zwei Spieler müssen verbunden sein.")
        for p in roster:
            p.deck.clear(); p.confirmed_direction = None
        deck = list(CARD_BY_ID)
        self.rng.shuffle(deck)
        self.total_active_cards = ACTIVE_CARD_COUNTS[len(roster)]
        active_deck, self.reserve = deck[:self.total_active_cards], deck[self.total_active_cards:]
        per_player = self.total_active_cards // len(roster)
        for index, card_id in enumerate(active_deck):
            roster[index % len(roster)].deck.append(card_id)
        assert all(len(p.deck) == per_player for p in roster)
        self.phase = "choosing"
        self.round_number = 1
        self.round_step = 0
        self.active_player_id = self.rng.choice([p.id for p in roster if p.connected])
        self.current_category = None
        self.revealed.clear(); self.pot.clear(); self.contenders.clear(); self.round_participants.clear()
        self.winner_id = None; self.pending_confirmations.clear(); self.confirmation_deadline = None
        self.resolution_note = ""; self.last_result = None
        self.resolution_id += 1
        self.touch()

    def abort_game(self, player_id: str) -> None:
        self._require_host(player_id)
        for p in self.active_players:
            p.deck.clear(); p.confirmed_direction = None
        self.phase = "lobby"; self.round_number = 0; self.round_step = 0
        self.active_player_id = None; self.current_category = None
        self.revealed.clear(); self.pot.clear(); self.reserve.clear(); self.contenders.clear(); self.round_participants.clear()
        self.winner_id = None; self.pending_confirmations.clear(); self.confirmation_deadline = None
        self.resolution_id += 1; self.touch()

    def kick_player(self, host_id: str, target_id: str) -> None:
        self._require_host(host_id)
        if self.phase != "lobby":
            raise GameError("Spieler können nur in der Lobby entfernt werden.")
        if target_id == host_id:
            raise GameError("Der Gastgeber kann sich nicht selbst entfernen.")
        target = self.players.get(target_id)
        if not target:
            raise GameError("Spieler nicht gefunden.")
        del self.players[target_id]
        self.touch()

    def _round_player_ids(self) -> list[str]:
        if self.phase == "tie_choose":
            return [pid for pid in self.contenders if self.players[pid].deck]
        return [p.id for p in self.active_players if p.deck]

    @staticmethod
    def comparison_value(card: dict[str, Any], category: str) -> float | None:
        # Dichten werden intern in der gemeinsamen Einheit g/L verglichen,
        # während die Karte Gase in g/L und kondensierte Stoffe in g/cm³ anzeigt.
        key = "densityCompare" if category == "density" else category
        value = card.get(key)
        return None if value is None else float(value)

    def available_categories(self) -> list[str]:
        participant_ids = self._round_player_ids()
        available=[]
        for key in CATEGORY_META:
            if participant_ids and all(self.comparison_value(CARD_BY_ID[self.players[pid].deck[0]], key) is not None for pid in participant_ids):
                available.append(key)
        return available

    def choose_category(self, player_id: str, category: str) -> None:
        if self.phase not in {"choosing", "tie_choose"}:
            raise GameError("Aktuell kann keine Kategorie gewählt werden.")
        if player_id != self.active_player_id:
            raise GameError("Du bist noch nicht an der Reihe.")
        if category not in CATEGORY_META:
            raise GameError("Unbekannte Kategorie.")
        participant_ids = self._round_player_ids()
        if len(participant_ids) < 2:
            raise GameError("Für den Vergleich sind nicht genügend Karten vorhanden.")
        if category not in self.available_categories():
            raise GameError("Diese Kategorie ist für die aktuellen Karten nicht vergleichbar.")

        self.current_category = category
        self.revealed = {}
        self.round_step += 1
        for pid in participant_ids:
            card_id = self.players[pid].deck.pop(0)
            self.revealed[pid] = card_id
            self.pot.append(card_id)
            self.round_participants.add(pid)
        values = {pid: self.comparison_value(CARD_BY_ID[cid], category) for pid, cid in self.revealed.items()}
        assert all(value is not None for value in values.values())
        best = max(values.values())
        winners = [pid for pid, value in values.items() if value == best]

        if len(winners) == 1:
            self._set_winner(winners[0])
        else:
            eligible = [pid for pid in winners if self.players[pid].deck]
            if len(eligible) == 1:
                self.resolution_note = "Die anderen Gleichstands-Spieler hatten keine weitere Karte."
                self._set_winner(eligible[0])
            elif not eligible:
                chosen = self.rng.choice(winners)
                self.resolution_note = "Alle Gleichstands-Spieler waren ohne Folgekarte; ein fairer Losentscheid war nötig."
                self._set_winner(chosen)
            else:
                self.phase = "tie_choose"
                self.contenders = eligible
                self.active_player_id = player_id if player_id in eligible else eligible[0]
                self.winner_id = None
                self.pending_confirmations.clear()
                self.confirmation_deadline = None
                self.resolution_note = "Gleichstand – Stechen! Die Karten bleiben im Pot."
        self.touch()

    def _set_winner(self, winner_id: str) -> None:
        self.phase = "awaiting_confirmations"
        self.winner_id = winner_id
        self.contenders.clear()
        self.pending_confirmations = set(self.round_participants)
        for p in self.players.values():
            p.confirmed_direction = None
        self.confirmation_deadline = time.time() + 15
        self.resolution_id += 1

    def confirm_transfer(self, player_id: str, direction: str) -> bool:
        if self.phase != "awaiting_confirmations" or not self.winner_id:
            raise GameError("Es wartet keine Kartenübertragung auf Bestätigung.")
        if player_id not in self.round_participants:
            raise GameError("Du warst an dieser Runde nicht beteiligt.")
        if player_id not in self.pending_confirmations:
            raise GameError("Deine Bestätigung wurde bereits gespeichert.")
        expected = "right" if player_id == self.winner_id else "left"
        if direction != expected:
            arrow = "rechts" if expected == "right" else "links"
            raise GameError(f"Falsche Richtung – bitte nach {arrow} wischen.")
        self.players[player_id].confirmed_direction = direction
        self.pending_confirmations.remove(player_id)
        self.touch()
        if not self.pending_confirmations:
            self.finalize_round()
            return True
        return False

    def finalize_round(self) -> None:
        if self.phase != "awaiting_confirmations" or not self.winner_id:
            return
        winner = self.players[self.winner_id]
        won_count = len(self.pot)
        won_cards = self.pot[:]
        self.rng.shuffle(won_cards)
        winner.deck.extend(won_cards)
        category = self.current_category
        self.last_result = {
            "winnerId": winner.id, "winnerName": winner.name, "wonCards": won_count,
            "category": category, "categoryLabel": CATEGORY_META.get(category or "", {}).get("label", ""),
            "note": self.resolution_note,
        }
        remaining = [p for p in self.active_players if p.deck]
        self.pot.clear(); self.revealed.clear(); self.round_participants.clear(); self.pending_confirmations.clear()
        self.confirmation_deadline = None; self.current_category = None; self.resolution_note = ""
        for p in self.players.values(): p.confirmed_direction = None
        self.resolution_id += 1
        if len(remaining) <= 1:
            self.phase = "finished"
            self.active_player_id = remaining[0].id if remaining else winner.id
            self.winner_id = self.active_player_id
        else:
            self.phase = "choosing"
            self.round_number += 1
            self.round_step = 0
            self.active_player_id = winner.id if winner.deck else remaining[0].id
            self.winner_id = None
        self.touch()

    def expected_direction(self, player_id: str) -> str | None:
        if self.phase != "awaiting_confirmations" or player_id not in self.round_participants:
            return None
        return "right" if player_id == self.winner_id else "left"

    def public_state(self, viewer_id: str) -> dict[str, Any]:
        viewer = self.players[viewer_id]
        participant_ids = self._round_player_ids() if self.phase in {"choosing", "tie_choose"} else []
        own_card = None
        if viewer.role == "player" and viewer.id in participant_ids and viewer.deck:
            own_card = CARD_BY_ID[viewer.deck[0]]
        revealed_cards = [
            {"playerId": pid, "playerName": self.players[pid].name, "card": CARD_BY_ID[cid], "isWinner": pid == self.winner_id}
            for pid, cid in self.revealed.items()
        ]
        players=[]
        for p in self.players.values():
            players.append({
                "id": p.id, "name": p.name, "role": p.role, "isHost": p.is_host,
                "connected": p.connected, "cardCount": len(p.deck) if p.role == "player" else None,
                "isActive": p.id == self.active_player_id, "isContender": p.id in self.contenders,
                "eliminated": p.role == "player" and self.phase not in {"lobby"} and len(p.deck) == 0 and p.id not in self.round_participants,
                "confirmed": p.confirmed_direction is not None,
            })
        active_name = self.players[self.active_player_id].name if self.active_player_id in self.players else ""
        winner_name = self.players[self.winner_id].name if self.winner_id in self.players else ""
        status = self._status_for(viewer_id, active_name, winner_name)
        return {
            "roomCode": self.code, "phase": self.phase, "roundNumber": self.round_number,
            "roundStep": self.round_step, "players": players,
            "you": {"id": viewer.id, "name": viewer.name, "role": viewer.role, "isHost": viewer.is_host},
            "activePlayerId": self.active_player_id, "currentCategory": self.current_category,
            "currentCategoryLabel": CATEGORY_META.get(self.current_category or "", {}).get("label"),
            "ownCard": own_card, "revealedCards": revealed_cards,
            "potCount": len(self.pot), "reserveCount": len(self.reserve), "totalActiveCards": self.total_active_cards,
            "winnerId": self.winner_id, "winnerName": winner_name,
            "pendingConfirmations": list(self.pending_confirmations),
            "expectedDirection": self.expected_direction(viewer_id),
            "confirmationDeadline": self.confirmation_deadline,
            "availableCategories": self.available_categories() if viewer.id == self.active_player_id and self.phase in {"choosing", "tie_choose"} else [],
            "categories": CATEGORY_META, "status": status, "resolutionNote": self.resolution_note,
            "lastResult": self.last_result,
        }

    def _status_for(self, viewer_id: str, active_name: str, winner_name: str) -> str:
        if self.phase == "lobby": return "Warte auf den Spielstart."
        if self.phase == "choosing":
            return "Wähle eine Kategorie – der höchste Wert gewinnt." if viewer_id == self.active_player_id else f"{active_name} wählt eine Kategorie."
        if self.phase == "tie_choose":
            return "Stechen: Wähle die nächste Kategorie." if viewer_id == self.active_player_id else f"Stechen: {active_name} wählt die nächste Kategorie."
        if self.phase == "awaiting_confirmations":
            direction = self.expected_direction(viewer_id)
            if direction == "right": return "Du hast gewonnen – nach rechts wischen oder → drücken."
            if direction == "left": return "Du hast verloren – nach links wischen oder ← drücken."
            return f"{winner_name} gewinnt die Runde."
        if self.phase == "finished":
            return "Du hast das Spiel gewonnen!" if viewer_id == self.winner_id else f"{winner_name} gewinnt das Spiel."
        return ""
