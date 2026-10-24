"""Enemy behaviour: activity check hierarchy, enemy actions, snipers, spotters, leaders (8.x)."""

import dataclasses
import functools
import typing

from . import briefing, combat, commands, comms, contact, fire, geometry, options, rules, state


OFFENSIVE_TACTICS = ("Offensive Assault", "Assault", "Overrun")

# row ids of the Enemy Activity Check Hierarchy (L260, review H1: a translated literal made the Leader rows unreachable)
ROW_NONE = "none"
ROW_Z4 = "Z4"
ROW_Z6 = "Z6"

MINE_CHECK_REASON = "enemy enters a mined card"
# chart result naming both alternatives; resolved by the situation in _grenade_mode (L272)
CHART_GRENADE_OR_CF = "grenade attack (or concentrate fire)"


def enemy_segments(s):
    """(Enemy Higher HQ Event segment, Enemy Activity Check segment) of the mission's sequence of play: offensive
    3.4.1/3.4.2, defensive 3.2.1/3.2.2 [RULE 3.0 p.15]. L261 (review H2): derived from state.sop, not hard-wired."""
    sop = state.sop(s)
    event_seg = next(i for i, name in sop if name.startswith("Enemy Higher HQ Event"))
    check_seg = next(i for i, name in sop if name.startswith("Enemy Activity Check"))
    return event_seg, check_seg


def series_rules(s):
    """True when the series rules apply instead of the FM1 PAC run-1 simplifications: a company game (CO HQ on the
    board) or a mission that records the open rules questions (setup 'optionen'). One predicate for the former copies
    in enemy.py and contact.py (L262); the Activity Check additionally counts special rules (_Situation.has_los)."""
    return state.company(s) or "optionen" in s


def under_fire(s, e):
    """[PLAYER AID Key 'Under Fire'] a VOF on the card without unactivated Mines and Pending (BGG E35); a mine hit counts
    as an active VOF."""
    return fire.vof_against(s, e["karte"], "Feind", ignore_mines=True) is not None or bool(e.get("mine_hit"))


def fire_from_other_direction(s, kid, own_target):
    """[Enemy Activity Chart Z7] opposing fire reaches kid from a direction other than the own PDF (L263, review M28:
    directions are compared, not cards; Point Blank fire on the own card has no direction)."""
    own = geometry.direction(s, kid, own_target) if own_target != kid else None
    return any(geometry.direction(s, kid, k) != own for k in fire.pdfs_to(s, kid, "Feind"))


def best_free_cover(s, kid):
    """Cover markers on kid an enemy may enter (no US unit under them), highest value only; several = random choice by
    R# [RULE 8.6.1E p.66]. Empty list without a free marker (L264, review M26)."""
    free = state.free_cover(s, kid, side="Feind")
    if not free:
        return []
    top = max(c["wert"] for c in free)
    return [c for c in free if c["wert"] == top]


def move_enemy(s, n, target, prot, *, cover=True, exposed=True, how="moves", rule="8.6.1C"):
    """The one path for an enemy unit changing its card (L264, review M19-M23, M26, structure 1): ammo above capacity
    stays behind [RULE 8.11 p.68], a Grenade marker expires [RULE 7.10.4], Deep Bunker left [CSR 5], the highest free
    cover marker on the target card [RULE 8.6.1E p.66], Exposed [RULE 8.6.1C p.66] unless moving between fixed cover of
    adjacent cards [RULE 5.1.2 p.32], fire after the move [RULE 6.1.2] and the mine check of the target card [7.9.1,
    Normandy rules only, as before]. cover=False keeps the unit in the open (correction command, move towards a
    Casualty); exposed=False after a successful infiltration. Returns the cover marker entered or None."""
    e = s["einheiten"][n]
    origin = e["karte"]
    combat.ammo_surplus(s, n, e, origin, prot)  # L145 [RULE 8.11 p.68]
    commands.grenade_expires(
        s, e, n, prot
    )  # L92 [RULE 7.10.4] Grenade marker becomes a Grenade Miss on the origin card
    cv_from = geometry.cover_marker(s, e)
    e["karte"], e["bereich"] = target, "offen"
    e.pop("deep_bunker", None)  # cover ids are per card: the marker stays behind (review M19)
    chosen, best = None, []
    if cover:
        best = best_free_cover(s, target)
        if best:
            chosen = best[0]
            e["bereich"] = chosen["id"]
    fixed = bool(cv_from and chosen and cv_from["typ"] in rules.FIXED_COVER and chosen["typ"] in rules.FIXED_COVER)
    if exposed and not fixed:
        commands.mark(e, rules.EXPOSED)
    where = (
        f" under {chosen['id']} ({chosen['typ']} +{chosen['wert']})"
        + (f" (tie with {', '.join(c['id'] for c in best[1:])}: choose by R#)" if len(best) > 1 else "")
        if chosen
        else " (open)"
    )
    status = (
        f", from {cv_from['typ']}: not Exposed [5.1.2]"
        if exposed and fixed
        else (", Exposed" if exposed else ", not Exposed (infiltrated)")
    )
    prot.append(f"{n} {how} to {target}{where}{status} [{rule}" + (", 8.6.1E]" if chosen else "]"))
    fire.fire_after_move(s, n, prot, origin=origin)
    if state.is_v4(s):
        contact.request_mine_check(s, [n], target, prot, MINE_CHECK_REASON)
    return chosen


def grenade_target_check(s, zk, ze, attacker):
    """[RULE 7.10.1 p.54] the target of an enemy Grenade Attack is an opposing unit on the attacked card (L265, review
    M11: --unit was not validated, a -4 Grenade VOF could land on the attacker's own side)."""
    z = state.unit(s, ze)
    if z["seite"] == attacker["seite"]:
        raise rules.Violation(f"{ze} is on the attacker's own side, no target of a Grenade Attack [7.10.1]")
    if z.get("karte") != zk:
        raise rules.Violation(f"{ze} is on {z.get('karte')}, the Grenade Attack hits {zk} [7.10.1]")
    if z["typ"] == "Casualty":
        raise rules.Violation(f"{ze} is a Casualty, not a valid target [6.1.1]")
    return z


# ---- Enemy Activity Check Hierarchy as data (review structure 4)
#
# CHART: row key -> Row(label, columns, results[, with_leader]). columns/results are indexed by the chart column set:
# the defensive tactic (tactic_index: Delay 0, Hasty 1, Deliberate 2), the offensive tactic (Assault 0, Overrun 1), or a
# single entry for the LAT/Pinned and v4 rows. A label may name situation facts as {field} (format_map on _Situation).
# The *_ROWS tuples hold the hierarchy order: the first row whose predicate holds applies.

NA, SC, FB = "No Action", "Move into or Seek Cover", "Fall Back"
GA, GCF = "Grenade Attack", "Grenade Attack (or Concentrate Fire)"
ACF, ADV, INF = "Attempt to Concentrate Fire", "Advance Straight Ahead", "Infiltrate towards closest opposing unit"
NO_SHIFT = "No Action (Shift PDF not possible)"
SNIPER_FORTIFICATIONS = ("Foxholes", "Trench", "Bunker", "Pillbox", "Deep Bunker", "Cave")


class Row(typing.NamedTuple):
    label: str
    columns: tuple
    results: tuple
    with_leader: typing.Optional[tuple] = None  # (column, result) with a Good Order Leader present [8.9 p.67]


def _auto(label, action=NA):
    return Row(label, ("Auto",), ({"Auto": action},))


