"""L514-L526 (05.11.2026): tool gaps from the aborted Naktong run 1 and the BGG research of 05.11.2026."""

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


# ---- L515 Pinned/LAT enemy Fall Back without a card: redraw (Stead BGG 3514510), not No Action
def test_restricted_fall_back_says_redraw(board):
    """L552 (review T3): behaviour: no card without VOF towards the enemy edge: redraw, the team stays."""
    from fof import combat, enemy, rules

    s = board
    s.update(zug=2, phase="3.4.2", feind_taktik="Hasty", aktivitaet="Contact", kampagne={})
    for k in ("31", "32"):
        s["karten"][k]["extern"].append({"typ": "Incoming", "wert": -3, "quelle": "x"})
    s["einheiten"]["U1"] = unit("11")
    pt = unit("21", side="Feind", typ="Paralyzed Team", steps=1, vof=None, check_offen=True)
    combat.set_lat_values(pt, "Paralyzed Team")
    s["einheiten"]["PT"] = pt
    with pytest.raises(rules.Violation, match="draw the activity R# again"):
        enemy.cmd_enemy_action(s, ["PT", "Fall Back", "--ziel=31"])
    assert pt["karte"] == "21"


# ---- L516 3.7.2 list sorted by PC letter
def test_pc_list_sorted_by_letter(board):
    from fof import phase

    s = board
    s["karten"]["12"]["pc"] = "B"
    s["karten"]["21"]["pc"] = "A"
    s["einheiten"]["U1"] = unit("12")
    s["einheiten"]["U2"] = unit("21")
    prot = []
    phase._enter_3_7_2(s, prot)
    line = next(x for x in prot if x.startswith("PC markers to resolve"))
    assert line.index("21 (PC A)") < line.index("12 (PC B)")


# ---- L517 Z5 needs a valid target on the PDF card
def test_z5_needs_target_on_pdf_card(board):
    from fof import enemy

    s = board
    s["kampagne"] = {}
    s["feind_taktik"] = "Hasty"
    s["einheiten"]["G1"] = unit("31", side="Feind", ziel="21", typname="NKPA Squad")
    s["einheiten"]["U1"] = unit("22")
    row, _, _ = enemy.enemy_row(s, "G1")
    assert not row.startswith("Z5")
    s["einheiten"]["U2"] = unit("21")
    row, _, _ = enemy.enemy_row(s, "G1")
    assert row.startswith("Z5")


# ---- L518 6.3.4: the last unit under the VOF moves further away along the same PDF, the fire follows
def test_fire_follows_along_same_pdf(board):
    from fof import fire

    s = board
    s["einheiten"]["G1"] = unit("31", side="Feind", ziel="21", typname="NKPA Squad")
    s["einheiten"]["U1"] = unit("11")  # moved from 21 to 11
    prot = []
    fire.fire_after_move(s, "U1", prot, origin="21")
    assert s["einheiten"]["G1"]["ziel"] == "11"
    assert any("fire follows U1 along the same PDF" in x for x in prot)


# ---- L519 G! first fire on placement names the card count
def _g_contact(board, erfahrung, o):
    import copy

    from fof import contact

    s = board
    s.update(kampagne={}, aktivitaet="No Contact")
    s["karten"]["11"]["pc"] = "A"
    s["einheiten"]["1/1"] = unit("11")
    pk = {
        "name": "G! team",
        "spotted": True,
        "place_vof": True,
        "einheiten": [
            {
                "einheit": "Rifle Grenade Team",
                "typ": "Weapons Team",
                "vof_rating": "G",
                "reichweite": "L",
                "steps": 1,
                "platz": "max",
                "grenade_ranged": True,
                "erfahrung": erfahrung,
            }
        ],
    }
    contact.pc_contact_v4(s, "11", "A1", copy.deepcopy(pk), {"--richtung": "Front", **o})
    return s


def test_g_first_fire_card_count_text(board):
    """L552 (review T3): the prompt counts base 2 adjusted for Experience."""
    from fof import rules

    with pytest.raises(rules.Violation, match=r"draw 3 cards \(base 2, experience Veteran\)"):
        _g_contact(board, "Veteran", {})


# ---- L520 capture note from the setup
def test_prisoner_source_text():
    from fof import phase

    assert "Normandy" in phase.prisoner_source({})
    assert (
        phase.prisoner_source({"gefangene_nehmen": {"US": True, "Feind": False}})
        == "only US takes prisoners (campaign rules)"
    )


