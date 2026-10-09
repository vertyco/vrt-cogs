import random

from marblemunch.common import npc as npc_module
from marblemunch.common.npc import REACTION, Npc
from marblemunch.common.rules import DT, MARBLE_COUNT, Board, Marble


def lone_marble_board(x, y, vx=0.0, vy=0.0):
    board = Board(random.Random(5))
    board.released = MARBLE_COUNT
    board.marbles = [Marble(0, x, y, vx, vy)]
    return board


def play(board, npc, seconds):
    """Run the board with the NPC sending its inputs, the way the match does"""
    actions = []
    for _ in range(round(seconds / DT)):
        action = npc.decide(board, DT)
        actions.append(action)
        if action == "press":
            board.hippos[npc.seat].press()
        elif action == "release":
            board.hippos[npc.seat].release()
        board.step()
    return actions


def test_an_npc_munches_a_marble_sitting_in_its_lane(monkeypatch):
    monkeypatch.setattr(npc_module, "MISS_CHANCE", 0.0)
    board = lone_marble_board(500, 600)
    actions = play(board, Npc(0, random.Random(2)), 3)
    assert board.hippos[0].score == 1
    assert set(actions) <= {"press", "release", None}


def test_an_npc_munches_a_marble_rolling_toward_it(monkeypatch):
    monkeypatch.setattr(npc_module, "MISS_CHANCE", 0.0)
    board = lone_marble_board(500, 450, 0.0, 60.0)
    play(board, Npc(0, random.Random(2)), 4)
    assert board.hippos[0].score == 1


def test_an_npc_waits_a_human_reaction_time_before_pressing():
    board = lone_marble_board(500, 600)
    assert "press" not in play(board, Npc(0, random.Random(2)), REACTION[0] - DT)


def test_an_npc_leaves_marbles_outside_its_lane_alone():
    board = lone_marble_board(200, 600)
    assert "press" not in play(board, Npc(0, random.Random(2)), 2)


def test_npcs_in_every_seat_find_their_own_lane(monkeypatch):
    monkeypatch.setattr(npc_module, "MISS_CHANCE", 0.0)
    for seat, (x, y) in enumerate([(500, 600), (400, 500), (500, 400), (600, 500)]):
        board = lone_marble_board(x, y)
        play(board, Npc(seat, random.Random(2)), 3)
        assert board.hippos[seat].score == 1, seat


def test_an_npc_munches_a_marble_under_its_own_neck(monkeypatch):
    monkeypatch.setattr(npc_module, "MISS_CHANCE", 0.0)
    board = lone_marble_board(500, 1000 - 150)
    play(board, Npc(0, random.Random(2)), 3)
    assert board.hippos[0].score == 1