CHART = {
    # LAT/Pinned hierarchy without Leader; with_leader = the 'With Leader' column [8.9]
    "P1": Row(
        "P1 Pinned, opponent on card, without cover",
        ("5",),
        ({"1": NA, "2": SC, "3": "Rally", "4-5": FB},),
        ("4", {"1-2": SC, "3": "Rally", "4": FB}),
    ),
    "P2": Row(
        "P2 Pinned, opponent on card, under cover",
        ("5",),
        ({"1-2": NA, "3": "Rally", "4-5": FB},),
        ("3", {"1": NA, "2-3": "Rally"}),
    ),
    "P3": Row(
        "P3 Pinned, without cover",
        ("5",),
        ({"1-2": NA, "3": SC, "4": "Rally", "5": FB},),
        ("3", {"1": NA, "2": SC, "3": "Rally"}),
    ),
    "P4": Row("P4 Pinned, under cover", ("4",), ({"1-2": NA, "3": "Rally", "4": FB},), ("Auto", {"Auto": "Rally"})),
    "P6": Row("P6 Assault Team on opponent's card", ("2",), ({"1": NA, "2": GA},), ("Auto", {"Auto": GA})),
    "P7": Row(
        "P7 Assault Team not on opponent's card",
        ("2",),
        ({"1": NA, "2": "Infiltrate to nearest opponent"},),
        ("3", {"1": NA, "2-3": "Infiltrate to nearest opponent"}),
    ),
    "P8": Row(
        "P8 Fire Team without cover on opponent's card",
        ("5",),
        ({"1": NA, "2": SC, "3-5": FB},),
        ("4", {"1": NA, "2-3": SC, "4": FB}),
    ),
    "P9": Row(
        "P9 Fire Team under cover on opponent's card",
        ("5",),
        ({"1-2": NA, "3": GA, "4-5": FB},),
        ("3", {"1": NA, "2": GA, "3": FB}),
    ),
    "P10": Row("P10 Leader on Fire Team side", ("3",), ({"1": NA, "2-3": "Rally"},), ("Auto", {"Auto": "Rally"})),
    "P11": Row(
        "P11 Spotter/Sniper/Weapon Team on Fire Team side",
        ("2",),
        ({"1": NA, "2": "Rally"},),
        ("Auto", {"Auto": "Rally"}),
    ),
    "P12": Row(
        "P12 Litter Team with Casualty",
        ("3",),
        ({"1": NA, "2-3": "Fall Back with Casualty"},),
        ("Auto", {"Auto": "Fall Back with Casualty"}),
    ),
    "P13": Row(
        "P13 Litter Team with Casualty in LOS",
        ("3",),
        ({"1": NA, "2-3": "Move towards closest Casualty"},),
        ("2", {"1": NA, "2": "Move towards closest Casualty"}),
    ),
    "P14": Row(
        "P14 Litter Team without Casualty in LOS",
        ("3",),
        ({"1-2": NA, "3": "Rally"},),
        ("2", {"1": NA, "2": "Rally"}),
    ),
    "P15": Row("P15 Paralyzed Team", ("Auto",), ({"Auto": NA},), ("2", {"1": NA, "2": "Rally"})),
    "none_lat": _auto("none (no LAT row applies)"),
    # Defensive hierarchy, columns Delay / Hasty / Deliberate
    "Z1": Row(
        "Z1 opponent on card, without cover",
        ("5", "4", "3"),
        (
            {"1": NA, "2": SC, "3-4": FB, "5": GA},
            {"1": NA, "2": SC, "3": FB, "4": GA},
            {"1": SC, "2": FB, "3": GA},
        ),
    ),
    "Z2": Row(
        "Z2 opponent on card, under cover",
        ("4", "3", "3"),
        ({"1": NA, "2-3": FB, "4": GA}, {"1": NA, "2": FB, "3": GA}, {"1": NA, "2-3": GA}),
    ),
    "Z3": Row(
        "Z3 A/G!/H with Out of Ammo",
        ("Auto", "3", "2"),
        ({"Auto": FB}, {"1": NA, "2-3": FB}, {"1": NA, "2": FB}),
    ),
    # [FM1 p.36] Deliberate Defense: 'ignore a "Remove unit, place PC marker" action result and do "No Action" instead'
    "Z4_fm1": _auto("Z4 not under fire, no LOS to opponents (special rule FM1 p.36: No Action instead of Remove)"),
    "Z4_u1": _auto(
        "Z4 not under fire, no LOS to opponents (special rule FM1 p.36 also in Run 2/3: No Action){u1_note}"
    ),
    ROW_Z4: _auto("Z4 not under fire, no LOS to opponents", "Remove unit; place PC marker"),
    "Z5": Row(
        "Z5 not under fire, target along PDF",
        ("3", "2", "Auto"),
        ({"1-2": NA, "3": GCF}, {"1": NA, "2": GCF}, {"Auto": GCF}),
    ),
    ROW_Z6: Row(
        "Z6 under fire, without cover",
        ("5", "5", "3"),
        (
            {"1": NA, "2": SC, "3-4": FB, "5": GCF},
            {"1": NA, "2-3": SC, "4": FB, "5": GCF},
            {"1-2": SC, "3": GCF},
        ),
    ),
    "Z7": Row(
        "Z7 under fire from a direction other than own PDF",
        ("5", "5", "4"),
        (
            {"1": NA, "2": GCF, "3": "Shift PDF", "4-5": FB},
            {"1": NA, "2": GCF, "3-4": "Shift PDF", "5": FB},
            {"1": NA, "2": GCF, "3-4": "Shift PDF"},
        ),
    ),
    "Z8": Row(
        "Z8 A/H unit that has opened fire{u4_note}",
        ("3", "3", "Auto"),
        ({"1-2": NA, "3": ACF}, {"1": NA, "2-3": ACF}, {"Auto": ACF}),
    ),
    "Z9": Row(
        "Z9 Trading fire, own VOF better",
        ("3", "2", "3"),
        ({"1-2": NA, "3": GCF}, {"1": NA, "2": GCF}, {"1": NA, "2-3": GCF}),
    ),
    "Z10": Row(
        "Z10 Trading fire, own VOF equal or worse",
        ("3", "5", "2"),
        ({"1": NA, "2": GCF, "3": FB}, {"1-2": NA, "3-4": GCF, "5": FB}, {"1": NA, "2": GCF}),
    ),
    ROW_NONE: _auto("none (no row applies)"),
    # [PLAYER AID] 'Also applies to a G! rated unit on a card with no PDF, but with a target in LOS'
    "Z5_g": Row(
        "Z5 G! unit without PDF with target in LOS (player aid)",
        ("3", "2", "Auto"),
        ({"1-2": NA, "3": GCF}, {"1": NA, "2": GCF}, {"Auto": GCF}),
    ),
    # L67/L86 (K28) [RULE 8.9 p.67] Leader with Rifle Grenades as a G! unit along his card's PDF
    "Z5_leader": Row(
        "Z5 Leader with Rifle Grenade ({rounds} rounds) as G! along the PDF to {rgz} [8.9 p.67]",
        ("3", "2", "Auto"),
        ({"1-2": NA, "3": GA}, {"1": NA, "2": GA}, {"Auto": GA}),
    ),
    "Z6_leader": Row(
        "Z6 Leader with Rifle Grenade under fire, no cover (as G!, target {rgz}) [8.9 p.67, K28]",
        ("5", "5", "3"),
        (
            {"1": NA, "2": SC, "3-4": FB, "5": GA},
            {"1": NA, "2-3": SC, "4": FB, "5": GA},
            {"1-2": SC, "3": GA},
        ),
    ),
    "Z7_leader": Row(
        "Z7 Leader with Rifle Grenade under fire from a direction other than his card's PDF (as G!, target {rgz}; "
        "Shift PDF lapses without a VOF = No Action) [8.9 p.67, K28]",
        ("5", "5", "4"),
        (
            {"1": NA, "2": GA, "3": NO_SHIFT, "4-5": FB},
            {"1": NA, "2": GA, "3-4": NO_SHIFT, "5": FB},
            {"1": NA, "2": GA, "3-4": NO_SHIFT},
        ),
    ),
    "Z10_leader": Row(
        "Z10 Leader with Rifle Grenade in a firefight (as G! -4, target {rgz}; compare with the best opposing VOF on "
        "the chart) [8.9 p.67, K28]",
        ("3", "2", "3"),
        ({"1-2": NA, "3": GA}, {"1": NA, "2": GA}, {"1": NA, "2-3": GA}),
    ),
    # [PLAYER AID Enemy Offensive Activity Check Hierarchy] columns Assault / Overrun
    "O1": Row(
        "O1 on a card with opposing units, without cover",
        ("5", "6"),
        ({"1": NA, "2-3": SC, "4": FB, "5": GA}, {"1": NA, "2": FB, "3-4": ADV, "5-6": GA}),
    ),
    "O2": Row(
        "O2 on a card with opposing units, under cover",
        ("5", "6"),
        ({"1": NA, "2": FB, "3-5": GA}, {"1": NA, "2": FB, "3-4": ADV, "5-6": GA}),
    ),
    "O3": Row("O3 A/G!/H with Out of Ammo", ("3", "2"), ({"1-2": NA, "3": FB}, {"1": NA, "2": ADV})),
    # L89 [RULE 8.9 p.67] Leader with Rifle Grenade as a G! unit with a target along the card's PDF (table O4)
    "O4_leader": Row(
        "O4 Leader with Rifle Grenade ({rounds} rounds) as G! along the PDF to {rgz} [8.9 p.67]",
        ("4", "Auto"),
        ({"1": NA, "2-3": GA, "4": ADV}, {"Auto": GA}),
    ),
    # L89: player aid O4: Assault 1/4 No Action, 2-3/4 Grenade Attack, 4/4 Advance; Overrun Auto Grenade Attack
    "O4": Row(
        "O4 A/G!/H with a valid target along the PDF",
        ("4", "Auto"),
        ({"1": NA, "2-3": GCF, "4": ADV}, {"Auto": GCF}),
    ),
    "O5": Row("O5 all other cases", ("4", "3"), ({"1": NA, "2-3": INF, "4": ADV}, {"1": INF, "2-3": ADV})),
    # v4 rows the series chart does not know (8.8, 8.10, 8.11)
    "O-A": _auto("O-A Out-of-Ammo team on Fire Team side, Spotted: Fall Back instead of hierarchy [8.11 p.68]", FB),
    "S3": _auto("S3 Sniper in a field fortification stays put even when Spotted [8.8 Exception]"),
    "S1": _auto("S1 Sniper Spotted: Fall Back until out of LOS, then Unspotted again [8.8 p.67]", FB),
    "S2": _auto("S2 Sniper Unspotted: fires by target priority or does nothing [8.8 p.67]"),
    "SP0": _auto("SP0 Spotter without fire missions: remove [8.10 p.68]", "Remove (no fire missions left)"),
    "SP2": _auto("SP2 Spotter without target in LOS: nothing [8.10 p.68]"),
    "SP1": _auto(
        "SP1 Spotter: Call for Fire on {spotter_target} ({spotter_cards} cards{target_marker_note}, burst symbol; "
        "experience already included) [8.10 p.68]",
        "Call for Fire",
    ),
}


