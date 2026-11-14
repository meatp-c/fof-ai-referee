"""Review 23.10.2026, structure items in commands/vehicles/enemy/contact/events (Struktur 2, 3, 9, 10, LOW dead code;
L420-L439): pure refactors, checked in-process on the synthetic board."""

import dataclasses
import pathlib
import re

import pytest
from conftest import unit

from fof import briefing, commands, contact, enemy, rules, state, vehicles
from fof import grenades  # L556: split from commands

SRC = pathlib.Path(commands.__file__).resolve().parent


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def plt_hq(board, name="1st PLT HQ", card_id="22"):
    board["commands"][name] = {"available": 6, "saved": 0, "activated": True, "done": False}
    board["units"][name] = unit(card_id, vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    board["active_hq"] = name
    return board["units"][name]


# ---------------------------------------------------------------- Struktur 9: spotted helpers


def test_spotted_helpers_filter_side_and_flag_in_board_order(board):
    s = board
    s["units"]["E1"] = unit("23", side="Enemy")
    s["units"]["E2"] = unit("23", side="Enemy", spotted=False)
    s["units"]["E3"] = unit("23", side="Enemy")
    s["units"]["E4"] = unit("23", side="Enemy")
    del s["units"]["E4"]["spotted"]  # a missing flag counts as Unspotted
    s["units"]["US1"] = unit("23")
    s["units"]["E5"] = unit("22", side="Enemy")
    assert commands.spotted_enemies(s, "23") == ["E1", "E3"]
    assert commands.unspotted_enemies(s, "23") == ["E2", "E4"]
    assert commands.spotted_enemies(s, "11") == [] and commands.unspotted_enemies(s, "11") == []


def test_vehicle_spot_step_flips_only_the_unspotted(board):
    s = board
    s["units"]["E1"] = unit("23", side="Enemy", spotted=False)
    s["units"]["E2"] = unit("23", side="Enemy")
    prot = []
    vehicles.run_spot(s, "Sherman", vehicles.make_step("spot", card="23", success=True), prot)
    assert s["units"]["E1"]["spotted"] is True
    assert prot[0] == "23: E1 Spotted, flip the counters [8.5]"
    prot = []
    vehicles.run_spot(s, "Sherman", vehicles.make_step("spot", card="23", success=True), prot)
    assert prot == ["23: no Unspotted enemy left to Spot"]


def test_point_blank_grenade_needs_a_spotted_enemy(board):
    s = board
    z = s["units"]["1/1"] = unit("23")
    s["units"]["E1"] = unit("23", side="Enemy", spotted=False)
    with pytest.raises(rules.Violation, match=r"No Spotted enemy on 23 \[7.10\]"):
        grenades.check_grenade(s, z, "1/1", {})
    s["units"]["E1"]["spotted"] = True
    assert grenades.check_grenade(s, z, "1/1", {}) == "23"


# ---------------------------------------------------------------- Struktur 10: OrderCtx / EnemyActionCtx


def _ctx(s):
    plt_hq(s)
    s["phase"] = "3.3.2a"
    s["units"]["1/1"] = unit("22", platoon="1")
    return commands.order_context(s, "1st PLT HQ", "1/1", "4.2.4b", {"--success": "yes"}, None)


def test_order_context_is_an_order_ctx_with_defaults(board):
    ctx = _ctx(board)
    assert isinstance(ctx, commands.OrderCtx)
    assert (ctx.action_id, ctx.target_name, ctx.hq_name, ctx.success, ctx.gi) == (
        "4.2.4b",
        "1/1",
        "1st PLT HQ",
        "yes",
        False,
    )
    assert ctx.recipient is board["units"]["1/1"] and ctx.recipient_card is board["cards"]["22"]
    assert ctx.prot == [] and ctx.mods == [] and ctx.moved == [] and ctx.extra == 0
    assert ctx.orig is None and ctx.candidates is None and ctx.late_order is None
    assert ctx.name == rules.ACTIONS["4.2.4b"][0]


def test_order_ctx_copy_is_shallow_like_the_old_namespace(board):
    """Platoon Fire copies ctx per firing unit: the copy writes into the same protocol, the original keeps its fields."""
    ctx = _ctx(board)
    other = unit("22", platoon="1")
    ctx2 = dataclasses.replace(ctx, action_id="4.2.4d", target_name="2/1", recipient=other, o={"--x": 1}, success="no")
    ctx2.prot.append("line of the copy")
    assert ctx.prot == ["line of the copy"] and ctx2.prot is ctx.prot and ctx2.mods is ctx.mods
    assert (ctx.action_id, ctx.target_name, ctx.success) == ("4.2.4b", "1/1", "yes") and ctx.recipient is not other
    assert (ctx2.action_id, ctx2.target_name, ctx2.success, ctx2.recipient) == ("4.2.4d", "2/1", "no", other)
    assert ctx2.hq_name == ctx.hq_name and ctx2.recipient_card is ctx.recipient_card


def test_order_ctx_lists_are_not_shared_between_orders(board):
    a = _ctx(board)
    b = commands.order_context(board, "1st PLT HQ", "1/1", "4.2.4b", {}, None)
    a.prot.append("x")
    assert b.prot == [] and b.success is None


def _ctx_attributes(path, var):
    text = path.read_text(encoding="utf-8")
    return set(re.findall(rf"\b{var}2?\.([a-z_][a-z_0-9]*)", text))


def test_every_ctx_attribute_used_is_a_field():
    """The contract is explicit: every ctx.<attr> read or written by the order code is an OrderCtx field, every one of
    the enemy action code an EnemyActionCtx field (a dataclass without slots would accept a typo silently)."""
    order_fields = {f.name for f in dataclasses.fields(commands.OrderCtx)}
    used = _ctx_attributes(SRC / "commands.py", "ctx") | _ctx_attributes(SRC / "vehicles.py", "ctx")
    assert used - {"append"} <= order_fields
    enemy_fields = {f.name for f in dataclasses.fields(enemy.EnemyActionCtx)}
    assert _ctx_attributes(SRC / "enemy.py", "ctx") <= enemy_fields


# ---------------------------------------------------------------- Struktur 10: direct imports in vehicles.py


def sherman(card_id, side="US", **extra):
    e = unit(card_id, side=side, type="Vehicle", vehicle="M4 Sherman 75mm", platoon="Tank", vof="H", rng="V", steps=2)
    e.update(extra)
    return e


def test_knocked_out_crew_gets_free_fire_team_names(board):
    s = board
    s["units"]["Fire Team 1"] = unit("11", type="Fire Team", steps=1)
    s["units"]["Sherman 1"] = sherman("22")
    prot = []
    vehicles.apply_result(s, "Sherman 1", "Knocked Out", prot)
    crew = [n for n, e in s["units"].items() if e.get("crew_hit_open")]
    assert crew == ["Fire Team 2", "Fire Team 3"]
    assert all(s["units"][n]["status"] == [rules.EXPOSED] for n in crew)
    assert all(s["units"][n]["area"] == "C1" for n in crew) and "Sherman 1" not in s["units"]


def test_vehicle_concentrate_fire_marks_the_whole_stack(board):
    s = board
    s["cards"]["23"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1, "field": False}]
    s["units"]["E1"] = unit("23", side="Enemy", area="C1")
    s["units"]["E2"] = unit("23", side="Enemy", area="C1")
    s["units"]["E3"] = unit("23", side="Enemy")
    prot = []
    vehicles.run_cf(s, "Sherman 1", vehicles.make_step("cf", target="E1", success=True, critical=False), prot)
    assert [s["units"][n].get("cf", 0) for n in ("E1", "E2", "E3")] == [1, 1, 0]
    assert "(stack: E1, E2)" in prot[0]


