import random
import pytest
from app.game import GameError, GameRoom, ACTIVE_CARD_COUNTS

def room_with_players(n: int, seed: int = 7):
    room=GameRoom("TEST42", rng=random.Random(seed))
    players=[room.add_player(f"P{i+1}") for i in range(n)]
    for p in players: p.connected=True
    return room,players

@pytest.mark.parametrize("count",[2,3,4,5])
def test_equal_start_distribution(count):
    room,players=room_with_players(count)
    room.start_game(players[0].id)
    expected=ACTIVE_CARD_COUNTS[count]//count
    assert [len(p.deck) for p in players]==[expected]*count
    assert len(room.reserve)==34-ACTIVE_CARD_COUNTS[count]
    assert len({c for p in players for c in p.deck}|set(room.reserve))==34

def test_unique_winner_requires_correct_swipes():
    room,players=room_with_players(2)
    a,b=players
    room.phase="choosing"; room.round_number=1; room.active_player_id=a.id
    a.deck=["h"]; b.deck=["he"]
    room.total_active_cards=2
    room.choose_category(a.id,"molarMass")
    assert room.winner_id==b.id and room.phase=="awaiting_confirmations"
    with pytest.raises(GameError): room.confirm_transfer(a.id,"right")
    room.confirm_transfer(a.id,"left")
    with pytest.raises(GameError): room.confirm_transfer(a.id,"left")
    room.confirm_transfer(b.id,"right")
    assert room.phase=="finished"
    assert len(b.deck)==2 and len(a.deck)==0

def test_tie_goes_to_stechen_and_pot_is_preserved():
    room,players=room_with_players(2)
    a,b=players
    room.phase="choosing"; room.round_number=1; room.active_player_id=a.id
    a.deck=["li","h"]; b.deck=["be","he"]; room.total_active_cards=4
    room.choose_category(a.id,"occupiedShells")
    assert room.phase=="tie_choose" and len(room.pot)==2
    room.choose_category(a.id,"firstIonizationEnergy")
    assert room.winner_id==b.id and len(room.pot)==4
    room.confirm_transfer(a.id,"left"); room.confirm_transfer(b.id,"right")
    assert room.phase=="finished" and len(b.deck)==4

def test_missing_value_category_is_rejected():
    room,players=room_with_players(2);a,b=players
    room.phase="choosing";room.round_number=1;room.active_player_id=a.id
    a.deck=["he"];b.deck=["h"]
    assert "meltingPoint" not in room.available_categories()
    with pytest.raises(GameError): room.choose_category(a.id,"meltingPoint")

def test_host_transfer_on_disconnect():
    room,players=room_with_players(3);a,b,c=players
    assert a.is_host
    room.mark_connected(a.id,False)
    assert b.is_host and not a.is_host

def test_density_is_compared_in_common_unit():
    room,players=room_with_players(2);a,b=players
    room.phase="choosing";room.round_number=1;room.active_player_id=a.id
    a.deck=["cl"];b.deck=["li"]
    room.choose_category(a.id,"density")
    # Chlor shows 3.2 g/L, Lithium 0.534 g/cm³ (= 534 g/L).
    assert room.winner_id==b.id