class _Situation:
    """Facts about one enemy unit for the chart predicates, each computed on first use (several need LOS checks)."""

    def __init__(self, s, n):
        self.s, self.n = s, n
        self.e = s["einheiten"][n]
        self.kid = self.e["karte"]
        self.typ = self.e["typ"]
        self.row_id = None  # id of the basic row, set by enemy_row

    def __getitem__(self, key):  # str.format_map on the chart labels
        return getattr(self, key)

    @functools.cached_property
    def opp(self):
        return bool(state.valid_target(self.s, self.kid, "Feind"))

    @functools.cached_property
    def cover(self):
        return self.e.get("bereich", "offen") != "offen"

    @functools.cached_property
    def under_fire(self):
        return under_fire(self.s, self.e)

    @functools.cached_property
    def firing(self):
        return fire.is_firing(self.e)

    @functools.cached_property
    def pinned(self):
        return state.pinned(self.e)

    @functools.cached_property
    def ft_side(self):
        return state.fire_team_side(self.e)

    @functools.cached_property
    def lat_like(self):
        """Pinned, LAT or Fire Team side: the LAT/Pinned hierarchy applies."""
        return self.pinned or state.is_lat(self.e) or self.ft_side

    @functools.cached_property
    def out_of_ammo_agh(self):
        return bool(self.e.get("out_of_ammo")) and self.e.get("vof_rating") in ("A", "G", "H")

    @functools.cached_property
    def has_los(self):
        s, kid = self.s, self.kid
        los_ = bool(fire.fire_candidates(s, self.n))
        if series_rules(s) or s.get("sonderregeln"):
            # [PLAYER AID Enemy Activity Hierarchy] 'no LOS to an opposing unit' is pure LOS (5.2), independent of
            # weapon range and bunker fire arc [RULE 5.3.2 p.37 'Being in a Bunker ... does not affect a unit's LOS']
            los_ = los_ or any(
                geometry.los(
                    s, kid, k, ha=geometry.card_height_bonus(s, kid, "Feind"), hb=geometry.card_height_bonus(s, k, "US")
                )[0]
                for k in s["karten"]
                if k != kid and state.units_on(s, k, "US")
            )
        return los_

    @functools.cached_property
    def quiet(self):
        """Z4: not under fire, no LOS to opponents, not firing."""
        return not self.under_fire and not self.has_los and not self.firing

    @functools.cached_property
    def casualty_in_los(self):
        s, kid = self.s, self.kid
        return any(c.get("casualties_feind") and geometry.los(s, kid, k)[0] for k, c in s["karten"].items() if k != kid)

    @functools.cached_property
    def a_rating(self):
        s = self.s
        return ("A", "H", "A/S") if ("optionen" in s and state.option(s, "U4_as_zaehlt_als_a")) else ("A", "H")

    @functools.cached_property
    def own_vof_better(self):
        """Z9: own VOF better than the opposing one (None with a mine hit but no active Mines marker, L266)."""
        e, kid = self.e, self.kid
        own_unit = rules.VOF_VALUE.get(fire.current_vof_rating(e, e["ziel"] == kid), 0)
        opposing = fire.vof_against(self.s, kid, "Feind")
        return opposing is not None and own_unit < opposing[1]

    @functools.cached_property
    def rgz(self):
        """Target card of a Leader's Rifle Grenade along his card's PDF (v4), else None."""
        return leader_rg_target(self.s, self.n) if state.is_v4(self.s) else None

    @functools.cached_property
    def leader_row(self):
        # L260 (review H1): the Leader rows compared with the untranslated id 'keine' and were never reached. A Leader
        # (no VOF rating, never firing) falls through the chart to 'none' unless he is under fire without cover (Z6);
        # that generic Z6 is replaced by the Leader's Z6 (K28), the other cases come from 'none'.
        return bool(self.rgz) and self.row_id in (ROW_NONE, ROW_Z6)

    @functools.cached_property
    def spotter_target(self):
        return spotter_target(self.s, self.n)

    @property
    def spotter_cards(self):
        return self.e.get("karten_folge", 3) + (1 if self._target_marker == self.spotter_target else 0)

    @property
    def target_marker_note(self):
        return " incl. +1 Target marker" if self._target_marker == self.spotter_target else ""

    @property
    def _target_marker(self):
        return self.s.get("feind_target", {}).get(self.e.get("typname"))

    @property
    def rounds(self):
        return self.e.get("rifle_grenades")

    @property
    def u1_note(self):
        return state.open_reading(self.s, "U1_remove_pc_no_action")

    @property
    def u4_note(self):
        return state.open_reading(self.s, "U4_as_zaehlt_als_a") if self.e.get("vof_rating") == "A/S" else ""


def _is_sniper_row(c):
    return is_sniper(c.e)


V4_ROWS = (
    ("O-A", lambda c: c.e.get("ooa_fallback") and c.ft_side and c.e.get("spotted")),
    (None, lambda c: c.lat_like),  # the LAT/Pinned hierarchy applies
    ("S3", lambda c: _is_sniper_row(c) and (geometry.cover_marker(c.s, c.e) or {}).get("typ") in SNIPER_FORTIFICATIONS),
    ("S1", lambda c: _is_sniper_row(c) and c.e.get("spotted")),
    ("S2", _is_sniper_row),
    ("SP0", lambda c: c.e.get("spotter") and c.e.get("missionen", 0) <= 0),
    ("SP2", lambda c: c.e.get("spotter") and not c.spotter_target),
    ("SP1", lambda c: c.e.get("spotter")),
)

LAT_ROWS = (
    ("P1", lambda c: c.pinned and c.opp and not c.cover),
    ("P2", lambda c: c.pinned and c.opp),
    ("P3", lambda c: c.pinned and not c.cover),
    ("P4", lambda c: c.pinned),
    ("P6", lambda c: c.typ == "Assault Team" and c.opp),
    ("P7", lambda c: c.typ == "Assault Team"),
    ("P8", lambda c: c.typ == "Fire Team" and c.opp and not c.cover),
    ("P9", lambda c: c.typ == "Fire Team" and c.opp),
    ("P10", lambda c: c.ft_side and state.is_hq(c.e)),
    ("P11", lambda c: c.ft_side),
    ("P12", lambda c: c.typ == "Litter Team" and state.card(c.s, c.kid).get("casualties_feind")),
    ("P13", lambda c: c.typ == "Litter Team" and c.casualty_in_los),
    ("P14", lambda c: c.typ == "Litter Team"),
    ("P15", lambda c: c.typ == "Paralyzed Team"),
    ("none_lat", lambda _c: True),
)

DEFENSIVE_ROWS = (
    ("Z1", lambda c: c.opp and not c.cover),
    ("Z2", lambda c: c.opp),
    ("Z3", lambda c: c.out_of_ammo_agh),
    ("Z4_fm1", lambda c: c.quiet and c.s.get("sonderregeln", {}).get("remove_pc_no_action")),
    ("Z4_u1", lambda c: c.quiet and "optionen" in c.s and state.option(c.s, "U1_remove_pc_no_action")),
    (ROW_Z4, lambda c: c.quiet),
    ("Z5", lambda c: not c.under_fire and c.firing),
    (ROW_Z6, lambda c: c.under_fire and not c.cover),
    ("Z7", lambda c: c.under_fire and c.firing and fire_from_other_direction(c.s, c.kid, c.e["ziel"])),
    (
        "Z8",
        lambda c: (
            c.firing and c.e.get("vof_rating") in c.a_rating and c.e["ziel"] != c.kid and not c.e.get("konzentriert")
        ),
    ),
    ("Z9", lambda c: c.under_fire and c.firing and c.own_vof_better),
    ("Z10", lambda c: c.under_fire and c.firing),
    (ROW_NONE, lambda _c: True),
)

# v4 additions to the defensive chart for Good Order units: a G! unit without PDF, a Leader with Rifle Grenades
SPECIAL_ROWS = (
    (
        "Z5_g",
        lambda c: (
            state.is_v4(c.s)
            and c.e.get("vof_rating") == "G"
            and not c.firing
            and c.row_id in (ROW_Z4, ROW_NONE)
            and fire_candidates_g(c.s, c.n)
        ),
    ),
    ("Z5_leader", lambda c: c.leader_row and not c.under_fire),
    ("Z6_leader", lambda c: c.leader_row and not c.cover),
    ("Z7_leader", lambda c: c.leader_row and fire_from_other_direction(c.s, c.kid, c.rgz)),
    ("Z10_leader", lambda c: c.leader_row),
)

OFFENSIVE_ROWS = (
    ("O1", lambda c: c.opp and not c.cover),
    ("O2", lambda c: c.opp),
    ("O3", lambda c: c.out_of_ammo_agh),
    ("O4_leader", lambda c: c.rgz),
    (
        "O4",
        lambda c: (
            c.e.get("vof_rating") in ("A", "G", "H")
            and (c.firing or (c.e.get("vof_rating") == "G" and fire_candidates_g(c.s, c.n)))
        ),
    ),
    ("O5", lambda _c: True),
)


def _first_row(rows, sit):
    """Key of the first row whose predicate holds (None: no row of this table applies)."""
    for key, holds in rows:
        if holds(sit):
            return key
    return None


def chart_row(sit, key, column=0):
    """(row text, R# column, results) of a chart row for the situation; column = index of the tactic column (a row
    with a single entry applies to every tactic)."""
    row = CHART[key]
    i = column if len(row.columns) > 1 else 0
    return row.label.format_map(sit), row.columns[i], dict(row.results[i])


def tactic_index(s):
    """Column index of the enemy tactic on the Enemy Activity Check Hierarchy: Delay 0, Hasty 1, Deliberate 2."""
    return {"Delay": 0, "Hasty": 1, "Deliberate": 2}.get(s.get("feind_taktik", "Hasty"), 2)


def _basic(sit):
    """Key of the basic row: LAT/Pinned hierarchy or the defensive hierarchy."""
    sit.under_fire  # noqa: B018  the VOF and LOS checks run in the former order (their LOS notes keep their order)
    if sit.lat_like:
        return _first_row(LAT_ROWS, sit)
    sit.has_los  # noqa: B018
    return _first_row(DEFENSIVE_ROWS, sit)


def enemy_row(s, n):
    """Row of the Enemy Activity Check for unit n: v4 rows (Sniper 8.8, Spotter 8.10, Out of Ammo 8.11), the basic row,
    the With Leader column (8.9), the Offensive hierarchy (counterattack), G! unit without PDF, Leader with Rifle
    Grenades. Returns (row text, R# column, {R# band: action})."""
    sit = _Situation(s, n)
    offensive = s.get("feind_taktik") in OFFENSIVE_TACTICS
    if state.is_v4(s) or offensive:
        key = _first_row(V4_ROWS, sit)
        if key:
            return chart_row(sit, key)
    key = _basic(sit)
    T = tactic_index(s)
    row_, column, result = chart_row(sit, key, 0 if sit.lat_like else T)
    sit.row_id = row_.split(" ")[0]
    with_leader = CHART[key].with_leader
    if with_leader and leader_present(s, sit.e):
        return row_ + " (With Leader, 8.9)", with_leader[0], dict(with_leader[1])
    if sit.lat_like:
        return row_, column, result
    if offensive:
        z, sp, er = chart_row(sit, _first_row(OFFENSIVE_ROWS, sit), int(s["feind_taktik"] == "Overrun"))
        return z + f" [Enemy Offensive Activity Check Hierarchy, {s['feind_taktik']}]", sp, er
    special = _first_row(SPECIAL_ROWS, sit)
    if special:
        return chart_row(sit, special, T)
    return row_, column, result