# ---- L521 package variant with R# bands from the mission table
def test_variant_bands_in_hint(board):
    """L552 (review T3): the variant prompt names the R# bands of the mission table."""
    from fof import contact, rules

    s = board
    s["kampagne"] = {}
    s["karten"]["11"]["pc"] = "A"
    s["einheiten"]["1/1"] = unit("11")
    pk = {
        "name": "Incoming",
        "spotted": True,
        "einheiten": [],
        "varianten": {"Artillery": {"r": "1-4/10", "wert": -4}, "Mortar": {"r": "5-10/10", "wert": -3}},
    }
    with pytest.raises(rules.Violation, match=r"R# 1-4/10 = Artillery, R# 5-10/10 = Mortar \(mission table\)"):
        contact.pc_contact_v4(s, "11", "A1", pk, {})


# ---- L522 Leader with a random squad (--leader-squad)
def test_leader_joins_drawn_squad(board):
    from fof import contact, rules

    s = board
    units = [
        {"einheit": "S", "typ": "Squad", "platz": "pb"},
        {"einheit": "S", "typ": "Squad", "platz": "pb"},
        {"einheit": "L", "typ": "HQ", "platz": "mit_zufaelligem"},
    ]
    with pytest.raises(rules.Violation, match="--leader-squad"):
        contact.contact_choose_places(s, [], [dict(u) for u in units], "22", {}, {}, [], [], [], [], {})
    places, uu = [], [dict(u) for u in units]
    contact.contact_choose_places(s, [], uu, "22", {"--leader-squad": "2"}, {}, places, [], [], [], {})
    assert uu[2]["_ref"] == 1 and places == ["22", "22", "22"]


# ---- L523 Pinned move also checks the asset list
def test_pinned_move_must_drop_assets(board):
    from fof import commands, rules

    s = board
    s["einheiten"]["U1"] = unit("21", status=[rules.PINNED], assets=["HC Smoke"])
    s["einheiten"]["U2"] = unit("22")
    with pytest.raises(rules.Violation, match="HC Smoke"):
        commands.check_move(s, s["einheiten"]["U1"], "U1", "22", "4.2.2a")


# ---- L524 Flip to Front of an Out-of-Ammo flip needs --ooa-flip=yes
def test_ooa_flip_rally_blocked(board):
    from types import SimpleNamespace

    from fof import commands, rules

    s = board
    z = unit(
        "21", typ="Weapons Team", status=[rules.FIRE_TEAM_SIDE], ooa_flip=True, munition={"typ": "MG", "punkte": 0}
    )
    s["einheiten"]["W1"] = z
    ctx = SimpleNamespace(z=z, o={}, target_name="W1", prot=[], success=None, akt="4.2.3f")
    with pytest.raises(rules.Violation, match="--ooa-flip"):
        commands._order_flip_to_front(s, ctx)
    ctx.o = {"--ooa-flip": "ja"}
    commands._order_flip_to_front(s, ctx)
    assert rules.FIRE_TEAM_SIDE not in z["status"]


# ---- L525 Max LOS of a package without PDF counts the trigger's view into an Incoming card
def test_max_los_no_pdf_uses_trigger_view():
    """L552 (review T3): a package without PDF looks INTO an Incoming card from the trigger (8.4.3): Max LOS reaches
    the Incoming card itself; with a PDF the unit needs LOS out of the card, so it stops one card short."""
    from conftest import card
    from fof import contact

    def place(place_vof):
        s = {
            "sicht": "tag",
            "typ": "offensiv",
            "zug": 1,
            "phase": "3.7.2",
            "einheiten": {},
            "kommandos": {},
            "karten": {f"{r}{c}": card(r, c) for r in (1, 2, 3, 4) for c in (1, 2, 3)},
            "protokoll": [],
            "optionen": {},
        }
        s["karten"]["31"]["extern"].append({"typ": "Incoming", "wert": -3, "quelle": "x"})
        u = {"einheit": "S", "typname": "S", "typ": "Squad", "platz": "max", "reichweite": "L"}
        places = []
        contact.contact_choose_places(s, [u], [u], "11", {}, {"place_vof": place_vof}, places, [], [], ["Front"], {})
        return places

    assert place(False) == ["31"] and place(True) == ["21"]


# ---- L526 jeep radio usable on the same card as the jeep (Stead BGG 3747382)
def test_jeep_radio_on_same_card():
    from fof import comms

    fo = {"karte": "21", "funk": [{"typ": "SCR610", "netz": "Arty FD", "eingebaut": "Jeep"}]}
    s = {"einheiten": {"Jeep": {"karte": "21"}, "FO": fo}}
    assert comms.radios_of(fo) == []
    assert len(comms.radios_of(fo, s=s)) == 1
    s["einheiten"]["Jeep"]["karte"] = "22"
    assert comms.radios_of(fo, s=s) == []