# ---------------------------------------------------------------- Struktur 3: free_cover, LOW: set_area


def test_move_hint_names_only_cover_not_held_by_the_enemy(board, quiet):
    s = board
    s["cards"]["22"]["cover"] = [
        {"id": "C1", "type": "Basic Cover", "value": 1, "field": False},
        {"id": "C2", "type": "Basic Cover", "value": 1, "field": False},
    ]
    s["units"]["E1"] = unit("22", side="Enemy", area="C1")
    s["units"]["1/1"] = unit("21")
    prot = []
    commands.move_unit(s, "1/1", "22", None, True, prot)
    hint = [p for p in prot if "free or friendly Cover marker" in p]
    assert len(hint) == 1 and "on 22: C2 -" in hint[0]


@pytest.mark.parametrize("variant", ["existing_marker", "patrol"])
def test_package_unit_takes_only_cover_not_held_by_us_units(board, variant):
    """E58 (existing free marker instead of a second one) and a successful patrol infiltration both use
    state.free_cover(side="Enemy"): the marker under a US unit is taken."""
    s = board
    s["phase"] = "3.6"
    s["cards"]["23"]["cover"] = [
        {"id": "C1", "type": "Basic Cover", "value": 1, "field": False},
        {"id": "C2", "type": "Basic Cover", "value": 1, "field": False},
    ]
    s["units"]["1/1"] = unit("23", area="C1")
    s["units"]["1/2"] = unit("22")
    u = {"type_name": "Squad", "place": "x", "type": "Squad", "steps": 3, "vof_rating": "S"}
    u.update({"cover": "Basic Cover", "cover_value": 1} if variant == "existing_marker" else {"infiltration": True})
    prot = []
    new = contact.contact_place_units(
        s, s["cards"]["23"], [u], "22", {"--success": "yes"}, 7, {}, ["23"], prot, ["1/2"], None
    )
    assert new == ["Squad 1"] and s["units"]["Squad 1"]["area"] == "C2"
    assert [c["id"] for c in s["cards"]["23"]["cover"]] == ["C1", "C2"]  # no second marker


def test_set_area_without_the_unused_name_argument(board):
    """The unused name parameter is gone (review LOW, L449)."""
    s = board
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1, "field": False}]
    e = s["units"]["1/1"] = unit("22")
    commands.set_area(s, e, "C1")
    assert e["area"] == "C1"
    with pytest.raises(rules.Violation, match="Cover C9 does not exist"):
        commands.set_area(s, e, "C9")
    commands.set_area(s, e, "open")
    assert e["area"] == "open"