def prepare_enemy_check(s, prot):
    if state.is_v4(s):
        for n, e in s["einheiten"].items():
            if (
                e["seite"] == "Feind"
                and e.get("leader")
                and not state.fire_team_side(e)
                and not [m for m in state.units_on(s, e["karte"], "Feind") if m != n]
            ):
                commands.mark(e, rules.FIRE_TEAM_SIDE)
                prot.append(f"{n}: Leader alone on {e['karte']}, flipped to Fire Team side [8.9 p.67]")
    enemies = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind"]
    for n in enemies:
        s["einheiten"][n]["check_offen"] = True
    # L60: units from an Enemy Higher HQ Event this turn do not check again [RULE 3.4.1 p.16]
    without = (
        [n for n in s.get("ereignis_einheiten", []) if n in enemies]
        if s.get("ereignis_erledigt") == [s["zug"], enemy_segments(s)[0]]
        else []
    )
    for n in without:
        s["einheiten"][n]["check_offen"] = False  # L281: the one place for it (events.py wrote it before, uselessly)
    if without:
        prot.append(
            f"no Activity Check for {', '.join(without)} (already affected by the Enemy Higher HQ Event) [3.4.1 p.16]"
        )
        enemies = [n for n in enemies if n not in without]
        if not enemies:
            prot.append("no further enemies to check")
            return
    cards = sorted({s["einheiten"][n]["karte"] for n in enemies})
    if not enemies:
        prot.append("no enemies on the board, Activity Check skipped")
    elif len(cards) > 1:
        prot.append(
            f"card order by R# (column {len(cards)}) for {', '.join(cards)}; per card first Pinned/LAT, then Good Order, then Leader; then fof.py enemycheck [8.6.2]"
        )
    else:
        prot.append(f"Activity Check for {', '.join(enemies)}: fof.py enemycheck [8.6.2]")


def auto_command(s, n, action):
    """Executable enemyaction line for an Auto result; a Spotter's Call for Fire carries its target as an option
    (L267, review M25: the target used to sit inside the quoted action string with the German key)."""
    cmd = f'fof.py enemyaction "{n}" "{action}"'
    if action.lower().startswith("call for fire"):
        z = spotter_target(s, n)
        return cmd + (f" --target={z}" if z else " --target=<card>") + " --success=yes|no"
    return cmd + " ..."


def cmd_enemy_check(s, args):
    check_seg = enemy_segments(s)[1]
    if s["phase"] != check_seg:
        print(f"Note: Activity Check belongs in {check_seg}, currently {s['phase']}")
    for n, e in s["einheiten"].items():
        if e["seite"] != "Feind":
            continue
        row_, column, result = enemy_row(s, n)
        print(
            f"{n} on {e['karte']}"
            + ("" if e.get("check_offen") else " (check done)")
            + f": {row_} [Enemy Activity Chart, {s.get('feind_taktik', 'Hasty')}]"
        )
        if column == "Auto":
            action = next(iter(result.values()))  # an Auto row has exactly one result
            print(f"  Auto: {action}   {auto_command(s, n, action)}")
        else:
            print(f"  R# column {column}: " + "; ".join(f"{k} = {v}" for k, v in result.items()))
            print(f'  then fof.py enemyaction "{n}" "<action>" [--target=K] [--success=yes|no] [--unit=<target unit>]')


def cf_stack(s, ze):
    """[RULE 7.11.2 p.56] Target under a cover marker: CF affects all units under that marker."""
    z = s["einheiten"][ze]
    b = z.get("bereich", "offen")
    if b in (None, "offen"):
        return [ze]
    return [
        n
        for n, e in s["einheiten"].items()
        if e.get("karte") == z.get("karte") and e.get("seite") == z.get("seite") and e.get("bereich") == b
    ]


def _enemy_no_action(s, ctx):
    """cmd_feindaktion: a.startswith('no action')"""
    ctx.prot.append(f"{ctx.n}: No Action, fire continues [Chart]")


def _is_no_action(s, ctx):
    return ctx.a.startswith("no action")


def _enemy_call_for_fire(s, ctx):
    """cmd_feindaktion: a.startswith('call for fire')"""
    if not ctx.e.get("spotter") or ctx.e.get("missionen", 0) <= 0:
        raise rules.Violation(f"{ctx.n} is not a Spotter with fire missions")
    target = ctx.o.get("--ziel")
    if not target:
        raise rules.Violation("--target=<card by priority (enemycheck)>")
    tk = s.get("feind_target", {}).get(ctx.e.get("typname"))
    if ctx.o.get("--erfolg") not in ("ja", "nein"):
        raise rules.Violation(
            f"Call for Fire: {ctx.e.get('karten_folge', 3) + (1 if tk == target else 0)} cards, Burst symbol; --success=yes|no [8.10 p.68]"
        )
    if ctx.o["--erfolg"] == "ja":
        state.card(s, target).setdefault("extern", []).append(
            {"typ": "Pending", "wert": ctx.e.get("fm_wert", -3), "quelle": ctx.n, "seite": "Feind"}
        )
        ctx.e["missionen"] -= 1
        s.setdefault("feind_target", {})[ctx.e.get("typname")] = target
        ctx.prot.append(
            f"{ctx.n}: Pending Fire Mission ({ctx.e.get('fm_wert', -3):+d}) on {target}, enemy Target marker moved there; becomes active in 3.7.1; {ctx.e['missionen']} mission(s) left [8.10 p.68, 3.7.1]"
        )
    else:
        ctx.prot.append(f"{ctx.n}: Call for Fire failed, no mission used up (BGG E19)")


def _is_call_for_fire(s, ctx):
    return ctx.a.startswith("call for fire")


def _enemy_no_fire_missions(s, ctx):
    """cmd_feindaktion: 'keine feuerauftraege' in a or 'no fire missions' in a"""
    remove_enemy(s, ctx.n, ctx.prot, reason="Spotter without fire missions [8.10 p.68]")


def _is_no_fire_missions(s, ctx):
    return "keine feuerauftraege" in ctx.a or "no fire missions" in ctx.a


def _enemy_advance(s, ctx):
    """cmd_feindaktion: 'advance' in a"""
    c = state.card(s, ctx.e["karte"])
    target = geometry.card_at(s, c["reihe"] - 1, c["spalte"])
    if c["reihe"] == geometry.first_card_row(s):
        if s.get("feind_taktik") == "Overrun":
            remove_enemy(s, ctx.n, ctx.prot, reason="Overrun: Advance from row 1 leaves the board")
            return
        target = ctx.o.get("--ziel")
        if (
            not target
            or not geometry.adjacent(s, ctx.e["karte"], target)
            or (state.card(s, target).get("staging") and not state.option(s, "U24_assault_in_staging"))
        ):
            raise rules.Violation(
                "Assault from row 1: --target=<adjacent card towards the nearest US unit>"
                + state.open_reading(s, "U24_assault_in_staging")
            )
    if not target:
        # L268 (review M23): no card straight ahead used to be a silent no-op that still closed the check
        missing = state.card_id(c["reihe"] - 1, c["spalte"])
        raise rules.Violation(
            f"Advance Straight Ahead of {ctx.n}: card {missing} (row {c['reihe'] - 1}, column {c['spalte']}) does not "
            f"exist; extend the map (fof.py extend {c['reihe'] - 1} {c['spalte']} <type>) or redraw the result "
            f"[8.4.5, 8.6.1]"
        )
    # L169 [RULE 8.6.1E p.66] advancing enemies take the highest free cover marker on the target card
    move_enemy(s, ctx.n, target, ctx.prot, how="advances straight ahead", rule="Offensive Hierarchy, 8.6.1C")


def _is_advance(s, ctx):
    return "advance" in ctx.a


def _enemy_seek_cover(s, ctx):
    """cmd_feindaktion: 'seek cover' in a or 'move into' in a"""
    kk = state.card(s, ctx.e["karte"])
    best = best_free_cover(s, ctx.e["karte"])  # L264 (review M26): highest value, not the first marker
    if best and ctx.e.get("bereich", "offen") == "offen":
        commands.grenade_expires(s, ctx.e, ctx.n, ctx.prot)  # L171 [RULE 7.10.4] moving within the card
        ctx.e["bereich"] = best[0]["id"]
        commands.mark(ctx.e, rules.EXPOSED)
        ctx.prot.append(
            f"{ctx.n} moves under {best[0]['id']} ({best[0]['typ']} +{best[0]['wert']})"
            + (f" (tie with {', '.join(c['id'] for c in best[1:])}: choose by R#)" if len(best) > 1 else "")
            + ", Exposed [8.6.1C, 8.6.1E]"
        )
    else:
        if ctx.o.get("--erfolg") not in ("ja", "nein"):
            n_cards = (kk.get("cover_draw") or 2) + {"Green": -1, "Veteran": 1}.get(comms.experience(ctx.e), 0)
            n_cards += leader_cards(s, ctx.e)  # L142 [RULE 8.9 p.67]
            raise rules.Violation(
                f"Seek Cover: draw {n_cards} cards (cover draw of the card, experience {comms.experience(ctx.e)}{', Leader +1' if leader_cards(s, ctx.e) else ''}), word 'Cover'; --success=yes|no"
            )
        if ctx.o["--erfolg"] == "ja":
            present = len([c for c in kk.get("cover", []) if not c.get("feld")])
            if kk.get("cover_max") is not None and present >= kk["cover_max"]:
                # L133 [RULE 5.3 p.36] Cover Potential of the card also limits enemy Seek Cover
                ctx.prot.append(
                    f"{ctx.n}: Seek Cover drawn successfully, but {ctx.e['karte']} has reached its Cover Potential ({kk['cover_max']}): no new marker [5.3 p.36]"
                )
                return
            gt, gw = "Basic Cover", 1
            if kk.get("gebaeude_tabelle") and state.is_v4(s):
                # L219 [Normandy CSR 8 p.15 'When cover is found on Village, Farm, Cemetery and Church cards, it may be a
                # building or Basic +1 Cover']: building table also for enemy Seek Cover; enemies never take upper stories
                if not ctx.o.get("--gebaeude"):
                    raise rules.Violation(
                        "Enemy Seek Cover on Village/Farm/Cemetery/Church: R# column 8 on the building table, --building=<R#> [CSR 8 p.15]"
                    )
                gt, gw, _upper = contact.building_cover(
                    s, ctx.e["karte"], ctx.e, ctx.o["--gebaeude"], ctx.o.get("--gebaeude_wert")
                )
            cid = commands.new_cover_marker(s, ctx.e["karte"], gt, gw)
            if gt != "Basic Cover":
                next(c_ for c_ in kk["cover"] if c_["id"] == cid)["feld"] = False
            commands.grenade_expires(s, ctx.e, ctx.n, ctx.prot)  # L171 [RULE 7.10.4] moving within the card
            ctx.e["bereich"] = cid
            commands.mark(ctx.e, rules.EXPOSED)
            ctx.prot.append(
                f"{ctx.n}: new cover marker {cid} ({gt} +{gw}) on {ctx.e['karte']}, {ctx.n} under it, Exposed [4.2.2e, CSR 8]"
            )
        else:
            ctx.prot.append(f"{ctx.n}: Seek Cover failed")


def _is_seek_cover(s, ctx):
    return "seek cover" in ctx.a or "move into" in ctx.a


def _enemy_fall_back(s, ctx):
    """cmd_feindaktion: 'fall back' in a"""
    target = ctx.o.get("--ziel")
    off = fall_back_offmap(s, ctx.e)
    if target == "off-map":
        if not off:
            raise rules.Violation(
                f"{ctx.n} is neither at the enemy edge with an empty position behind it nor beyond the left/right boundary: no off-map Fall Back [8.6.3]"
            )
        remove_enemy(s, ctx.n, ctx.prot, reason=f"Fall Back off-map ({off}) [8.6.3 priority 1, K26]")
    else:
        if off:
            raise rules.Violation(
                f"Fall Back: off-map has priority 1 ({off}), before extension cards: --target=off-map [8.6.3, K26]"
            )
        if not target:
            raise rules.Violation(
                "Fall Back: --target=<card> (priority: card outside every US LOS; highest cover value incl. available cover markers; random on a tie) [8.6.3]"
            )
        state.card(s, target)
        if not geometry.adjacent(s, ctx.e["karte"], target):
            raise rules.Violation(f"{target} not adjacent to {ctx.e['karte']}")
        commands.diagonal_pdf_check(s, ctx.e, target)  # L131 [RULE 5.1.2 p.32]
        best = fall_back_candidates(s, ctx.e)  # L141 [RULE 8.6.3 p.66] priorities 2 and 3
        if not best and restricted_mover(ctx.e):
            raise rules.Violation(
                f"Fall Back of {ctx.n}: no adjacent card towards the enemy edge without VOF (Pinned/Paralyzed/Litter, 4.2.5, E90): "
                f'no movement, book fof.py enemyaction "{ctx.n}" "No Action" [RULE 4.2.5 p.26, 8.6.1C p.66]'
            )
        if best and target not in best:
            raise rules.Violation(
                f"Fall Back of {ctx.n}: by 8.6.3 to {', '.join(best)} (towards the enemy edge; first out of every US LOS, then highest cover value incl. free markers; tie: R#) [RULE 8.6.3 p.66]"
            )
        move_enemy(s, ctx.n, target, ctx.prot, how="falls back", rule="8.6.3")


def fall_back_offmap(s, e):
    """[RULE 8.6.3] Priority 1 'Off-map if unit is at their edge of the map or beyond the Left or Right boundaries'.
    K26 (BGG Shonai_Dweller 3458315, 3498658): off-map comes before extension cards; it is possible as soon as one of the
    three positions towards the enemy edge has no card (also diagonally, also beyond a side boundary).
    Returns the reason or None."""
    c = state.card(s, e["karte"])
    top = state.top_row(s)
    cols = [v["spalte"] for v in s["karten"].values() if not v.get("ausserhalb")]
    if c["reihe"] <= top and (c["spalte"] < min(cols) or c["spalte"] > max(cols)):
        return "beyond the left/right mission boundary"
    if c["reihe"] < top:
        return None
    empty = [
        state.card_id(c["reihe"] + 1, sp)
        for sp in (c["spalte"] - 1, c["spalte"], c["spalte"] + 1)
        if geometry.card_at(s, c["reihe"] + 1, sp) is None
    ]
    return f"at the enemy edge, no card at {', '.join(empty)}" if empty else None


def _is_fall_back(s, ctx):
    return "fall back" in ctx.a


def _grenade_mode(s, ctx):
    """Which of the two chart alternatives applies: 'grenade' (Point Blank target on the own card, G! unit, Leader with
    Rifle Grenades) or 'concentrate'. The chart result 'Grenade Attack (or Concentrate Fire)' names both; the engine
    prints it as the Auto command, so it is resolved by the situation instead of refused (L272). Returns
    (mode, grenade_pb, g_without_pdf, rg)."""
    e = ctx.e
    has_grenade = "grenade" in ctx.a
    if has_grenade and "concentrate" in ctx.a and not ctx.a.startswith(CHART_GRENADE_OR_CF):
        # LOW: any other text naming both used to run the prompt of one and the booking of the other
        raise rules.Violation(
            f"'{ctx.action}' names both Grenade Attack and Concentrate Fire: book the chart result "
            f"'Grenade Attack (or Concentrate Fire)' or one of the two [Enemy Activity Chart]"
        )
    grenade_pb = has_grenade and bool(state.valid_target(s, e["karte"], "Feind"))
    g_without_pdf = (
        has_grenade and state.is_v4(s) and e.get("vof_rating") == "G" and not fire.is_firing(e) and not grenade_pb
    )
    rg = leader_rg_target(s, ctx.n) if (state.is_v4(s) and has_grenade and not grenade_pb) else None  # L67 [8.9]
    g_firing = has_grenade and e.get("vof_rating") == "G" and fire.is_firing(e)  # Mortar Team with its own PDF
    grenade_ok = grenade_pb or g_without_pdf or bool(rg) or g_firing
    if has_grenade and "concentrate" not in ctx.a and not grenade_ok:
        raise rules.Violation(
            f"{ctx.n}: Grenade Attack only against a Point Blank target or as a G!/Rifle Grenade unit; at range the "
            f"chart alternative is 'Concentrate Fire' [7.10, 7.3.2, 8.9]"
        )
    mode = "grenade" if grenade_ok else "concentrate"
    return mode, grenade_pb, g_without_pdf, rg


def _grenade_prompt(s, ctx, mode, grenade_pb):
    """Draw prompt for the attempt (Violation) unless --success is given."""
    if ctx.o.get("--erfolg") in ("ja", "nein"):
        return
    concentrate = mode == "concentrate"
    raise rules.Violation(
        f"{'Attempt to Concentrate Fire' if concentrate else 'Grenade Attack (only Point Blank or G! rating)'}: draw "
        f"{enemy_attempt_cards(s, ctx.e, concentrate)} cards "
        f"(base 2, experience {comms.experience(ctx.e)}{', Leader +1' if leader_cards(s, ctx.e) else ''}{', tripod +1' if concentrate and ctx.e.get('tripod') else ''}), "
        f"{'Crosshairs' if concentrate else 'Grenade symbol'}; --success=yes|no --unit=<target unit or cover stack>{largest_target_note(s, ctx.e)} [7.10, 7.11, 8.9] "
        + commands.draw_watch(s, "cf" if concentrate else "grenade", ctx.e, ranged=mode == "grenade" and not grenade_pb)
    )


def _leave_deep_bunker(s, ctx):
    """[CSR 5 p.14] 'Enemy units will leave the Bunker upon drawing Fall Back or Grenade Attack actions' (L130). The unit
    opens fire at once; a target tie is settled with --target (L273, review M20: the tie used to be unrecoverable)."""
    cv0 = geometry.cover_marker(s, ctx.e)
    if not (cv0 and cv0["typ"] == "Deep Bunker"):
        return
    ctx.e["bereich"] = "offen"
    ctx.e.pop("deep_bunker", None)
    commands.mark(ctx.e, rules.EXPOSED)
    ctx.prot.append(
        f"{ctx.n} leaves Deep Bunker {cv0['id']} for the Grenade Attack, Exposed; VOF now active [CSR 5 p.14, 5.3.2]"
    )
    fire.open_fire(s, ctx.prot, only=[ctx.n])
    if ctx.e.get("ziel_offen"):
        zk = ctx.o.get("--ziel")
        if zk not in ctx.e["ziel_offen"]:
            raise rules.Violation(
                f"{ctx.n} leaves the Deep Bunker and has several targets: R# from {', '.join(ctx.e['ziel_offen'])}; "
                f"repeat with --target=<card> [6.1.1]"
            )
        ctx.e["ziel"] = zk
        ctx.e.pop("ziel_offen", None)
        ctx.prot.append(f"{ctx.n} opens fire on {zk} (chosen by R#) [6.1.1]")


def _grenade_target_card(s, ctx, grenade_pb, g_without_pdf, rg):
    """The attacked card; a G! unit without PDF places its PDF first; a Leader fires a Rifle Grenade along the PDF."""
    if not fire.is_firing(ctx.e) and not grenade_pb and not g_without_pdf and not rg:
        raise rules.Violation(f"{ctx.n} is not firing, no Concentrate Fire possible [4.2.4b]")
    if g_without_pdf:
        zk_g = ctx.o.get("--ziel")
        if zk_g not in fire_candidates_g(s, ctx.n):
            raise rules.Violation(
                f"G! unit without PDF: --target=<card with target in LOS/range> from {', '.join(fire_candidates_g(s, ctx.n)) or 'none'}"
            )
        ctx.e["ziel"], ctx.e["nur_pdf"] = zk_g, True
        ctx.prot.append(f"{ctx.n} places PDF towards {zk_g} [7.3.2 p.53]")
    zk = ctx.e["karte"] if grenade_pb else (rg or fire.effective_fire_target(s, ctx.n))
    if rg:
        ctx.e["rifle_grenades"] -= 1
        ctx.prot.append(
            f"{ctx.n} fires a Rifle Grenade along the PDF to {rg}; {ctx.e['rifle_grenades']} round(s) left [8.9 p.67, Normandy p.23]"
        )
    return zk


def _apply_grenade_hit(s, ctx, zk, ze, z):
    """[RULE 7.10.1 p.54] one unit out of cover or the whole stack under its Cover marker (L124)."""
    gw = options.int_opt(ctx.o, "--wert", "--value", s.get("granate_vof", rules.GRENADE_VOF_DEFAULT))  # L274 (M27)
    stack = commands.grenade_stack(s, ze)
    crit = ctx.o.get("--kritisch") == "ja"
    under = z.get("bereich", "offen") != "offen"
    for m in stack:
        s["einheiten"][m].setdefault("grenade", []).append(gw)
        if crit and under:
            s["einheiten"][m]["grenade_critical"] = True  # L154 [RULE 7.10.3 p.55] also for enemy grenades
        elif crit:
            s["einheiten"][m]["grenade"].append(gw)
    where = f" (stack under {z['bereich']})" if under else ""
    ctx.prot.append(f"{ctx.n}: Grenade VOF {gw} on {', '.join(stack)}{where} [7.10.1]")
    if crit:
        ctx.prot.append(
            "Critical Hit: combined Grenade/Critical Hit marker, the stack loses its cover benefit [7.10.3]"
            if under
            else f"Critical Hit: a second Grenade VOF on {ze} [7.10.3]"
        )
    commands.grenade_back_notes(s, ctx.e, stack, True, ctx.prot, ctx.n)


def _apply_concentrate_hit(s, ctx, zk, ze):
    """[RULE 7.11 p.56] Concentrated Fire marker on the target (stack under a cover marker, 7.11.2)."""
    commands.cf_target_check(s, zk, ze, ctx.e, side="US")  # L150 [RULE 7.11.1, 5.2.2 Fig 3]
    for _m in cf_stack(s, ze):
        s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
    ctx.e["konzentriert"] = True
    ctx.prot.append(
        f"{ctx.n}: Concentrated Fire marker on {ze} (stack: {', '.join(cf_stack(s, ze))}; -1 NCM, cumulative) [7.11]"
    )
    commands.cf_critical(s, ze, ctx.o, ctx.prot)  # L154 [RULE 7.11.4]
    if combat.fire_ammo(ctx.e):  # L173
        combat.ammo_use(s, ctx.n, ctx.e, 1, "successful Concentrate Fire", ctx.prot)


def _enemy_grenade_concentrate(s, ctx):
    """cmd_feindaktion: 'grenade' in a or 'concentrate' in a (prompt, Deep Bunker exit, target, hit or miss; L272)"""
    mode, grenade_pb, g_without_pdf, rg = _grenade_mode(s, ctx)
    _grenade_prompt(s, ctx, mode, grenade_pb)
    if "grenade" in ctx.a:
        # a drawn Grenade Attack result (also 'Grenade Attack (or Concentrate Fire)') leaves the Deep Bunker [CSR 5];
        # before the 'not firing' check, so a target tie can be settled with --target (L273, review M20)
        _leave_deep_bunker(s, ctx)
    zk = _grenade_target_card(s, ctx, grenade_pb, g_without_pdf, rg)
    if (
        state.is_v4(s)
        and mode == "grenade"
        and not grenade_pb
        and combat.ammo(ctx.e)
        and (ctx.e.get("vof_rating") == "G" or ctx.e.get("grenade_ranged"))
    ):
        combat.ammo_use(s, ctx.n, ctx.e, 1, "Grenade Attack at range", ctx.prot)
    if state.is_v4(s) and ctx.o.get("--jam") == "ja" and not grenade_pb and commands.jam_prone(ctx.e):
        commands.jam(s, ctx.n, ctx.prot)
        ctx.o["--erfolg"] = "nein"
    cv = geometry.cover_marker(s, ctx.e)
    if grenade_pb and cv and cv["typ"] in rules.STRUCTURES:
        # [RULE 5.3 p.37] Grenade Attack against a Point Blank opponent: unit leaves Bunker/Pillbox and becomes Exposed
        ctx.e["bereich"] = "offen"
        commands.mark(ctx.e, rules.EXPOSED)
        ctx.prot.append(f"{ctx.n} leaves {cv['typ']} {cv['id']} for the Point Blank attack, Exposed [5.3 p.37]")
    grenade_hit = mode == "grenade" and (zk == ctx.e["karte"] or ctx.e.get("vof_rating") == "G" or rg)
    if ctx.o["--erfolg"] == "ja":
        ze = ctx.o.get("--einheit")
        if not ze:
            raise rules.Violation(f"specify --unit=<target unit> (cover stack or random unit without cover on {zk})")
        z = grenade_target_check(s, zk, ze, ctx.e) if grenade_hit else state.unit(s, ze)  # L265 (M11)
        if zk == ctx.e["karte"]:
            best = largest_targets(s, zk)  # L143 [RULE 8.6.1B p.66] largest target first on the own card
            if best and ze not in best:
                raise rules.Violation(
                    f"{ctx.n} targets the largest target on its card first: {', '.join(best)} (equal size: R#) [RULE 8.6.1B p.66]"
                )
        if grenade_hit:
            _apply_grenade_hit(s, ctx, zk, ze, z)
        else:
            _apply_concentrate_hit(s, ctx, zk, ze)
    elif mode == "grenade" and zk == ctx.e["karte"]:
        state.card(s, zk)["grenade_miss"] = True
        ctx.prot.append(f"{ctx.n}: Grenade Miss (-1) on {zk} [7.10.4]")
        ze = ctx.o.get("--einheit")
        commands.grenade_back_notes(
            s, ctx.e, commands.grenade_stack(s, ze) if ze else state.units_on(s, zk, "US"), False, ctx.prot, ctx.n
        )
    else:
        ctx.prot.append(f"{ctx.n}: attempt failed")


def _is_grenade_concentrate(s, ctx):
    return "grenade" in ctx.a or "concentrate" in ctx.a


def _enemy_shift(s, ctx):
    """cmd_feindaktion: 'shift' in a"""
    target = ctx.o.get("--ziel")
    if geometry.arc_direction(s, ctx.e) or ctx.e.get("bunker_richtung"):
        raise rules.Violation(f"{ctx.n} is in a Bunker/Pillbox: draw the 'Shift Fire' result again [RULE 5.3.2 p.37]")
    if not target:
        raise rules.Violation("Shift PDF: --target=<card the fire comes from> (random if several; Bunker: draw again)")
    state.card(s, target)
    # L59: Chart 'Shift Fire if possible to place VOF on opposing units' - only with LOS, range and a valid target
    _los = geometry.los(
        s,
        ctx.e["karte"],
        target,
        ha=geometry.height_bonus(s, ctx.e),
        hb=geometry.card_height_bonus(s, target, geometry.opponent_of(ctx.e)),
    )
    if not _los[0] or not geometry.in_range(s, ctx.e, target) or not state.valid_target(s, target, ctx.e["seite"]):
        reason = (
            _los[1]
            if not _los[0]
            else ("out of range" if not geometry.in_range(s, ctx.e, target) else "no valid target")
        )
        ctx.prot.append(
            f"{ctx.n}: Shift PDF to {target} not possible ({reason}); fire continues [Enemy Activity Chart: 'Shift Fire if possible', 9.2.1]"
        )
    else:
        ctx.e["ziel"] = target
        ctx.e.pop("konzentriert", None)
        ctx.prot.append(f"{ctx.n} shifts its PDF to {target} [Chart, 6.3.3]")


def _is_shift(s, ctx):
    return "shift" in ctx.a


def _enemy_rally(s, ctx):
    """cmd_feindaktion: a.startswith('rally')"""
    if state.pinned(ctx.e):
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            kz, ez = comms.enemy_rally_cards(ctx.e)
            raise rules.Violation(
                f"Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]"
            )
        if not ctx.under_vof or ctx.o["--erfolg"] == "ja":
            ctx.e["status"].remove(rules.PINNED)
            ctx.prot.append(f"{ctx.n}: Pinned marker removed, VOF Basic again [6.5.1]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")
    elif state.fire_team_side(ctx.e):
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            raise rules.Violation("Flip to Front under VOF: 2 cards, word 'Rally'; --success=yes|no [4.2.3f]")
        if not ctx.under_vof or ctx.o["--erfolg"] == "ja":
            ctx.e["status"].remove(rules.FIRE_TEAM_SIDE)
            ctx.prot.append(f"{ctx.n}: back to the front side [4.2.3f]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")
    elif state.is_lat(ctx.e):
        nearest = {"Paralyzed Team": "Litter Team", "Litter Team": "Fire Team", "Fire Team": "Assault Team"}.get(
            ctx.e["typ"]
        )
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            kz, ez = comms.enemy_rally_cards(ctx.e)
            raise rules.Violation(
                f"LAT Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]"
            )
        if nearest and (not ctx.under_vof or ctx.o["--erfolg"] == "ja"):
            ctx.e["typ"] = nearest
            combat.set_lat_values(ctx.e, nearest)
            ctx.prot.append(f"{ctx.n} becomes {nearest} [6.5.1]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")


def _is_rally(s, ctx):
    return ctx.a.startswith("rally")


def _enemy_remove(s, ctx):
    """cmd_feindaktion: 'remove' in a"""
    remove_enemy(s, ctx.n, ctx.prot, reason="Z4: no LOS, no fire", pc=True)


def _is_remove(s, ctx):
    return "remove" in ctx.a


def _enemy_move_towards(s, ctx):
    """cmd_feindaktion: 'move towards' in a"""
    target = ctx.o.get("--ziel")
    if not target or not geometry.adjacent(s, ctx.e["karte"], target):
        raise rules.Violation(
            "Move towards closest Casualty: --target=<adjacent card towards the closest Casualty> [LAT/Pinned Hierarchy]"
        )
    commands.diagonal_pdf_check(s, ctx.e, target)  # L131 [RULE 5.1.2 p.32]
    move_enemy(s, ctx.n, target, ctx.prot, cover=False, how="moves towards the Casualty")  # in the open, as before


def _is_move_towards(s, ctx):
    return "move towards" in ctx.a


def closest_opponent_cards(s, e):
    """L168 [Enemy Activity Chart 'Infiltrate towards closest opposing unit'; Shonai_Dweller BGG 3575248 '"Closest" means
    closest ... equally distant you have to randomize', UrineJoeGarin 3488797 'draw a R#']: nearest opponent-occupied cards
    and, per card, the adjacent cards that bring the unit closer."""
    opp = state.opponent_of_side(e["seite"])
    occ = sorted(
        k
        for k, c in s["karten"].items()
        if not c.get("staging") and any(s["einheiten"][m]["typ"] != "Casualty" for m in state.units_on(s, k, opp))
    )
    if not occ:
        return []
    d0 = min(geometry.distance(s, e["karte"], k) for k in occ)
    out = []
    for k in occ:
        if geometry.distance(s, e["karte"], k) != d0:
            continue
        steps = sorted(
            a
            for a in s["karten"]
            if geometry.adjacent(s, e["karte"], a)
            and not s["karten"][a].get("ausserhalb")
            and geometry.distance(s, a, k) < d0
        )
        out.append((k, steps))
    return out


def _enemy_infiltrate(s, ctx):
    """cmd_feindaktion: 'infiltrate' in a"""
    target = ctx.o.get("--ziel")
    if not target:
        cands = closest_opponent_cards(s, ctx.e)
        lines = [f"{k} (step to {', '.join(st) or '-'})" for k, st in cands]
        raise rules.Violation(
            "Infiltrate towards closest opposing unit: closest opponent card(s) "
            + "; ".join(f"{i + 1}. {x}" for i, x in enumerate(lines))
            + (f" - choose by R# column {len(cands)}" if len(cands) > 1 else "")
            + "; then the step card (R# if several); give --target=<card> [Chart, BGG 3575248, 3488797, L168]"
        )
    if not geometry.adjacent(s, ctx.e["karte"], target):
        raise rules.Violation(f"{target} is not adjacent to {ctx.e['karte']} [RULE 5.1.2 p.31]")

    def _any_vof(k):  # a VOF marker of either side on the card [5.1.4]
        return any(fire.vof_against(s, k, side) is not None for side in ("US", "Feind"))

    vof_here, vof_there = _any_vof(ctx.e["karte"]), _any_vof(target)
    if not (vof_here or vof_there) and ctx.o.get("--erfolg") is None:
        # L168 [RULE 5.1.4 p.32 'as long as either the origin card or the destination card has a VOF marker'; K40]
        ctx.o["--erfolg"] = "nein"
        ctx.prot.append(
            f"{ctx.n}: no VOF on {ctx.e['karte']} or {target}, infiltration not possible: normal move, Exposed [5.1.4, K40]"
        )
    if ctx.o.get("--erfolg") not in ("ja", "nein"):
        raise rules.Violation(
            f"Infiltrate: --target=<card towards nearest opponent> --success=yes|no ({enemy_attempt_cards(s, ctx.e)} cards: base 2, experience {comms.experience(ctx.e)}{', Leader +1' if leader_cards(s, ctx.e) else ''}, Infiltrate symbol); failure = normal move with Exposed [8.6, 5.1.4, 8.9]"
        )
    state.card(s, target)
    commands.diagonal_pdf_check(s, ctx.e, target)  # L131
    # L264 (review M21): the Grenade marker now expires here as well (move_enemy)
    move_enemy(s, ctx.n, target, ctx.prot, exposed=ctx.o["--erfolg"] == "nein", how="infiltrates", rule="8.6, 5.1.4")


def _is_infiltrate(s, ctx):
    return "infiltrate" in ctx.a


@dataclasses.dataclass
class EnemyActionCtx:
    """The working record of one enemy action (cmd_enemy_action; review Struktur 10: a dataclass instead of a
    SimpleNamespace). The handlers of ENEMY_ACTION_HANDLERS read it and append to prot."""

    a: str  # the drawn result, lower case (the handler tests match on it)
    action: str  # the result as given
    e: dict  # the enemy unit
    n: str  # its name
    o: dict  # parsed options
    prot: list = dataclasses.field(default_factory=list)  # protocol lines
    under_vof: bool = False  # the unit's card is under friendly VOF
    origin_card: typing.Optional[str] = None  # card before the action


ENEMY_ACTION_HANDLERS = [
    (_is_no_action, _enemy_no_action),
    (_is_call_for_fire, _enemy_call_for_fire),
    (_is_no_fire_missions, _enemy_no_fire_missions),
    (_is_advance, _enemy_advance),
    (_is_seek_cover, _enemy_seek_cover),
    (_is_fall_back, _enemy_fall_back),
    (_is_grenade_concentrate, _enemy_grenade_concentrate),
    (_is_shift, _enemy_shift),
    (_is_rally, _enemy_rally),
    (_is_remove, _enemy_remove),
    (_is_move_towards, _enemy_move_towards),
    (_is_infiltrate, _enemy_infiltrate),
]


ENEMY_ACTION_USAGE = 'enemyaction <enemy> "<result>" [--target=K] [--success=yes|no] [--unit=<target>]'


def cmd_enemy_action(s, args):
    rules.need(args, 2, ENEMY_ACTION_USAGE)  # L269 (review H12)
    n = args[0]
    e = state.unit(s, n)
    if e["seite"] != "Feind":
        raise rules.Violation(f"{n} is not an enemy")
    action = args[1]
    event_seg, check_seg = enemy_segments(s)  # L261 (review H2): defensive missions use 3.2.1/3.2.2
    event_rally = s["phase"] == event_seg and n in s.get("rally_offen", []) and action.lower().startswith("rally")
    if s["phase"] != check_seg and not event_rally:
        raise rules.Violation(
            f"Enemy actions only in the Enemy Activity Check segment {check_seg}, currently {s['phase']}"
        )
    o = options.parse_opts(args[2:])
    prot = []
    a = action.lower()
    if event_rally:
        s["rally_offen"].remove(n)
    # L270: 'move' alone also matched 'Move into or Seek Cover', which an immobile AT gun may do
    if e.get("unbeweglich") and any(w in a for w in ("fall back", "move towards", "infiltrate", "advance")):
        raise rules.Violation(f"{n} is an immobile AT gun: draw the result again [RULE 8.12 p.68]")
    origin_card = e["karte"]
    under_vof = fire.vof_against(s, e["karte"], "Feind") is not None
    ctx = EnemyActionCtx(a=a, action=action, e=e, n=n, o=o, prot=prot, under_vof=under_vof, origin_card=origin_card)
    for test, handler in ENEMY_ACTION_HANDLERS:
        if test(s, ctx):
            handler(s, ctx)
            break
    else:
        raise rules.Violation(f"Action '{ctx.action}' unknown")
    if n in s["einheiten"]:
        s["einheiten"][n]["check_offen"] = False
        e2 = s["einheiten"][n]
        if state.is_v4(s) and e2["karte"] != origin_card:
            # the mine check of the new card is requested by move_enemy (L264)
            if is_sniper(e2) and not any(
                geometry.los(
                    s, e2["karte"], k, ha=geometry.height_bonus(s, e2), hb=geometry.card_height_bonus(s, k, "US")
                )[0]
                for k in s["karten"]
                if state.units_on(s, k, "US") and not state.card(s, k).get("staging")
            ):
                for m in state.units_on(s, e2["karte"], "Feind"):
                    s["einheiten"][m]["spotted"] = False
                prot.append(f"{n} out of LOS of all US units: Unspotted again [8.8 p.67]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Activity Check {n}: {action}; " + "; ".join(prot), "8.6.2 p.66, Enemy Activity Chart")
    briefing.print_board(prot, s)


def remove_enemy(s, n, prot, reason="", pc=False):
    """Enemy counter off the board, back to the pool [8.3] (Fall Back off the map edge, Sniper/Spotter removal, PC
    return). Not routed through combat.remove_from_play: the counter returns to the counter mix at once, so it is
    not listed as Removed from Play (L449); package and ammo marker are handled here."""
    e = s["einheiten"][n]
    kid = e["karte"]
    if pc and not state.card(s, kid).get("pc"):
        state.card(s, kid)["pc"] = e.get("pc_herkunft", "A")
        prot.append(f"Place PC marker {state.card(s, kid)['pc']} on {kid} [8.6.1]")
    pk = s.get("pakete", {}).get(str(e.get("paket")))
    if pk:
        pk["im_spiel"] = False
    ammo_lost(e, n, prot)
    del s["einheiten"][n]
    prot.append(f"{n} off the board ({reason}), counter back to the pool [8.3]")


def ammo_lost(e, name, prot):
    """L62 (the player 09.10.2026): remove the ammo marker of a counter removed from the board; 5.1.6E only drops Assets and
    Casualties, enemy ammo is not captured (BGG 3498471)."""
    m = e.get("munition")
    if m and m.get("punkte"):
        prot.append(
            f"Remove ammo marker of {name} ({m['punkte']} {m.get('typ', '')}) from {e.get('karte')}: ammo lost, "
            f"no capture [5.1.6E, BGG 3498471]"
        )


def is_sniper(e):
    return e.get("vof_rating") == "S!" and not state.fire_team_side(e) and not state.is_lat(e)


def sniper_on_card(s, kid):
    """Firing, non-pinned snipers whose VOF lies on kid (7.15: HQs there -3 Command draw)."""
    return [
        n
        for n, e in s["einheiten"].items()
        if is_sniper(e) and fire.is_firing(e) and not state.pinned(e) and fire.effective_fire_target(s, n) == kid
    ]


def choose_sniper_targets(s, prot):
    """[RULE 7.15 p.57] At the start of 3.7.4: random target on the card, Exposed first."""
    s["sniper_ziele"] = {}
    s["sniper_offen"] = {}
    for n in [m for m, e in s["einheiten"].items() if is_sniper(e) and fire.is_firing(e) and not state.pinned(e)]:
        kid = fire.effective_fire_target(s, n)
        candidate = state.units_on(s, kid, state.opponent_of_side(s["einheiten"][n]["seite"]))
        exp = [m for m in candidate if rules.EXPOSED in s["einheiten"][m]["status"]]
        if exp:
            candidate = exp
        if len(candidate) == 1:
            s["sniper_ziele"][n] = candidate[0]
            prot.append(f"Sniper VOF (-3) from {n} on {candidate[0]}; rest of the card Small Arms only [7.15 p.57]")
        elif candidate:
            s["sniper_offen"][n] = candidate
            prot.append(
                f"Sniper {n}: target by R# (column {len(candidate)}) from {', '.join(candidate)}"
                + (" (Exposed only)" if exp else "")
                + f'; then fof.py sniper "{n}" <target> [7.15 p.57]'
            )


def cmd_sniper(s, args):
    rules.need(args, 2, "sniper <sniper> <target unit>")  # L269 (review H12)
    n, z = args[0], args[1]
    candidate = s.get("sniper_offen", {}).get(n)
    if not candidate:
        raise rules.Violation(f"No target choice pending for {n}")
    if z not in candidate:
        raise rules.Violation(f"{z} not among {', '.join(candidate)}")
    s["sniper_offen"].pop(n)
    s.setdefault("sniper_ziele", {})[n] = z
    if z in s.get("kampf_ncm", {}) or z in s.get("kampf_offen", []):
        s.setdefault("kampf_ncm", {})[z] = [list(x) for x in combat.ncm_rows(s, z)]
    prot = [f"Sniper VOF (-3) from {n} on {z} [7.15 p.57]"]
    state.save_state(s, "; ".join(prot), "7.15 p.57")
    briefing.print_board(prot, s)


def spotter_target(s, n):
    """[RULE 8.10 p.68] Priority: Target Marker card, vehicle, most steps, nearest card, random."""
    e = s["einheiten"][n]
    candidate = [
        k
        for k in s["karten"]
        if state.units_on(s, k, "US")
        and not state.card(s, k).get("staging")
        and (
            k == e["karte"]
            or geometry.los(
                s, e["karte"], k, ha=geometry.height_bonus(s, e), hb=geometry.card_height_bonus(s, k, "US")
            )[0]
        )
    ]
    if not candidate:
        return None
    tk = s.get("feind_target", {}).get(e.get("typname"))
    if tk in candidate:
        return tk
    st = {k: sum(state.steps(s["einheiten"][m]) for m in state.units_on(s, k, "US")) for k in candidate}
    best = max(st.values())
    candidate = [k for k in candidate if st[k] == best]
    d = min(geometry.distance(s, e["karte"], k) for k in candidate)
    candidate = [k for k in candidate if geometry.distance(s, e["karte"], k) == d]
    if len(candidate) > 1:
        s.setdefault("_hinweise", []).append(f"Spotter targets tied: {', '.join(candidate)}; choose by R# [8.10]")
    return candidate[0]


def fire_candidates_g(s, n):
    """G! unit without PDF: target in LOS and range (player aid: 'Also applies to a G! rated unit on a card with no PDF, but with a target in LOS')."""
    e = s["einheiten"][n]
    return [
        k
        for k in s["karten"]
        if k != e["karte"]
        and state.valid_target(s, k, e["seite"])
        and geometry.in_range(s, e, k)
        and geometry.los(
            s,
            e["karte"],
            k,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, k, geometry.opponent_of(e)),
        )[0]
    ]


def leader_rg_target(s, n):
    """L67 [RULE 8.9 p.67] Leader with Rifle Grenade: 'can fire them along their card's existing PDF ... treat them as G!-rated units on the
    Enemy Activity Chart'. Returns the target card along an existing PDF of his card (rifle grenade range), else None."""
    e = s["einheiten"][n]
    if not e.get("leader") or e.get("rifle_grenades", 0) <= 0 or not state.good_order(e) or state.fire_team_side(e):
        return None
    kid = e["karte"]
    rw = s.get("rifle_grenade_reichweite", "C")
    for m, x in s["einheiten"].items():
        if (
            m == n
            or x.get("seite") != e["seite"]
            or x.get("karte") != kid
            or not fire.is_firing(x)
            or x.get("ziel") in (None, kid)
        ):
            continue
        z = x["ziel"]
        if state.valid_target(s, z, e["seite"]) and geometry.in_range(s, dict(e, reichweite=rw), z):
            return z
    return None


def leader_cards(s, e):
    """[RULE 8.9 p.67] 'All enemy units in Visual-Verbal communication with a Good Order enemy leader draw one additional card
    for any action attempts made.' L142"""
    return 1 if e.get("seite") == "Feind" and leader_present(s, e) else 0


def enemy_attempt_cards(s, e, concentrate=False):
    """Cards for an enemy attempt: base 2, experience, Leader +1 (8.9), tripod +1 for Concentrate Fire (7.11.2)."""
    n = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(e), 0) + leader_cards(s, e)
    if concentrate and e.get("tripod") and not state.fire_team_side(e):
        n += 1
    return max(1, n)


def largest_targets(s, kid):
    """[RULE 8.6.1B p.66] targets on the enemy's own card: 'the largest target (highest number of steps) first, then randomly
    among equal sized targets'. Returns the names of the largest target(s): a stack under a cover marker counts as one target. L143"""
    us = [m for m in state.units_on(s, kid, "US") if s["einheiten"][m]["typ"] != "Casualty"]
    if not us:
        return []
    size = {}
    for m in us:
        b = s["einheiten"][m].get("bereich", "offen")
        key = m if b == "offen" else f"stack {b}"
        size[key] = size.get(key, 0) + state.steps(s["einheiten"][m])
    top = max(size.values())
    best = []
    for m in us:
        b = s["einheiten"][m].get("bereich", "offen")
        key = m if b == "offen" else f"stack {b}"
        if size[key] == top:
            best.append(m)
    return best


def largest_target_note(s, e):
    best = largest_targets(s, e["karte"]) if state.valid_target(s, e["karte"], "Feind") else []
    return f"; on the own card the largest target first: {', '.join(best)}" if best else ""


def restricted_mover(e):
    """[RULE 4.2.5 p.26] Pinned units and Paralyzed/Litter Teams move to an adjacent card only without VOF there (E90)."""
    return state.pinned(e) or e.get("typ") in ("Paralyzed Team", "Litter Team")


def fall_back_candidates(s, e):
    """[RULE 8.6.3 p.66] Fall Back towards the own side (one row towards the enemy edge, straight or diagonal, cards that exist):
    2. cards out of LOS of every US unit; 3. highest cover value (terrain C&C plus the best free cover marker). Returns the
    best set (several = random choice by R#); empty if no card exists. L141"""
    c = state.card(s, e["karte"])
    cands = []
    for sp in (c["spalte"] - 1, c["spalte"], c["spalte"] + 1):
        k = geometry.card_at(s, c["reihe"] + 1, sp)
        if k and not state.card(s, k).get("staging"):
            cands.append(k)
    if restricted_mover(e):
        # E90/L213 [RULE 4.2.5 p.26, 8.6.1C p.66] reading B: Pinned units, Paralyzed and Litter Teams need no
        # friendly-occupied card (8.6.1C), but 'with no VOF on it' still applies
        cands = [k for k in cands if fire.vof_against(s, k, e["seite"]) is None]
    if not cands:
        return []
    us_cards = {x["karte"] for x in s["einheiten"].values() if x["seite"] == "US" and x.get("karte") in s["karten"]}

    def seen(k):  # L271: with the US height bonus like every other LOS pair
        return any(
            geometry.los(
                s, uk, k, ha=geometry.card_height_bonus(s, uk, "US"), hb=geometry.card_height_bonus(s, k, "Feind")
            )[0]
            for uk in us_cards
        )

    hidden = [k for k in cands if not seen(k)]
    pool = hidden or cands

    def cover_value(k):
        ck = state.card(s, k)
        free = [cv["wert"] for cv in state.free_cover(s, k, side="Feind")]
        return (ck.get("cc") or 0) + (max(free) if free else 0)

    top = max(cover_value(k) for k in pool)
    return [k for k in pool if cover_value(k) == top]


def leader_present(s, e):
    """[RULE 8.9 p.67] Good Order leader in Visual-Verbal (same card, same area)."""
    return any(
        x.get("leader")
        and x["seite"] == e["seite"]
        and x["karte"] == e["karte"]
        and x.get("bereich", "offen") == e.get("bereich", "offen")
        and state.good_order(x)
        and x is not e
        for x in s["einheiten"].values()
    )
