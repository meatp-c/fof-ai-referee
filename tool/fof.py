#!/usr/bin/env python3
"""fof.py v4 - shadow board, sequence of play and rules check for Fields of Fire Deluxe (Series Rules 3rd Ed.).

Usage:  python3 tool/fof.py <command> [...]   (run from the project folder; German command names work too)
  new <aufbau.json> [game]          create a game
  setup <unit> <staging-card> | setup <unit> --platoon=1|2|none
                                    starting setup and attachments (only turn 1 before 3.3.1a, 2.3.3/2.3.5)
  status                            briefing (writes BRIEFING.md)
  radio [check <hq> <unit> | damage <card> <device> intact|destroyed]   communication (4.3, 4.3.5)
  drop <unit> <Casualty|device>     drop a Casualty or radio without a Command (5.1.6B)
  options                           open rules questions (Ux) and chosen reading
  phase [next|<id>]                 sequence of play; segments with automation: 3.4.2, 3.5.1, 3.5.2, 3.7.1, 3.7.2, 3.7.3, 3.7.4
  activate <hq>                     4.2.1a in the CO/BN HQ impulse
  hq <hq>                           choose the active HQ for the impulse
  card <no> <helmet number> [--raw] Command Draw (4.1.2)
  gi <no> <initiative number> [--skill-from=<HQ>]   General Initiative (3.3.2d), optional skill General Initiative
  order <hq|GI> <unit> <action> [--target=K] [--success=yes|no] [--area=<cover-id|open>] [--skill=<Auto ...|Extra Draw>]
                                    [--originator=<hq>] [--team=Fire|Assault] [--squad=<name>] [--unit=<target unit>]
                                    [--agency=81mm|105mm] [--short=yes] [--place=K] [--what=Casualty|<device>]
  done                              end the impulse
  fire <unit> <card|off>            set a fire target by hand (random decision, correction)
  enemycheck                        3.4.2: hierarchy row and R# column for each enemy
  enemyaction <enemy> "<action>" [--target=K] [--success=yes|no] [--unit=<target>]   carry out the result
  pc [<card>] | pc clear <card> | pc contact <card> <package> [--place=K] [--type=<counter name for squad choice>]
  external <card> Incoming|Mines|AirStrike|Smoke|Pending <value> | external <card> remove
  enemy <name> spotted|unspotted|pinned|unpinned|remove|karte=K|cover=<id>|steps=n
  ncm <unit>                        precompute NCM (6.4)
  hit <unit> HIT|PIN|MISS [<effect>]   6.4.2 / 6.4.3
  endturn                           3.8 Clean Up
  check | rule <no> | search <term>
Every change is saved only if the check finds no errors. VOF, PDF and Crossfire are derived from the
units' fire targets (6.1 to 6.3), not tracked by hand.
New in v3 (company, CAC): CO HQ on the board, BN HQ off-map, radio SCR300/SCR536, Mortar Section (Direct and
Indirect Lay 4.2.4j), Call for Fire with several firing agencies, Short, Target marker, Gully with two C&C values,
directional card edges, bunker fire arc and capacity, multiple packages, Casualty Collection Point (4.2.1l).
Open rules questions are options in the setup JSON ("optionen") and appear in output as [open Ux].
New in v4 (Normandy campaign, normandy/aenderungen_fof_v4.md):
  terrain <card> <type> [--no=..] [--hill=n] [--edges=top:white,..] [--cc=..]   enter a random card (2.2.1)
  extend <row> <column> <type> [...]   map extension (8.4.5), off-limits to US outside the boundaries
  objective primary|secondary|ap|ccp <card> | objective phaseline <n> <row>   Tactical Controls (2.4.1)
  set <unit> field=value ...            enter unverified counter values before turn 1
  setup ... --net=radio|phone --mortar=section|teams --asset=<type> --lines=n --pyro=<type>:<code>
  event <card no> yes <R#> [--who=..] | event <card no> no   Higher HQ Events (3.1, 3.4.1)
  pc reveal <card> <A|B|C> | pc set <card> <A|B|C|?>
  mine <unit> yes|no                    mine check (7.9.1)
  sniper <sniper> <target>              target of the sniper VOF in 3.7.4 (7.15)
  line <card> ok|cut | line lay <card>  phone lines (4.3.4)
  runner                                runner overview (4.3.2); orders 4.2.1f/g/h
  ammo [depot <card> <type> <n>]        ammo (7.18)
  capture <enemy> <guard>               take prisoners (3.5.1, 8.15)
  xp [add <n> <reason>]                 experience log (12.1)
  reattempt [done] | reconstitute <unit> --from=<LAT,..> [--experience=..]   Reattempt (3.9)
  campaign                              Mission Log (2.3.1, 12.2)
  visibility [<light> [<weather>] [--this-turn-only=yes]]   visibility modifier (9.0), +2 or more is Limited Visibility (9.1)
  illum <card> <top> [<bottom>] [--origin=..] | illum <card> remove   Illumination (9.2), removed in Clean Up
  patrol [start|next <platoon> [--with=a,b]]   Combat Patrol (2.6, MSR 1-4); objective route <1-4> <card>, objective cop <card>
"""
import json, re, sys, copy, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ---------------------------------------------------------------- Sequence of play (3.0, player aid Sequence of Play)
SOP_OFFENSIV = [
    ("3.1", "Friendly Higher HQ Event Phase (from turn 2)"),
    ("3.3.1a", "Activation Segment: BN HQ Impulse"),
    ("3.3.1b", "Activation Segment: CO HQ Impulse"),
    ("3.3.1c", "Activation Segment: PLT HQ / CO Staff Impulse"),
    ("3.3.2a", "Initiative Segment: CO HQ Initiative Impulse"),
    ("3.3.2b", "Initiative Segment: PLT HQ Initiative Impulse"),
    ("3.3.2c", "Initiative Segment: CO Staff Initiative Impulse"),
    ("3.3.2d", "Initiative Segment: General Initiative Impulse"),
    ("3.4.1", "Enemy Higher HQ Event Segment (from turn 2)"),
    ("3.4.2", "Enemy Activity Check Segment"),
    ("3.5.1", "Capture Segment"),
    ("3.5.2", "Retreat Segment"),
    ("3.6", "AT Combat & Vehicle Movement Phase"),
    ("3.7.1", "Fire Mission Update Segment"),
    ("3.7.2", "Potential Contact Evaluation Segment"),
    ("3.7.3", "Pinned Recovery Segment"),
    ("3.7.4", "Combat Effects Segment"),
    ("3.8", "Clean Up Phase"),
]
SOP_DEFENSIV = [SOP_OFFENSIV[0], ("3.2.1", "Enemy Higher HQ Event Segment (from turn 2)"),
                ("3.2.2", "Enemy Activity Check Segment")] + SOP_OFFENSIV[1:8] + SOP_OFFENSIV[10:]
IMPULSE = {"3.3.1a", "3.3.1b", "3.3.1c", "3.3.2a", "3.3.2b", "3.3.2c", "3.3.2d"}
PLT_IMPULSE = {"3.3.1c", "3.3.2b"}
AB_ZUG_2 = {"3.1", "3.2.1", "3.4.1"}

# ---------------------------------------------------------------- Actions (4.2, p.22-26)
# id: (name, cost, draw type, originator, rule reference)   draw type: auto | attempt | attempt_vof (Rally: auto without VOF) | cover | cff
AKTIONEN = {
    "4.2.1a": ("Activate a subordinate HQ or Staff", 1, "auto", "CO_BN", "4.2.1a p.22"),
    "4.2.1b": ("Exhort", 1, "auto", "HQ", "4.2.1b p.22"),
    "4.2.1c": ("Deploy Pyrotechnic", 1, "auto", "HQ", "4.2.1c p.22"),
    "4.2.1d": ("Reconstitute a Platoon HQ", 1, "auto", "HQ", "4.2.1d p.22, 6.5.2 p.49"),
    "4.2.1e": ("Reconstitute the CO HQ", 1, "auto", "BN", "4.2.1e p.22, 6.5.2 p.49/50"),
    "4.2.1f": ("Create a Runner", 1, "auto", "CO_ONLY", "4.2.1f p.22, 4.3.2 p.27"),
    "4.2.1g": ("Dispatch a Runner", 1, "auto", "CO_ONLY", "4.2.1g p.22, 4.3.2 p.27"),
    "4.2.1h": ("Dismiss a Runner", 1, "auto", "CO_ONLY", "4.2.1h p.22, 4.3.2 p.27"),
    "4.2.1j": ("Switch Radio/Phone to a Different Network", 1, "auto", "HQ", "4.2.1j p.22, 4.3.3 p.27"),
    "4.2.1k": ("Repair a Cut Phone Line", 1, "auto", "HQ", "4.2.1k p.22, 4.3.4 p.29"),
    "4.2.1l": ("Designate a New Tactical Control", 1, "auto", "CO", "4.2.1l p.22, 5.1.7 p.33"),
    "4.2.2a": ("Move to an Adjacent Card", 1, "auto", "HQ", "4.2.2a p.23"),
    "4.2.2b": ("Move a Platoon to an Adjacent Card", 2, "auto", "PLT", "4.2.2b p.23"),
    "4.2.2c": ("Attempt to Infiltrate an Adjacent Card", 1, "attempt", "HQ", "4.2.2c p.23"),
    "4.2.2d": ("Attempt to have a Platoon Infiltrate an Adjacent Card", 2, "attempt", "PLT", "4.2.2d p.23"),
    "4.2.2e": ("Attempt to Seek Cover", 1, "cover", "HQ", "4.2.2e p.23"),
    "4.2.2f": ("Move within a Card", 1, "auto", "HQ", "4.2.2f p.23"),
    "4.2.2g": ("Attempt to Infiltrate within a Card", 1, "attempt", "HQ", "4.2.2g p.23"),
    "4.2.2h": ("Pick up, load, unload, embark", 1, "auto", "HQ", "4.2.2h p.23"),
    "4.2.3a": ("Attempt to Remove a Pinned marker", 1, "attempt_vof", "HQ", "4.2.3a p.24"),
    "4.2.3b": ("Attempt to Convert a Paralyzed Team to a Litter Team", 1, "attempt_vof", "HQ", "4.2.3b p.24"),
    "4.2.3c": ("Attempt to Convert a Litter Team to a Fire Team", 1, "attempt_vof", "HQ", "4.2.3c p.24"),
    "4.2.3d": ("Attempt to Convert a Fire Team to an Assault Team", 1, "attempt_vof", "HQ", "4.2.3d p.24"),
    "4.2.3e": ("Convert an Assault Team to a Fire Team", 1, "auto", "HQ", "4.2.3e p.24"),
    "4.2.3f": ("Attempt to Flip a unit with a Fire Team side to Front", 1, "attempt_vof", "HQ", "4.2.3f p.24"),
    "4.2.3g": ("Detach Team", 1, "auto", "HQ", "4.2.3g p.24"),
    "4.2.3h": ("Supplement Squad", 1, "auto", "HQ", "4.2.3h p.24"),
    "4.2.3i": ("Attempt to Reconstitute Squad", 1, "attempt", "HQ", "4.2.3i p.24, 6.5.2 p.49"),
    "4.2.3j": ("Flip a unit with a Fire Team side to its Fire Team side", 1, "auto", "HQ", "4.2.3j p.24"),
    "4.2.4a": ("Attempt to Spot", 1, "attempt", "HQ", "4.2.4a p.25, 8.5 p.65"),
    "4.2.4b": ("Attempt to Concentrate Fire", 1, "attempt", "HQ", "4.2.4b p.25, 7.11 p.56"),
    "4.2.4d": ("Attempt to make a Grenade Attack", 1, "attempt", "HQ", "4.2.4d p.25, 7.10 p.54"),
    "4.2.4i": ("Attempt to Call for Fire from an Off-Map Firing Agency", 1, "cff", "HQ", "4.2.4i p.25, 7.16 p.57"),
    "4.2.4j": ("Call for Indirect Fire from an On-Map Mortar", 1, "auto", "HQ", "4.2.4j p.25, 7.3.2 p.53"),
    "4.2.4k": ("Cease Fire", 1, "auto", "HQ", "4.2.4k p.26, 6.3.3 p.43"),
    "4.2.4l": ("Shift Fire", 1, "auto", "HQ", "4.2.4l p.26, 6.3.3 p.43"),
}
# 4.1.1 p.19: actions that need an HQ/Staff as originator even under General Initiative (Clarification 3)
HQ_PFLICHT_GI = {"4.2.1b", "4.2.1d", "4.2.1e", "4.2.1f", "4.2.1g", "4.2.1h", "4.2.1l", "4.2.3i", "4.2.4m"}
# 4.2.5 p.26 LAT restrictions (allow lists)
LAT_ERLAUBT = {
    "Assault Team": {"4.2.2a", "4.2.2c", "4.2.2e", "4.2.2f", "4.2.2g", "4.2.2h", "4.2.3e", "4.2.3h", "4.2.3i",
                     "4.2.4a", "4.2.4b", "4.2.4d", "4.2.4k", "4.2.4l"},
    "Fire Team": {"4.2.2a", "4.2.2c", "4.2.2e", "4.2.2f", "4.2.2g", "4.2.2h", "4.2.3d", "4.2.3h", "4.2.3i",
                  "4.2.4a", "4.2.4b", "4.2.4d", "4.2.4k", "4.2.4l"},
    "Litter Team": {"4.2.2a", "4.2.2c", "4.2.2e", "4.2.2f", "4.2.2g", "4.2.2h", "4.2.3c"},
    "Paralyzed Team": {"4.2.2a", "4.2.3b"},
}
# 4.2.5 p.26 Pinned: takes precedence over LAT; allows a (restricted), e, f, Rally a, Exhort
PINNED_ERLAUBT = {"4.2.2a", "4.2.2e", "4.2.2f", "4.2.3a", "4.2.1b"}
LAT_TYPEN = {"C": "Casualty", "P": "Paralyzed Team", "L": "Litter Team", "F": "Fire Team", "A": "Assault Team"}
LAT_ERFAHRUNG = {"Assault Team": "Line", "Fire Team": "Green", "Litter Team": "Green", "Paralyzed Team": "Green"}
SPAR_LIMIT = {"Green": (3, 2), "Line": (6, 4), "Veteran": (9, 6)}     # 4.1.3 p.20
MAX_IMPULS = {"tag": 6, "eingeschraenkt": 4}                          # 4.1.3 p.20
VOF_WERT = {"Pinned": 2, "S": 0, "A": -1, "H": -3}                    # 6.2.2 p.42 (A/S: A at Point Blank, otherwise S)
VOF_NAME = {"S": "Small Arms", "A": "Automatic Weapons", "H": "Heavy Weapons", "Pinned": "All Pinned",
            "Incoming": "Incoming!", "Mines": "Mines", "AirStrike": "Air Strike!", "G": "Grenade", "Sniper": "Sniper", "Pending": "Pending",
            "Indirect": "Heavy Weapons (Indirect Lay)"}
CMD_VOF_MOD = {"S": -1, "A": -2, "H": -3, "Sniper": -3, "G": -3, "Incoming": -3, "AirStrike": -3, "Pinned": 0, "Mines": 0,
               "Indirect": -3}  # 4.1.2B; Indirect Lay is a Heavy Weapons VOF (7.3.2 p.53)
# [RULE 5.2.3 p.36] lower C&C value and burst for Incoming and indirect mortar fire
TERRAIN_WIE_INCOMING = ("Incoming", "AirStrike", "Indirect")
FESTE_DECKUNG = ("Trench", "Bunker", "Pillbox")                       # [RULE 5.1.1 p.31, 5.1.2 p.32] movement without Exposed
STRUKTUR = ("Bunker", "Pillbox")                                      # [RULE 5.3.2 p.37] fire arc, no Point Blank
SEITE_NAME = {(1, 0): "oben", (-1, 0): "unten", (0, -1): "links", (0, 1): "rechts"}
# Open rules questions from cac/regeln_cac_run3.md (appendix). Default = the reading marked as more likely in the research;
# where none is marked, the reasoning is in cac/aenderungen_fof_v3.md. Effective only if the setup contains "optionen".
OPTIONEN_STANDARD = {
    "U1_remove_pc_no_action": (True, "Special rule 'Remove unit, place PC' = No Action also applies in Run 2/3 (reading a)"),
    "U2_fo_fd_funk": (True, "FOs implicitly have their FD radio (reading a)"),
    "U3_incoming_blockiert_funk": (True, "Incoming! also blocks SCR536 LOS (reading a, only smoke excepted)"),
    "U4_as_zaehlt_als_a": (False, "A/S does not count as A in the hierarchy row 'A or H VOF unit that has opened fire' (reading a)"),
    "U6_aktivieren_im_initiative_impuls": (False, "CO HQ does not activate PLT HQs in the CO HQ Initiative Impulse (reading b)"),
    "U7_lat_behaelt_funk": (True, "HQ becomes Paralyzed/Litter Team: the team keeps the radio (reading a)"),
    "U9_ziel_lesart": ("a", "a: no enemy non-Casualty unit left on the board; b: prisoners/withdrawn units also count"),
    "U9_reattempt": (False, "no Reattempt after the last turn (FM1 names none)"),
    "U10_staging_funk_ueber_hill": (False, "Staging Area radios only to the adjacent cards of row 1 (wording of 2.5)"),
    "U11_plt_mtr_ueber_hub": (True, "two SCR536 other than the CO HQ talk to each other if both have a connection to the CO HQ (reading a)"),
    "U12_moerser_reichweite": ("C-L", "Range 'C-L' = Close to Long"),
    "U12_indirekt_unter_gi": (False, "Indirect Lay not allowed under General Initiative (reading a)"),
    "U13_target_marker_bei_short": (False, "no automatic Target marker after Short (7.16.5 does not cover the case)"),
    # v4: open rules questions Normandy Mission 1 (normandy/regeln_normandy_m1.md, section U)
    "U14_telefon_diagonal": (True, "Phone lines also connect diagonally adjacent cards (cards count as adjacent diagonally, 5.1.2)"),
    "U15_leitung_automatisch": (True, "A unit with lines automatically lays one when leaving a card without a line (4.3.4 'occurs automatically'); --line=no suppresses it"),
    "U16_erste_commands_mit_gespart": (True, "'first N Commands' (Situation Report, Comm Trouble) include saved Commands"),
    "U17_gegenangriff_staging": (False, "Counterattack: no PC markers on staging cards (map area only)"),
    "U18_fall_back_rand_offmap": (True, "Enemy Event Fall Back at the top map edge: unit leaves the board (8.6.3, no map extension)"),
    "U19_erweitern_bis_reichweite": (True, "Max LOS/Range: extend the map up to maximum range, because Hills could give visibility (wording of 8.4.5)"),
    "U20_mine_bei_seek_cover": (True, "successful Seek Cover on a mine card triggers a mine check (movement within the card)"),
    "U21_pyro_alle_einheiten": (True, "Signal applies to all units with LOS, including higher-ranking HQs (wording of 4.4.1; Stead says otherwise)"),
    "U22_munition_leer_im_clean_up": (True, "Out of Ammo consequences (flip/marker) only in Clean Up, after simultaneous combat"),
    "U24_assault_in_staging": (True, "Advance Straight Ahead (Assault) from the first card row also into the Staging Area toward US units"),
    "U27_mtr_sec_nicht_fa": (True, "Mtr Sec: C/L/P results as normal (Casualty/LAT), last remaining step becomes a 1-step Mortar Team (CSR 2)"),
    "U28_gegenangriff_alle_pc_a": (True, "during the counterattack all PC A markers use the Counter-Attack list (MSR 1 'any PC A Markers')"),
    "U29_ein_target_marker_he_wp": (True, "HE and WP of the same firing agency (15th FA) share one Target marker (7.16.5)"),
}
MUNITION_KAP = {"MG": 6, "MTR": 2, "RKT": 3, "RCL": 3}                  # [RULE 5.1.6A p.33] per step
PYRO_LUFT = ("RSP", "RSC", "GSP", "GSC", "Handheld Illumination")       # [RULE 4.4 p.30] Aerial: same or adjacent card
PYRO_FARBE = ("Red Smoke", "Green Smoke", "Yellow Smoke", "Purple Smoke")
PYRO_CODES_OFF = ("CF", "M2PO", "InfAP2PO", "M2SO", "InfAP2SO", "M2S")  # [RULE 4.4.1 p.30] plus XPL#
PYRO_CODES_PAT = ("CF", "M2PO", "M2S")  # [RULE 4.4.1 p.30] Patrol Mission, plus M2RP#
PC_DRAWS = {"A": {"No Contact": 0, "Contact": 7, "Engaged": 5, "Heavily Engaged": 3},
            "B": {"No Contact": 0, "Contact": 5, "Engaged": 3, "Heavily Engaged": 2},
            "C": {"No Contact": 4, "Contact": 3, "Engaged": 2, "Heavily Engaged": 1}}                 # 8.2.4 Chart
REICHWEITE = {"P": 0, "C": 1, "L": 2, "V": 3}                          # 1.2.6 Range


class Verstoss(Exception):
    pass


# ---------------------------------------------------------------- Load / save
def partie_dir():
    """Game folder: environment variable FOF_PARTIE (for tests, v3) before ROOT/.aktuelle_partie before 'partie1'."""
    import os
    if os.environ.get("FOF_PARTIE"):
        return ROOT / os.environ["FOF_PARTIE"]
    st = ROOT / ".aktuelle_partie"
    return ROOT / (st.read_text().strip() if st.exists() else "partie1")


def laden():
    p = partie_dir() / "spielstand.json"
    if not p.exists():
        sys.exit("No game state. First: fof.py new <aufbau.json>")
    return json.loads(p.read_text(encoding="utf-8"))


def speichern(s, eintrag=None, regel=None):
    fehler = pruefen(s)
    if fehler:
        raise Verstoss("Check prevents saving: " + "; ".join(fehler))
    if eintrag:
        s["protokoll"].append({"nr": len(s["protokoll"]) + 1, "zug": s["zug"], "phase": s["phase"],
                               "text": eintrag, "regel": regel,
                               "zeit": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    h = s.pop("_hinweise", None)
    for k in ("_befehl_opts", "_phase_alt"):
        s.pop(k, None)
    (partie_dir() / "spielstand.json").write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    if h:
        s["_hinweise"] = h          # v3: hints (e.g. radio path) are kept for output, not saved
    briefing(s)


def opts_parse(args):
    return {a.split("=")[0]: a.split("=", 1)[1] for a in args if a.startswith("--") and "=" in a}


# ---------------------------------------------------------------- Basic helpers
def sop(s):
    return SOP_DEFENSIV if s["typ"] == "defensiv" else SOP_OFFENSIV


def phase_name(s, pid=None):
    return dict(sop(s)).get(pid or s["phase"], "?")


def einheit(s, name):
    if name not in s["einheiten"]:
        raise Verstoss(f"Unit '{name}' unknown. Known: {', '.join(s['einheiten'])}")
    return s["einheiten"][name]


def karte(s, kid):
    if kid not in s["karten"]:
        raise Verstoss(f"Card '{kid}' unknown. Known: {', '.join(s['karten'])}")
    return s["karten"][kid]


def ist_hq(e):
    return e["typ"] in ("HQ", "Staff")


def ist_lat(e):
    return e["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team")


def pinned(e):
    return "Pinned" in e["status"]


def ft_seite(e):
    return "Fire Team side" in e["status"]


def good_order(e):
    return not pinned(e) and not ist_lat(e) and not ft_seite(e)


def steps(e):
    return e.get("steps", 1)


def auf(s, kid, seite=None):
    return [n for n, e in s["einheiten"].items() if e["karte"] == kid and (seite is None or e["seite"] == seite)]


def gegner(seite):
    return "Feind" if seite == "US" else "US"


def opt(s, key):
    """Value of an open rules question: setup 'optionen' before OPTIONEN_STANDARD."""
    return s.get("optionen", {}).get(key, OPTIONEN_STANDARD[key][0])


def offen(s, key):
    """Tag '[open Ux]' for output, only if the mission tracks open questions (setup 'optionen')."""
    return f" [open {key.split('_')[0]}]" if "optionen" in s else ""


def kompanie(s):
    """CO HQ is a unit on the board (CAC, campaign; also after its loss); PAC: co_hq = 'off-map'."""
    return s.get("co_hq") not in (None, "off-map")


def funk_aktiv(s):
    return bool(s.get("funk_aktiv"))


def moerser(e):
    return bool(e.get("moerser"))


def reichweite_grenzen(s, e):
    """[RULE 1.2.6 p.7] Range P/C/L/V; 'C-L' (Mtr Sec) = minimum and maximum range [open U12]."""
    r = e.get("reichweite", "V") or "V"
    if e.get("out_of_ammo"):
        return 0, 1                                                              # [RULE 7.18.2 p.61] Out of Ammo: range Close
    if ft_seite(e) and e.get("ft_reichweite"):
        r = e["ft_reichweite"]                                                       # E10: Fire Team side with its own range (German LMG: A/C)
    if "-" in r:
        a, b = r.split("-", 1)
        return REICHWEITE.get(a, 0), REICHWEITE.get(b, 3)
    return (1 if e.get("min_reichweite") == "C" else 0), REICHWEITE.get(r, 3)


def richtung(s, von, nach):
    ka, kb = karte(s, von), karte(s, nach)
    dr, dc = kb["reihe"] - ka["reihe"], kb["spalte"] - ka["spalte"]
    return ((dr > 0) - (dr < 0), (dc > 0) - (dc < 0))


def rand(c, d):
    """Edge colour of card c on the side facing direction d=(dr,dc); 'raender' as text (all sides) or
    object with oben/unten/links/rechts/diagonal (Gully: white edges on two sides only, FM1 p.34/p.45)."""
    r = c.get("raender")
    if r is None or isinstance(r, str):
        return r
    return r.get(SEITE_NAME.get(d, "diagonal"), r.get("rest"))


def erste_kartenreihe(s):
    return min(c["reihe"] for c in s["karten"].values() if not c.get("staging"))


def sichtbar(e):
    """US units always count as Spotted (8.5); enemies only with the flag."""
    return True if e["seite"] == "US" else bool(e.get("spotted"))


def gueltiges_ziel(s, kid, seite_schuetze):
    """Visible unit of the opposing side on the card (6.1.1)."""
    return [n for n in auf(s, kid, gegner(seite_schuetze)) if sichtbar(s["einheiten"][n])]


def abstand(s, a, b):
    ka, kb = karte(s, a), karte(s, b)
    return max(abs(ka["reihe"] - kb["reihe"]), abs(ka["spalte"] - kb["spalte"]))


def benachbart(s, a, b):
    return a != b and abstand(s, a, b) == 1


def karte_bei(s, r, c):
    for k, v in s["karten"].items():
        if v["reihe"] == r and v["spalte"] == c:
            return k
    return None


def linie(s, a, b):
    """Cards between a and b on one of the eight straight lines (excluding a and b); None if not on a straight line."""
    ka, kb = karte(s, a), karte(s, b)
    dr, dc = kb["reihe"] - ka["reihe"], kb["spalte"] - ka["spalte"]
    if a == b or not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return None
    n = max(abs(dr), abs(dc))
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    out = []
    for i in range(1, n):
        k = karte_bei(s, ka["reihe"] + sr * i, ka["spalte"] + sc * i)
        if k is None:
            return None
        out.append(k)
    return out


def blockiert(c, funk=False, s=None):
    """[RULE 5.4 p.38] Smoke, Incoming!, Air Strike! block LOS out of the card and through it.
    Radio (SCR536): [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke'; Incoming per option U3."""
    typen = ("Incoming", "AirStrike", "Smoke")
    if funk:
        typen = ("Incoming", "AirStrike") if (s is None or opt(s, "U3_incoming_blockiert_funk")) else ()
    return any(x["typ"] in typen for x in c.get("extern", []))


def durchsicht(c, von_d, nach_d):
    """[RULE 5.2.1 p.34] Entry and exit sides of the card crossed must be white. None = not recorded."""
    r = c.get("raender")
    if r is None:
        return None
    if isinstance(r, str):
        return r == "weiss"
    return rand(c, von_d) == "weiss" and rand(c, nach_d) == "weiss"


# ---------------------------------------------------------------- Visibility and Illumination (chapter 9)
def licht_wetter(s):
    """[RULE 9.0 p.69] Visibility modifier = Light Level + Weather. Legacy: 'visibility' counts as light."""
    l = s.get("licht")
    if l is None:
        l = s.get("visibility", 0) or 0
    return l, s.get("wetter", 0) or 0


def sicht_aktualisieren(s):
    """[RULE 9.0 p.69] +2 or more is Limited Visibility (9.1): 4 Commands per impulse, save limit G2/L4/V6, LOS Close Range."""
    l, w = licht_wetter(s)
    s["sicht"] = "eingeschraenkt" if l + w >= 2 else "tag"


def illum_wert(s, kid):
    """[RULE 9.2 p.70] best (lowest) Illumination modifier on kid: top value of the marker on kid,
    bottom value of markers on adjacent cards; not cumulative. None = not illuminated."""
    werte = []
    for k2, c in s["karten"].items():
        for m in c.get("illum", []):
            if k2 == kid:
                werte.append(m["oben"])
            elif m.get("unten") is not None and abstand(s, k2, kid) == 1:
                werte.append(m["unten"])
    return min(werte) if werte else None


def beleuchtet(s, kid):
    """[RULE 9.2.1 p.70] Illuminated only in Limited Visibility; never with Weather Conditions +2 or higher."""
    l, w = licht_wetter(s)
    return l + w >= 2 and w < 2 and illum_wert(s, kid) is not None


def sicht_karte(s, kid):
    """[RULE 9.0/9.2 p.69/70] Visibility modifier on kid: Illumination only mitigates light, light plus illum never better than +0."""
    l, w = licht_wetter(s)
    iw = illum_wert(s, kid)
    if iw is not None:
        l = max(0, l + iw)
    return l + w


def los(s, a, b, funk=False, staging_frei=False):
    """5.2.1/5.2.2/5.4: geometry, range, edge, Incoming/Smoke, elevation, staging. Returns (bool, reason).
    funk=True: LOS for SCR536 [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke' (range always up to Very Long)."""
    if a == b:
        return True, "same card"
    zw = linie(s, a, b)
    if zw is None:
        return False, "not on one of the eight straight lines [5.2.1]"
    maxr = 3 if funk else (1 if s["sicht"] == "eingeschraenkt" and not beleuchtet(s, b) else 3)   # [RULE 9.1, 9.2.1 p.70]
    if abstand(s, a, b) > maxr:
        return False, f"farther than {maxr} cards [5.2.1]"
    ka, kb = karte(s, a), karte(s, b)
    if (kb.get("staging") or ka.get("staging")) and not staging_frei:
        return False, "Staging Area: no LOS in or out [2.5]"
    if blockiert(ka, funk, s):
        return False, f"{a} has Incoming/Smoke, no LOS out [5.4]" + (offen(s, "U3_incoming_blockiert_funk") if funk else "")
    ea, eb = ka.get("elevation", 1), kb.get("elevation", 1)
    for z in zw:
        c = karte(s, z)
        if blockiert(c, funk, s):
            return False, f"Incoming/Smoke on {z} blocks [5.4]" + (offen(s, "U3_incoming_blockiert_funk") if funk else "")
        ez = c.get("elevation", 1)
        if ez > max(ea, eb) or (ez == max(ea, eb) and ez > min(ea, eb)):
            return False, f"{z} is higher than or as high as the lower point, blocks [5.2.2]"
        ds = durchsicht(c, richtung(s, z, a), richtung(s, z, b))
        if max(ea, eb) > ez:
            # [RULE 5.2.2 p.35] higher sees over lower despite dark edges; but 'straight up or downhill'
            # (level 3 to 1 across a level-2 card with dark edges) is blocked
            if ez > min(ea, eb) and ds is False:
                return False, f"{z} lies between the elevation levels and has dark edges (straight up/downhill) [5.2.2]"
            continue
        if ds is None:
            s.setdefault("_hinweise", []).append(f"LOS {a} to {b} passes through {z}: edge colours of {z} not recorded, check on the board (entry and exit sides white?) [5.2.1]")
        elif ds is False:
            return False, f"{z} has dark edges [5.2.1]"
    return True, "ok"


def in_reichweite(s, e, ziel):
    lo, hi = reichweite_grenzen(s, e)
    return lo <= abstand(s, e["karte"], ziel) <= hi


def cover_marker(s, e):
    """Cover marker the unit is under (or None)."""
    if e.get("bereich", "offen") == "offen" or e["karte"] not in s["karten"]:
        return None
    for c in s["karten"][e["karte"]].get("cover", []):
        if c["id"] == e["bereich"]:
            return c
    return None


def kein_pb(s, e):
    """No Point Blank fire: [RULE 5.3.2 p.37] units in Bunker/Pillbox; [RULE 7.3.1 p.52] mortars."""
    cv = cover_marker(s, e)
    return bool(e.get("kein_point_blank")) or moerser(e) or bool(cv and cv["typ"] in STRUKTUR)


def bogen_richtung(s, e):
    """Fire direction from Bunker/Pillbox [RULE 5.3.2 p.37]: marker field 'richtung' [dr,dc] or unit field 'bunker_richtung' (card, v2)."""
    cv = cover_marker(s, e)
    if cv and cv["typ"] in STRUKTUR and cv.get("richtung"):
        return tuple(cv["richtung"])
    return None


# ---------------------------------------------------------------- Derive fire (6.1 to 6.3)
def kann_feuern(e):
    if e.get("deep_bunker") and e.get("bereich") == e["deep_bunker"]:
        return False    # [CSR 5 p.14] Deep Bunker: units inside place no VOF
    if moerser(e) and ("Exposed" in e["status"] or e.get("indirekt")):
        return False    # [RULE 7.3.1 p.53] no fire with Exposed; [RULE 7.3.2 p.53] Indirect Lay replaces Direct Lay
    if e.get("tripod") and "Exposed" in e["status"] and not ft_seite(e):
        return False    # [RULE 7.2.1 p.51] tripod MG does not fire with an Exposed marker
    if e.get("vof_rating") == "G" and not ft_seite(e) and not e.get("out_of_ammo"):
        return False    # [RULE 7.3.2 p.53, 6.3.6 p.45] G! units fire only via Grenade Attack (Mortar Team: own PDF, 'nur_pdf')
    return bool(e.get("vof_rating")) and e["typ"] not in ("Litter Team", "Paralyzed Team", "Runner")


def feuert(e):
    return e.get("ziel") is not None and (kann_feuern(e) or bool(e.get("nur_pdf")))


def vof_rating_aktuell(e, point_blank):
    r = e.get("ft_vof", "S") if ft_seite(e) else e.get("vof_rating")
    if e.get("out_of_ammo"):
        return "S"                                                               # [RULE 7.18.2 p.61] Out of Ammo: VOF S
    if r == "S!":
        return "S"                                                               # [RULE 7.15 p.57] Sniper: Small Arms on the card, Sniper VOF on one target
    if r == "A/S":
        r = "A" if point_blank else "S"
    return r


def overhead_moeglich(s, von, zw, ziel):
    """[RULE 7.2.1 p.51] Elevation conditions for Overhead Fire over an intervening card."""
    lf, li, lt = (karte(s, k).get("elevation", 1) for k in (von, zw, ziel))
    return (li == lt and li <= lf - 1) or (li == lf and li <= lt - 1) or (li < lf and li < lt)


def feuerziel_effektiv(s, n):
    """6.1.1/6.1.2: VOF lies on the nearest occupied card along the PDF (unspotted enemies are fired over)."""
    e = s["einheiten"][n]
    z = e["ziel"]
    if z == e["karte"]:
        return z
    for k in (linie(s, e["karte"], z) or []):
        besetzt = [m for m in auf(s, k) if s["einheiten"][m]["seite"] == e["seite"] or sichtbar(s["einheiten"][m])]
        if moerser(e) or ((e.get("vof_rating") == "H" or e.get("tripod")) and overhead_moeglich(s, e["karte"], k, z)):
            # [RULE 7.3.1 p.53] mortars fire over cards with friendly troops without hitting them
            # [RULE 7.2.1 p.51] Overhead Fire (tripod MG, H VOF): "Do not place a VOF marker on the card being fired over."
            besetzt = [m for m in besetzt if s["einheiten"][m]["seite"] != e["seite"]]
        if besetzt:
            return k
    return z


def vof_eintraege(s, kid):
    """Fire effects on card kid: (typ, wert, quelle, trifft_seite or None=both, von_karte)."""
    out = []
    for n, e in s["einheiten"].items():
        if not feuert(e) or feuerziel_effektiv(s, n) != kid or e.get("nur_pdf"):
            continue
        pb = e["karte"] == kid
        typ = "Pinned" if pinned(e) else vof_rating_aktuell(e, pb)
        out.append((typ, VOF_WERT.get(typ, 0), n, gegner(e["seite"]) if pb else None, e["karte"]))
    for x in karte(s, kid).get("extern", []):
        if x["typ"] not in ("Pending", "Smoke"):                                   # [RULE 5.4 p.38] smoke is cover, not a VOF (v4 correction)
            out.append((x["typ"], x["wert"], x.get("quelle", x["typ"]), None, None))
    return out


def vof_gegen(s, kid, seite, ohne_minen=False):
    """Best (lowest) VOF that hits units of the side on kid: (typ, wert, [quellen]) or None.
    ohne_minen: Mines! markers count as VOF markers (Pinned Recovery, Rally, Infiltration, activity; BGG E35), but only hit
    the units that failed the mine check [RULE 6.3.6 p.45, 7.9.1 p.54]."""
    tr = [x for x in vof_eintraege(s, kid) if x[3] in (None, seite) and not (ohne_minen and x[0] == "Mines")]
    if not tr:
        return None
    best = min(x[1] for x in tr)
    return [x for x in tr if x[1] == best][0][0], best, [x[2] for x in tr]


def pdfs_nach(s, kid, seite_ziel):
    """Cards from which fire of the opposing side affects kid from outside."""
    return {e["karte"] for n, e in s["einheiten"].items()
            if feuert(e) and e["karte"] != kid and feuerziel_effektiv(s, n) == kid and e["seite"] == gegner(seite_ziel)}


def crossfire(s, kid, seite_ziel):
    """6.2.4: two or more PDFs from different directions from outside."""
    kz = karte(s, kid)
    richt = set()
    for k in pdfs_nach(s, kid, seite_ziel):
        kk = karte(s, k)
        dr, dc = kk["reihe"] - kz["reihe"], kk["spalte"] - kz["spalte"]
        richt.add(((dr > 0) - (dr < 0), (dc > 0) - (dc < 0)))
    return len(richt) >= 2


def aktivitaet_erwartet(s):
    """8.1 / Charts 1: No Contact only without any VOF/PDF marker and without a spotted enemy."""
    vk = [k for k in s["karten"] if vof_eintraege(s, k)]
    besetzt = [k for k in vk if auf(s, k)]
    spotted = any(e["seite"] == "Feind" and e.get("spotted") for e in s["einheiten"].values())
    pdf = any(feuert(e) and e["ziel"] != e["karte"] for e in s["einheiten"].values())
    pending = any(x["typ"] == "Pending" for c in s["karten"].values() for x in c.get("extern", []))
    if len(besetzt) >= 2 and any(auf(s, k, "US") and auf(s, k, "Feind") for k in besetzt):
        return "Heavily Engaged"
    if len(besetzt) >= 2:
        return "Engaged"
    if vk or spotted or pdf or pending:
        return "Contact"
    return "No Contact"


def aktivitaet_berechnen(s):
    if s.get("aktivitaet") is None or s["phase"] == "3.7.4":
        return None
    alt, neu = s["aktivitaet"], aktivitaet_erwartet(s)
    s["aktivitaet"] = neu
    return None if alt == neu else f"Activity level {alt} becomes {neu}: move the Activity marker [8.1]"


def feuerstellung_verboten(s, e):
    """Reason why a unit may not fire at all from its card, otherwise None."""
    if moerser(e):
        c = karte(s, e["karte"])
        if "Woods" in c.get("terrain", "") or c.get("moerser_verbot"):
            return "Mortars do not fire from Woods [RULE 7.3.1 p.53, FM1 p.36]"
        cv = cover_marker(s, e)
        if cv and cv["typ"] in STRUKTUR + ("Building", "Cave"):
            return "Mortars do not fire from Building/Bunker/Cave/Pillbox [RULE 7.3.1 p.52]"
    return None


def feuerkandidaten(s, n):
    e = s["einheiten"][n]
    kand = []
    if feuerstellung_verboten(s, e):
        return kand
    bogen = bogen_richtung(s, e)
    for kid in s["karten"]:
        if kid == e["karte"]:
            if kein_pb(s, e):
                continue
            if not in_reichweite(s, e, kid):
                continue
        else:
            if not in_reichweite(s, e, kid) or not los(s, e["karte"], kid)[0]:
                continue
            if e["seite"] == "US" and auf(s, kid, "US"):
                continue                                                                    # 8.4.3: friendly units do not open fire on jointly occupied cards
            if not moerser(e) and e.get("vof_rating") != "H" and any(auf(s, zw, e["seite"]) for zw in (linie(s, e["karte"], kid) or [])):
                continue                                                                    # [RULE 6.1.1 p.40 ex. 2, K16] VOF would land on the friendly intervening card; only H (Overhead) and mortars fire over it
            if e.get("bunker_richtung") and kid != e["bunker_richtung"] and e["bunker_richtung"] not in ((linie(s, e["karte"], kid) or []) + [kid]):
                continue
            if bogen and richtung(s, e["karte"], kid) != bogen:
                continue                                                                    # [RULE 5.3.2 p.37] only in the arrow direction
        if gueltiges_ziel(s, kid, e["seite"]):
            kand.append(kid)
    return kand


def pdf_hinweis(s, von, nach, n):
    """V20 (the player): with every new PDF, state whether the source card has further PDFs."""
    andere = sorted({x["ziel"] for m, x in s["einheiten"].items()
                     if m != n and x.get("karte") == von and x.get("ziel") and x["ziel"] not in (von, nach) and feuert(x)})
    return f" (further PDF from {von}: to {', '.join(andere)})" if andere else f" (no other PDF from {von})"


def feuer_eroeffnen(s, prot, nur=None):
    """6.1.1: unengaged units with a VOF rating open fire automatically. Tie: random choice by the player."""
    for n, e in s["einheiten"].items():
        if nur is not None and n not in nur:
            continue
        if e.get("ziel") is not None or not kann_feuern(e) or e.get("karte") not in s["karten"] or karte(s, e["karte"]).get("staging"):
            continue
        if e.get("kein_feuer_bis_clean_up"):
            continue                                                                # [RULE 8.3 p.63] Place PDF/VOF No: opens fire only in Clean Up
        kand = feuerkandidaten(s, n)
        if not kand:
            e.pop("ziel_offen", None)
            continue
        if e["seite"] == "US":
            d = min(abstand(s, e["karte"], k) for k in kand)
            kand = [k for k in kand if abstand(s, e["karte"], k) == d]
            if len(kand) > 1:
                def vof_von(k):
                    w = [x[1] for x in vof_eintraege(s, e["karte"]) if x[4] == k]
                    return min(w) if w else 99
                b = min(vof_von(k) for k in kand)
                kand = [k for k in kand if vof_von(k) == b]
        else:
            def us_steps(k):
                return sum(steps(s["einheiten"][m]) for m in gueltiges_ziel(s, k, "Feind"))
            m = max(us_steps(k) for k in kand)
            kand = [k for k in kand if us_steps(k) == m]
        if len(kand) == 1:
            cf_vorher = crossfire(s, kand[0], gegner(e["seite"]))
            e["ziel"] = kand[0]
            e.pop("ziel_offen", None)
            prot.append(f"{n} opens fire on {kand[0]}" + (" (Point Blank)" if kand[0] == e["karte"] else f", PDF from {e['karte']} to {kand[0]}" + pdf_hinweis(s, e['karte'], kand[0], n)) + (" with Pinned VOF" if pinned(e) else "") + " [6.1.1]")
            if not cf_vorher and crossfire(s, kand[0], gegner(e["seite"])):
                prot.append(f"Crossfire marker on {kand[0]} (PDFs from two directions) [6.2.4]")
        else:
            e["ziel_offen"] = kand
            prot.append(f"{n}: determine fire target by R# from {', '.join(kand)}, then fof.py fire \"{n}\" <card> [6.1.1]")


def feuer_nach_bewegung(s, n, prot):
    """6.1.2: movement to another card = Cease Fire, then 6.1.1 again; firing opponents on the new card shift to Point Blank."""
    e = s["einheiten"][n]
    if e.get("ziel") is not None:
        prot.append(f"{n} ceases fire due to the movement (adjust PDF/VOF) [6.1.2]")
        e["ziel"] = None
        e.pop("konzentriert", None)
    feuer_eroeffnen(s, prot, nur=[n])
    for m, f in s["einheiten"].items():
        if f["seite"] != e["seite"] and f["karte"] == e["karte"] and feuert(f) and f["ziel"] != f["karte"] and sichtbar(e) and not kein_pb(s, f):
            f["ziel"] = f["karte"]
            prot.append(f"{m} shifts fire to its own card (Point Blank) [6.1.2]")
    # [RULE 3.0 p.15, 6.1.1 p.39] after every board change all unengaged units with a valid target open fire
    feuer_eroeffnen(s, prot)


def cover_von(s, e):
    if e.get("bereich", "offen") == "offen":
        return None
    for c in karte(s, e["karte"]).get("cover", []):
        if c["id"] == e["bereich"]:
            return c
    return None


# ---------------------------------------------------------------- Radio (4.3.3, 4.3.5, 2.5)
def geraete(e, typ=None, netz=None):
    """Radios carried by the unit (setup field 'funk': [{typ, netz}]); destroyed ones do not count."""
    return [g for g in e.get("funk", []) if not g.get("zerstoert") and (typ is None or g["typ"] == typ) and (netz is None or g["netz"] == netz)]


def funk_los(s, a, b):
    """SCR536 LOS: [RULE 2.5 p.12] within staging and to adjacent cards of row 1; otherwise 5.2.1/5.2.2 [RULE 4.3.5 p.29]."""
    ka, kb = karte(s, a), karte(s, b)
    if ka.get("staging") and kb.get("staging"):
        return True, "both in the Staging Area, radio LOS always exists [RULE 2.5 p.12]"
    if ka.get("staging") or kb.get("staging"):
        st, mp = (a, b) if ka.get("staging") else (b, a)
        if karte(s, mp)["reihe"] == erste_kartenreihe(s) and benachbart(s, st, mp):
            return True, f"Staging {st} and adjacent card {mp} of row 1 [RULE 2.5 p.12]"
        if opt(s, "U10_staging_funk_ueber_hill"):
            ok, g = los(s, a, b, funk=True, staging_frei=True)
            return ok, g + offen(s, "U10_staging_funk_ueber_hill")
        return False, f"from the Staging Area only to adjacent cards of row 1 [RULE 2.5 p.12]{offen(s, 'U10_staging_funk_ueber_hill')}"
    # radio traffic goes both ways: LOS must exist from both ends (5.4 makes LOS one-sided with Incoming) [open U3]
    ok, g = los(s, a, b, funk=True)
    if ok:
        ok, g = los(s, b, a, funk=True)
    return ok, g


def funk_direkt(s, a_name, b_name, typ="SCR536", netz="CO TAC"):
    """Direct radio link between two units: both carry a device of the net, SCR536 not under a cover marker and only with LOS."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    if not geraete(a, typ, netz):
        return False, f"{a_name} has no {typ} {netz}"
    if not geraete(b, typ, netz):
        return False, f"{b_name} has no {typ} {netz}"
    if typ == "SCR536":
        for n, e in ((a_name, a), (b_name, b)):
            if e.get("bereich", "offen") != "offen":
                return False, f"{n} is under cover marker {e['bereich']}; SCR536 does not work there [RULE 4.3.5 p.29, FM1 p.50]"
        ok, g = funk_los(s, a["karte"], b["karte"])
        if not ok:
            return False, f"no radio LOS {a['karte']} to {b['karte']}: {g} [RULE 4.3.5 p.29]"
        return True, f"{typ} {netz}, LOS {a['karte']} to {b['karte']} ({g})"
    return True, f"{typ} {netz} [RULE 4.3.5 p.29]"


def funk_verbindung(s, a_name, b_name):
    """CO TAC Net [RULE 4.3.3 p.27]: the CO HQ is the hub; (None, '') if neither unit has a radio."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    if not (geraete(a) or geraete(b)) or not funk_aktiv(s):
        return None, ""
    if s.get("co_tac_mittel") == "telefon":
        return telefon_verbindung(s, a_name, b_name)                             # [CSR 1 p.13, 4.3.4 p.28]
    for n, e in ((a_name, a), (b_name, b)):
        if not geraete(e, "SCR536", "CO TAC"):
            return False, f"{n} has no SCR536 CO TAC (FOs may not join the CO TAC Net, [RULE 4.3.3 p.28])" if e["typ"] == "FO" else f"{n} has no SCR536 CO TAC"
    co = s.get("co_hq")
    if co in (a_name, b_name):
        return funk_direkt(s, a_name, b_name)
    if co not in s["einheiten"]:
        return False, "CO HQ (hub of the CO TAC Net) not in play [RULE 4.3.3 p.27]"
    if not opt(s, "U11_plt_mtr_ueber_hub"):
        return False, "only links with the CO HQ itself [RULE 4.3.3 p.27]" + offen(s, "U11_plt_mtr_ueber_hub")
    ok1, g1 = funk_direkt(s, a_name, co)
    ok2, g2 = funk_direkt(s, co, b_name)
    if ok1 and ok2:
        return True, f"via the hub {co}: {g1}; {g2} [RULE 4.3.5 p.29]" + offen(s, "U11_plt_mtr_ueber_hub")
    return False, f"via the hub {co}: " + (g1 if not ok1 else g2) + offen(s, "U11_plt_mtr_ueber_hub")


def bn_verbindung(s):
    """[RULE 4.1.1 p.18] BN HQ off-map activates the CO HQ if it is in communication via BN TAC."""
    co = s.get("co_hq")
    if co not in s["einheiten"]:
        return False, "CO HQ not in play"
    if s.get("co_immer_in_kommunikation") or not funk_aktiv(s):
        return True, "always in communication per the mission"
    if not geraete(s["einheiten"][co], "SCR300", "BN TAC"):
        return False, f"{co} carries no working SCR300 BN TAC [RULE 4.3.3 p.28, FM1 p.50]"
    return True, "SCR300 BN TAC, works everywhere [RULE 4.3.5 p.29]"


# ---------------------------------------------------------------- Communication, chain of command, permission
def visual_verbal(s, hq_name, ziel_name, akt=None):
    hq, z = einheit(s, hq_name), einheit(s, ziel_name)
    if hq["karte"] != z["karte"]:
        raise Verstoss(f"{hq_name} ({hq['karte']}) and {ziel_name} ({z['karte']}) not on the same card, no Visual-Verbal communication [RULE 4.3.1 p.27]")
    if hq.get("bereich", "offen") != z.get("bereich", "offen"):
        raise Verstoss(f"{hq_name} and {ziel_name} in different areas of {hq['karte']} (cover marker/open) [RULE 4.3.1 p.27]")
    if pinned(hq):
        raise Verstoss(f"{hq_name} is Pinned and cannot give Visual-Verbal orders [RULE 4.3.1 p.27]")
    if pinned(z) and akt not in ("4.2.3a", "4.2.1b"):
        raise Verstoss(f"{ziel_name} is Pinned; via Visual-Verbal only 'Attempt to Remove a Pinned marker' (4.2.3a) and a subsequent Exhort [RULE 4.3.1 p.27]")
    return True


def kommunikation(s, hq_name, ziel_name, akt=None):
    """4.3.1 Visual-Verbal: same card, same area, both Unpinned. Exception: Rally/Exhort to Pinned.
    Radio: field 'netz' (v2) or radios 'funk' (v3: SCR536 CO TAC with LOS, not under cover, CO HQ as hub)."""
    hq, z = einheit(s, hq_name), einheit(s, ziel_name)
    if hq_name == ziel_name:
        return True
    if hq.get("netz") and z.get("netz") and hq["netz"] == z["netz"]:
        return True
    # FM1 CAC Run 1 p.36: 'assume that the CO HQ is always in communication with the PLT HQs and with the mortar section'
    if s.get("co_immer_in_kommunikation") and hq_name == s.get("co_hq") and ziel_name in s.get("co_immer_in_kommunikation_mit", []):
        return True
    try:
        return visual_verbal(s, hq_name, ziel_name, akt)
    except Verstoss as vv:
        ok, grund = funk_verbindung(s, hq_name, ziel_name)
        if ok:
            s.setdefault("_hinweise", []).append(f"Communication {hq_name} with {ziel_name} by {'phone' if s.get('co_tac_mittel') == 'telefon' else 'radio'}: {grund}")
            return True
        if ok is None:
            raise
        raise Verstoss(f"{vv}; radio: {grund}")


def kommandokette(s, hq_name, ziel_name):
    """4.0 p.18 Command Reference Table: PLT HQ orders its own platoon units and any LAT; CO HQ/Staff everything except higher HQs."""
    hq, z = einheit(s, hq_name), einheit(s, ziel_name)
    if hq_name == ziel_name or ist_lat(z):
        return True
    if hq["typ"] == "Staff" or hq.get("ebene") in ("CO", "BN"):
        if hq["typ"] == "Staff" and z.get("ebene") in ("CO", "BN"):
            raise Verstoss("Staff may not order a higher HQ [RULE 4.0 p.18]")
        if hq["typ"] == "Staff" and z["typ"] == "Staff" and z.get("rang", 9) < hq.get("rang", 9):
            raise Verstoss(f"{hq_name} may not order {ziel_name} (Command Reference Table: 1st Sgt not to CO XO) [RULE 4.0 p.18]")
        return True
    if z.get("platoon") != hq.get("platoon") and hq_name not in z.get("attached_an", []):
        raise Verstoss(f"{ziel_name} is not in the chain of command of {hq_name} (Platoon {hq.get('platoon')}) [RULE 4.0 p.18]")
    return True


def aktion_erlaubt(z, ziel_name, akt):
    """4.2.5: Pinned takes precedence, then LAT lists, Fire Team side like Fire Team."""
    name = AKTIONEN[akt][0]
    cc = akt.startswith("4.2.1")
    if z.get("stationaer") and akt.startswith("4.2.2"):
        raise Verstoss(f"{ziel_name} is not part of the patrol: orders and fire yes, but no movement (except automatic retreat) [Normandy M3 MSR 1]")
    if pinned(z) and akt not in PINNED_ERLAUBT and not cc:
        raise Verstoss(f"{ziel_name} is Pinned: only Move to Adjacent (staging/friendly card without VOF), Seek Cover, Move within a Card, Rally 4.2.3a are allowed; no Combat Actions [RULE 4.2.5 p.26]")
    if pinned(z) and akt in PINNED_ERLAUBT:
        return                                   # Pinned takes precedence over the LAT lists (4.2.5)
    if z["typ"] in LAT_ERLAUBT and akt not in LAT_ERLAUBT[z["typ"]] and not cc:
        raise Verstoss(f"{z['typ']} may not perform '{name}' [RULE 4.2.5 p.26]")
    if ft_seite(z) and akt not in LAT_ERLAUBT["Fire Team"] | {"4.2.3f"} and not cc:
        raise Verstoss(f"{ziel_name} is on its Fire Team side and acts like a Fire Team [RULE 4.2.5 p.26, 6.4.3 p.47]")


def erfahrung(e):
    if ist_lat(e):
        return LAT_ERFAHRUNG[e["typ"]]
    if ft_seite(e):
        return "Green"
    return e.get("erfahrung", "Line")



def feind_rally_karten(e):
    """[RULE 6.5.1 p.48] Rally under VOF: 2 cards, modified by the experience of the commander; for the enemy the unit itself (L fix 08.10.2026)."""
    ez = e.get("erfahrung")
    return max(1, 2 + {"Green": -1, "Veteran": 1}.get(ez, 0)), ez

def kartenzahl(s, akt, orig, z, extra=0, basis_cff=None):
    """4.2 p.21: base 2 (Seek Cover: card; Call for Fire: mission); experience of the recipient (movement/combat) or of the originator (Rally).
    Clarification 1: 0 cards = not possible (except Spotting: minimum 1)."""
    if akt == "4.2.2e":
        basis = karte(s, z["karte"]).get("cover_draw")
        if basis is None:
            raise Verstoss(f"Cover draw number of card {z['karte']} not recorded (bottom centre of the terrain card)")
    elif akt == "4.2.4i":
        basis = basis_cff if basis_cff is not None else s.get("cff_karten", 2)   # [RULE 7.16.1 p.58] number according to the actual observer
    else:
        basis = 2
    wer = orig if akt.startswith("4.2.3") else z
    if akt == "4.2.4a":
        # [RULE 8.5 Spotting Chart] the spotter's experience is already in spot_modifikatoren ("Spotting Recipient is Green -1 / Veteran +1"), do not count it twice (L41)
        return max(1, basis + extra), wer, basis
    n = basis + {"Green": -1, "Veteran": 1}.get(erfahrung(wer), 0) + extra
    if n <= 0:
        raise Verstoss(f"Number of cards {n}: attempt not possible [Clarification 1 to 4.2, May 2025]")
    return n, wer, basis


def spot_modifikatoren(s, sp, zielkarte):
    """8.5 Spotting Attempt Draw Modifiers Chart (Charts & Tables 1)."""
    mods = []
    ez = erfahrung(sp)
    if ez == "Green":
        mods.append(("Spotter Green", -1))
    if ez == "Veteran":
        mods.append(("Spotter Veteran", +1))
    ks, kz = karte(s, sp["karte"]), karte(s, zielkarte)
    if ks.get("elevation", 1) > kz.get("elevation", 1):
        mods.append(("Spotter higher", +1))
    feinde = [s["einheiten"][n] for n in auf(s, zielkarte, "Feind")]
    if any(f.get("bereich", "offen") != "offen" for f in feinde):
        mods.append(("Target under cover", -1))
    if any(f.get("typname") in ("Sniper", "Spotter") for f in feinde):
        mods.append(("Target Sniper/FO", -1))
    if any(erfahrung(f) == "Veteran" for f in feinde):
        mods.append(("Target Veteran", -1))
    if any(erfahrung(f) == "Green" for f in feinde):
        mods.append(("Target Green", +1))
    cc = kz.get("cc", 0)
    if kz.get("cc2") is not None and zielkarte != sp["karte"] and rand(kz, richtung(s, zielkarte, sp["karte"])) == "weiss":
        cc = kz["cc2"]      # [PLAYER AID Charts & Tables 1, Spotting Chart *] lower value when spotting across a white edge (5.2.3)
    if cc >= 3:
        mods.append(("Target card C&C +3 or more", -1))
    if cc == 0:
        mods.append(("Target card C&C +0", +1))
    if zielkarte == sp["karte"]:
        mods.append(("same card", +1))
    if any("Exposed" in f["status"] for f in feinde):
        mods.append(("Target Exposed", +2))
    if any(f.get("vof_rating") == "A" for f in feinde):
        mods.append(("Target with VOF A", +1))     # A/S does not count [FM1 p.43 Note]
    if any(f.get("vof_rating") in ("H", "G") for f in feinde):
        mods.append(("Target with VOF H or G!", +2))
    return mods


# ---------------------------------------------------------------- Check, briefing
def pruefen(s):
    f = []
    for n, e in s["einheiten"].items():
        if e["karte"] is None and v4(s) and in_aufstellung(s):
            continue                                                                  # v4: start card is chosen with 'setup'
        if e["karte"] not in s["karten"]:
            f.append(f"{n} on unknown card {e['karte']}")
            continue
        for m in set(e["status"]):
            if e["status"].count(m) > 1:
                f.append(f"{n} duplicate {m}")
        if e.get("bereich", "offen") != "offen" and cover_von(s, e) is None:
            f.append(f"{n}: area {e['bereich']} does not exist on {e['karte']}")
        if e.get("ziel") and e["ziel"] not in s["karten"]:
            f.append(f"{n} fires at unknown card {e['ziel']}")
        if e.get("letzter_step") and e.get("fire_team_seite"):
            f.append(f"{n}: letzter_step and fire_team_seite are mutually exclusive")
    for kid in s["karten"]:
        fe = [s["einheiten"][n] for n in auf(s, kid, "Feind")]
        if fe and len({bool(x.get("spotted")) for x in fe}) > 1:
            f.append(f"{kid}: enemies mixed Spotted/Unspotted [8.5]")
        for cv in karte(s, kid).get("cover", []):
            seiten = {s["einheiten"][n]["seite"] for n in auf(s, kid) if s["einheiten"][n].get("bereich") == cv["id"]}
            if len(seiten) > 1:
                f.append(f"{kid}: cover {cv['id']} occupied by both sides [5.3]")
            if cv.get("kapazitaet"):
                st = sum(steps(s["einheiten"][n]) for n in auf(s, kid) if s["einheiten"][n].get("bereich") == cv["id"])
                if st > cv["kapazitaet"]:
                    f.append(f"{kid}: {cv['typ']} {cv['id']} with {st} steps, capacity {cv['kapazitaet']} [5.3.2]")
    for n, k in s["kommandos"].items():
        if k["verfuegbar"] < 0 or k["gespart"] < 0:
            f.append(f"{n}: negative Commands")
    if s["phase"] not in dict(sop(s)):
        f.append(f"Phase {s['phase']} not in the sequence of play")
    if s.get("aktivitaet") is not None and s["phase"] != "3.7.4" and aktivitaet_erwartet(s) != s["aktivitaet"]:
        f.append(f"Activity level is {s['aktivitaet']}, the board implies {aktivitaet_erwartet(s)} [8.1]")
    if s.get("ccp") and s["ccp"] not in s["karten"]:
        f.append(f"CCP on unknown card {s['ccp']}")
    return f


def stempel(s):
    f = pruefen(s)
    if f:
        return "CHECKSTAMP: ERROR " + "; ".join(f)
    off = [n for n, e in s["einheiten"].items() if e.get("ziel_offen")]
    return f"CHECKSTAMP OK Turn {s['zug']} Phase {s['phase']} Entry {len(s['protokoll'])}" + (f" (open: fire target {', '.join(off)})" if off else "")


def funk_uebersicht(s):
    """Connections of the CO HQ: BN TAC and CO TAC to every other radio."""
    co = s["co_hq"]
    out = []
    ok, g = bn_verbindung(s)
    out.append(f"BN HQ (off-map) with {co}: {'yes' if ok else 'NO'}, {g}")
    if co not in s["einheiten"]:
        out.append(f"{co} not in play: no hub for the CO TAC Net [RULE 4.3.3 p.27]; reconstitution per 6.5.2 p.49/50 (new CO HQ needs a BN TAC device, FM1 p.38)")
    for n, e in s["einheiten"].items():
        if n == co or not [g for g in e.get("funk", []) if "FD" not in g.get("netz", "")] or co not in s["einheiten"]:
            continue
        if e.get("karte") is None or s["einheiten"][co].get("karte") is None:
            out.append(f"{co} with {n}: start card still missing")
            continue
        ok, g = funk_verbindung(s, co, n)
        out.append(f"{co} with {n}: {'yes' if ok else 'no'}, {g}")
    for n, e in s["einheiten"].items():
        if e["typ"] == "FO":
            fd = [x for x in geraete(e) if "FD" in x["netz"]]
            out.append(f"{n}: {'FD radio ' + fd[0]['netz'] if fd else ('FD radio implied' + offen(s, 'U2_fo_fd_funk') if opt(s, 'U2_fo_fd_funk') else 'no FD radio' + offen(s, 'U2_fo_fd_funk'))}")
    return out


def ziel_stand(s):
    """Mission objective CAC: eliminate all enemies [FM1 p.36], clear all PC markers [FM1 p.48]. v4: secure objectives, clear rows."""
    if "sichern" in s.get("ziel_regeln", {}):
        ok, txt = ziel_stand_v4(s)
        return txt + f"; objective {'FULFILLED' if ok else 'open'}, turn {s['zug']} of {s['max_zuege']}, attempt {s['kampagne'].get('versuch', 1)} of {s['kampagne'].get('versuche_max', 1)}"
    feinde = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind"]
    pcs = [k for k, c in s["karten"].items() if c.get("pc")]
    t = f"{len(feinde)} enemy units on the board" + (f" ({', '.join(feinde)})" if feinde else "")
    if s["ziel_regeln"].get("pc_klaeren"):
        t += f", {len(pcs)} PC markers open" + (f" ({', '.join(pcs)})" if pcs else "")
    erfuellt = not feinde and not (s["ziel_regeln"].get("pc_klaeren") and pcs)
    t += f"; objective {'FULFILLED' if erfuellt else 'open'}, turn {s['zug']} of {s['max_zuege']}"
    if "optionen" in s:
        t += f"; 'eliminate' per reading {opt(s, 'U9_ziel_lesart')}{offen(s, 'U9_ziel_lesart')}"
    return t


def einheit_text(n, e):
    t = n
    if steps(e) != 1:
        t += f"({steps(e)}St)"
    st = list(e["status"])
    if e["seite"] == "Feind":
        st.append("spotted" if e.get("spotted") else "unspotted")
    if e.get("bereich", "offen") != "offen":
        st.append(f"in {e['bereich']}")
    if e.get("ziel"):
        st.append("fires at " + e["ziel"])
    if e.get("ziel_offen"):
        st.append("TARGET OPEN")
    if e.get("cf"):
        st.append(f"CF x{e['cf']}")
    if e.get("funk"):
        st.append("Radio " + "/".join(g["typ"] + ("(destroyed)" if g.get("zerstoert") else "") for g in e["funk"]))
    if e.get("traegt_casualties"):
        st.append(f"carries {e['traegt_casualties']} Casualty")
    if e.get("indirekt"):
        st.append("Indirect Lay")
    if e.get("munition"):
        st.append(f"{e['munition']['typ']} {e['munition']['punkte']}" + (" OUT OF AMMO" if e.get("out_of_ammo") else ""))
    if e.get("traegt_munition"):
        st.append(f"carries {e['traegt_munition']['punkte']} {e['traegt_munition']['typ']}")
    if e.get("mine_hit"):
        st.append("under Mine marker")
    if e.get("assets"):
        st.append("Assets " + "/".join(e["assets"]))
    if e.get("leitungen"):
        st.append(f"{e['leitungen']} Phone Line(s)")
    if e.get("runner_ziel"):
        st.append(f"Runner for {e['runner_ziel']}")
    if e.get("nur_pdf"):
        st.append("PDF (Grenade Attack)")
    if e.get("kein_feuer_bis_clean_up"):
        st.append("opens fire in Clean Up")
    if e.get("karte") is None:
        st.append("START CARD OPEN")
    return t + (" [" + ", ".join(st) + "]" if st else "")


def briefing(s):
    z = [f"# BRIEFING {s['mission']}",
         f"Turn {s['zug']} of {s['max_zuege']}, Phase {s['phase']} {phase_name(s)}",
         f"Visibility {({'eingeschraenkt': 'limited', 'tag': 'day'}).get(s['sicht'], s['sicht'])}" + (" (light {0:+d}, weather {1:+d})".format(*licht_wetter(s)) if sum(licht_wetter(s)) else "") + f", activity {s.get('aktivitaet') or 'not tracked'}, active HQ {s.get('aktiver_hq') or 'none'}", ""]
    if s.get("patrouille_mission") and s.get("patrouille"):
        p = s["patrouille"]
        zr = s.get("ziele", {}).get("route", {})
        z.append(f"Patrol Platoon {p.get('platoon') or '-'}: route " + ", ".join(f"{i}:{zr.get(str(i)) or '-'}" for i in (1, 2, 3, 4))
                 + f", reached {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primaer_besucht') else 'open'}, success {'yes' if p.get('erfolg') else 'no'}; done: {', '.join(p.get('erledigt', [])) or '-'}")
        z.append("")
    z.append("## Commands")
    for n, k in s["kommandos"].items():
        z.append(f"- {n}: available {k['verfuegbar']}, saved {k['gespart']}, activated {'yes' if k['aktiviert'] else 'no'}, done {'yes' if k['fertig'] else 'no'}")
    z.append("")
    z.append("## Board (card terrain (C&C) [markers]: units)")
    for kid, k in sorted(s["karten"].items(), key=lambda x: (-x[1]["reihe"], x[1]["spalte"])):
        extra = []
        for cv in k.get("cover", []):
            extra.append(f"Cover {cv['id']} {cv['typ']} +{cv['wert']}" + (f" ({cv['kapazitaet']})" if cv.get("kapazitaet") else "")
                         + (f" arrow {SEITE_NAME.get(tuple(cv['richtung']), 'diagonal')} {tuple(cv['richtung'])}" if cv.get("richtung") else ""))
        vu, vf = vof_gegen(s, kid, "US", ohne_minen=True), vof_gegen(s, kid, "Feind", ohne_minen=True)
        if vu and auf(s, kid, "US"):
            extra.append(f"VOF on US: {VOF_NAME.get(vu[0], vu[0])} {vu[1]:+d} from {','.join(vu[2])}" + (" +Crossfire" if crossfire(s, kid, "US") else ""))
        if vf and auf(s, kid, "Feind"):
            extra.append(f"VOF on enemy: {VOF_NAME.get(vf[0], vf[0])} {vf[1]:+d} from {','.join(vf[2])}" + (" +Crossfire" if crossfire(s, kid, "Feind") else ""))
        if (vu or vf) and not auf(s, kid):
            v = vu or vf
            extra.append(f"VOF on empty card: {VOF_NAME.get(v[0], v[0])} from {','.join(v[2])}")
        for x in k.get("extern", []):
            if x["typ"] == "Pending":
                extra.append(f"Pending Fire Mission {x['wert']}" + (f" ({x['agentur']})" if x.get("agentur") else ""))
        if k.get("grenade_miss"):
            extra.append("Grenade Miss")
        for m in k.get("illum", []):
            extra.append(f"Illumination {m['oben']:+d}" + (f"/{m['unten']:+d}" if m.get("unten") is not None else "") + f" ({m.get('quelle', '?')})")
        if s["sicht"] == "eingeschraenkt" and beleuchtet(s, kid):
            extra.append(f"illuminated (visibility {sicht_karte(s, kid):+d})")
        if k.get("pc"):
            extra.append("PC " + k["pc"])
        if k.get("casualties"):
            extra.append(f"US casualties {k['casualties']}")
        if k.get("casualties_feind"):
            extra.append(f"enemy casualties {k['casualties_feind']}")
        for g in k.get("assets", []):
            extra.append(f"lying here: {g['typ']} {g['netz']}" + (" (R# 1/2 open: fof.py radio damage)" if g.get("schaden_offen") else ""))
        if s.get("ccp") == kid:
            extra.append("CCP")
        for x in k.get("extern", []):
            if x["typ"] == "Mines":
                extra.append("Mines! " + ("triggered" if x.get("aktiv") else "(Draw 3)"))
            if x["typ"] == "Smoke":
                extra.append(f"Smoke {x.get('quelle', '')} +{x.get('wert', 0)}")
        for l in k.get("leitungen", []):
            extra.append("Phone Line" + (" CUT" if l.get("cut") else ""))
        if k.get("leitung_assets"):
            extra.append(f"{k['leitung_assets']} Phone Line(s) lying here")
        for mt, mz in k.get("munition", {}).items():
            if mz:
                extra.append(f"Ammo {mt} {mz}")
        for py in k.get("pyro", []):
            extra.append(f"Signal {py}")
        if k.get("pc2"):
            extra.append("second PC " + k["pc2"])
        for zn, zk in s.get("ziele", {}).items():
            if zk == kid and zn != "phaselines":
                extra.append({"primaer": "Primary Objective", "sekundaer": "Secondary Objective", "ap": "Attack Position", "ccp": "CCP (preset)"}.get(zn, zn))
        if k.get("ausserhalb"):
            extra.append("outside the boundaries")
        for sp, tk in s.get("feind_target", {}).items():
            if tk == kid:
                extra.append(f"enemy Target marker ({sp})")
        for ag, tk in s.get("target_marker", {}).items():
            if tk == kid:
                extra.append(f"Target marker {ag}")
        eins = [einheit_text(n, s["einheiten"][n]) for n in auf(s, kid)]
        cc_txt = f"+{k.get('cc', 0)}" + (f"/+{k['cc2']}" if k.get("cc2") is not None else "") if k.get("cc") is not None else "C&C open"
        z.append(f"- {kid} {k['terrain'] or 'TERRAIN NOT SET'} ({cc_txt}){' [' + '; '.join(extra) + ']' if extra else ''}: {', '.join(eins) if eins else '-'}")
    ohne_k = [n for n, e in s["einheiten"].items() if e.get("karte") is None]
    if ohne_k:
        z.append("- Start card open: " + ", ".join(ohne_k))
    if s.get("fm_werte"):
        z.append(f"- Fire Missions: {s.get('feuermissionen')}; " + ", ".join(f"{a} {w:+d}" for a, w in s["fm_werte"].items())
                 + "; observers " + ", ".join(f"{b} {n} card(s)" for b, n in s.get("cff_beobachter", {}).items()))
    elif s.get("feuermissionen") is not None:
        z.append(f"- Fire Missions Mtr FO: {s['feuermissionen']}")
    if s.get("evakuiert"):
        z.append(f"- Evacuated casualties: {s['evakuiert']}")
    if s.get("pakete"):
        z.append("- Enemy packages: " + "; ".join(f"{p} {'free' if paket_verfuegbar(s, p) else 'in use'}" for p in s["pakete"]))
    if s.get("removed_from_play"):
        z.append("- Removed from Play: " + ", ".join(s["removed_from_play"]))
    if s.get("gefangene"):
        z.append(f"- Prisoners: {s['gefangene']}")
    if kompanie(s) and funk_aktiv(s):
        z.append("")
        z.append("## Radio (CO TAC Net, BN TAC)")
        z.extend("- " + t for t in funk_uebersicht(s))
    if v4(s):
        z.append("")
        z.append("## Campaign")
        k = s["kampagne"]
        z.append(f"- Mission {k.get('mission_nr')}, attempt {k.get('versuch')} of {k.get('versuche_max')}; Experience {sum(x['punkte'] for x in s.get('xp', []))}; "
                 f"US casualty steps {s.get('us_casualties_gesamt', 0)}; enemy tactic {s.get('feind_taktik')}"
                 + (f" (counterattack until turn {s['gegenangriff']['bis_zug']})" if s.get("gegenangriff") else ""))
        z.append(f"- CO TAC: {s.get('co_tac_mittel') or 'choice open (CSR 1)'}; mortars: {s.get('moerser_wahl') or 'choice open (CSR 2)'}; runners in the box: {', '.join(s.get('runner_box', [])) or 'none'}"
                 + (f"; phone lines in the pool {s['leitungen_pool']}" if s.get("leitungen_pool") is not None else ""))
        if s.get("pyro_belegung"):
            z.append("- Pyro: " + ", ".join(f"{a}={b}" for a, b in s["pyro_belegung"].items()))
        if s.get("ziele", {}).get("phaselines"):
            z.append("- Phase Lines: " + ", ".join(f"PL{a} across row {b}" for a, b in s["ziele"]["phaselines"].items()))
        akt = []
        for key in ("ereignis_pflicht", "ereignis_flanke", "fm_gesperrt", "ereignis_munition", "bn_nicht_verfuegbar"):
            w = s.get(key)
            if w is not None and (w.get("zug") if isinstance(w, dict) else w) == s["zug"]:
                akt.append(key)
        if akt:
            z.append("- Event active: " + ", ".join(akt))
        if s.get("minen_checks"):
            z.append("- MINE CHECK OPEN: " + ", ".join(s["minen_checks"]))
        if s.get("reattempt_setup"):
            z.append("- REATTEMPT PREPARATION (3.9): reconstitute, setup, then reattempt done")
    if s.get("ziel_regeln"):
        z.append("")
        z.append("## Objective")
        z.append("- " + ziel_stand(s))
    z.append("")
    z.append("## Last entries")
    for p in s["protokoll"][-8:]:
        z.append(f"- {p['nr']} T{p['zug']} {p['phase']}: {p['text']}" + (f" [RULE {p['regel']}]" if p.get("regel") else ""))
    z.append("")
    z.append(stempel(s))
    txt = "\n".join(z) + "\n"
    (partie_dir() / "BRIEFING.md").write_text(txt, encoding="utf-8")
    return txt


def ausgabe(prot, s):
    for p in prot:
        print("Board: " + p)
    for h in dict.fromkeys(s.pop("_hinweise", [])):
        print("Note: " + h)
    print(stempel(s))


# ---------------------------------------------------------------- new / phase
def cmd_neu(args):
    if not args:
        sys.exit("fof.py new <setup.json> [game]")
    import os
    aufbau = json.loads(pathlib.Path(args[0]).read_text(encoding="utf-8"))
    name = args[1] if len(args) > 1 else "partie1"
    if os.environ.get("FOF_PARTIE"):
        name = os.environ["FOF_PARTIE"]          # test run: .aktuelle_partie stays unchanged
    else:
        (ROOT / ".aktuelle_partie").write_text(name)
    (ROOT / name).mkdir(exist_ok=True)
    for k in [k for k in aufbau if k.startswith("_")]:
        aufbau.pop(k)                             # comment fields of the setup do not go into the game state
    s = copy.deepcopy(aufbau)
    for k, v in {"zug": 1, "phase": sop(s)[0][0], "aktiver_hq": None, "impuls_aktionen": {}, "impuls_ausgegeben": {},
                 "protokoll": [], "kommandos": {}, "removed_from_play": [], "kampf_offen": []}.items():
        s.setdefault(k, v)
    for n, e in s["einheiten"].items():
        e.setdefault("status", [])
        e.setdefault("seite", "US")
        e.setdefault("bereich", "offen")
        e.setdefault("ziel", None)
        if ist_hq(e):
            s["kommandos"].setdefault(n, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    for k in s["karten"].values():
        k.setdefault("cover", [])
        k.setdefault("extern", [])
    if s.get("fm_werte"):
        s.setdefault("target_marker", {})
    if v4(s):
        # v4: record initial state for Reattempt (3.9), Experience (12.1) and Replacements (12.4)
        s["aufbau_einheiten"] = copy.deepcopy({**s["einheiten"], **s.get("reserve_einheiten", {})})
        s["pc_start"] = {k: c.get("pc") for k, c in s["karten"].items() if c.get("pc")}
        s["fm_start"] = copy.deepcopy(s.get("feuermissionen"))
        s["assets_start"] = copy.deepcopy(s.get("assets_pool", {}))
        s.setdefault("xp", [])
        s.setdefault("us_casualties_gesamt", 0)
    unbekannt = [k for k in s.get("optionen", {}) if k not in OPTIONEN_STANDARD]
    if unbekannt:
        sys.exit("Unknown options in setup: " + ", ".join(unbekannt))
    speichern(s, f"Game {name} created: {s['mission']}", None)
    print(briefing(s))
    if "optionen" in s:
        print("Open rules questions with chosen reading: fof.py options")


def segment_hinweis(s, pid):
    """Who acts in initiative segment 3.3.2a-c (or: skipped) [RULE 3.3.2 p.16]."""
    if not kompanie(s):
        return ""
    k = s["kommandos"]
    if pid == "3.3.2a":
        co = s["co_hq"]
        if co not in s["einheiten"]:
            return "skipped: CO HQ not on the board [RULE 3.3.2a p.16]"
        if k.get(co, {}).get("aktiviert"):
            return "skipped: CO HQ was activated in 3.3.1, no Initiative draw [RULE 3.3.2a p.16]"
        return f"{co} draws Initiative (modified) plus saved {k.get(co, {}).get('gespart', 0)} [RULE 3.3.2a p.16]"
    if pid == "3.3.2b":
        n = [h for h, c in k.items() if h in s["einheiten"] and s["einheiten"][h].get("ebene") == "PLT" and not c["aktiviert"] and not c.get("fertig")]
        return ("draw Initiative: " + ", ".join(n) + " [RULE 3.3.2b p.16]") if n else "skipped: no non-activated PLT HQ on the board [RULE 3.3.2b p.16]"
    if pid == "3.3.2c":
        n = [f"{h} 1 + saved {c.get('gespart', 0)}" for h, c in k.items() if h in s["einheiten"] and s["einheiten"][h]["typ"] == "Staff" and not c["aktiviert"] and not c.get("fertig")]
        return ("1 Command each without draw: " + "; ".join(n) + " [RULE 3.3.2c p.16]") if n else "done or skipped: no open non-activated CO Staff [RULE 3.3.2c p.16]"
    return ""


def cmd_phase(s, args):
    ids = [p for p, _ in sop(s)]
    if not args:
        i = ids.index(s["phase"])
        print(f"Turn {s['zug']}  Phase {s['phase']} {phase_name(s)}")
        if i + 1 < len(ids):
            print(f"Next: {ids[i+1]} {phase_name(s, ids[i+1])}")
            h = segment_hinweis(s, ids[i + 1])
            if h:
                print(f"  {h}")
        h = segment_hinweis(s, s["phase"])
        if h:
            print(f"Now: {h}")
        return
    prot = []
    if args[0] == "weiter":
        i = ids.index(s["phase"])
        if s["phase"] in PLT_IMPULSE | {"3.3.2d", "3.3.1b", "3.3.2a", "3.3.2c", "3.3.1a"} and s.get("aktiver_hq"):
            raise Verstoss(f"{s['aktiver_hq']} has not yet ended the impulse with 'done'")
        if v4(s):
            minen_sperre(s)
            if s.get("reattempt_setup"):
                raise Verstoss("Reattempt preparation in progress: first fof.py reattempt done [3.9 p.18]")
            if s["phase"] == sop(s)[0][0] and s["zug"] == 1 and not s.get("aufstellung_fertig"):
                fa = aufstellung_pruefen_v4(s)
                if fa:
                    raise Verstoss("Still open before turn 1: " + "; ".join(fa))
                if s.get("patrouille_mission"):
                    patrouille_reserve(s, prot)
            if s.get("ereignistabellen") and s["zug"] >= 2 and s["phase"] in ("3.1", "3.4.1", "3.2.1") and s.get("ereignis_erledigt") != [s["zug"], s["phase"]]:
                raise Verstoss(f"First the Higher HQ Event of this segment: draw an Action card, fof.py event <cardno> yes <R#> | no [RULE {'3.1 S.15' if s['phase'] == '3.1' else '3.4.1 S.16'}]")
            if s["phase"] == "3.1" and s.get("ereignis_munition") == s["zug"]:
                raise Verstoss("Ammo Resupply not yet placed: fof.py ammo depot <card> <type> 4 [Normandy M1 p.18]")
            if s["phase"] == "3.4.1" and s.get("rally_offen"):
                raise Verstoss("Rally event open for: " + ", ".join(s["rally_offen"]) + " (enemyaction <n> Rally --success=yes|no)")
            if s["phase"] == "3.7.4" and (s.get("sniper_offen") or s.get("leitung_checks")):
                raise Verstoss("Open: " + ", ".join([f"Sniper target {n}" for n in s.get("sniper_offen", {})] + [f"phone line {k}" for k in s.get("leitung_checks", {})]))
        if s["phase"] == "3.3.1c":
            offen = [n for n, k in s["kommandos"].items() if k["aktiviert"] and not k["fertig"] and s["einheiten"].get(n, {}).get("ebene") != "CO"]
            if offen:
                raise Verstoss(f"Activated HQs without impulse: {', '.join(offen)} [RULE 3.3.1c p.15]")
        if kompanie(s):
            co, kc = s["co_hq"], s["kommandos"].get(s["co_hq"], {})
            if s["phase"] == "3.3.1b" and kc.get("aktiviert") and not kc.get("fertig"):
                raise Verstoss(f"{co} is activated and must draw an Action card in the CO HQ Impulse (hq, card, done) [RULE 3.3.1b p.15]")
            if s["phase"] == "3.3.2a" and co in s["einheiten"] and not kc.get("aktiviert") and not kc.get("fertig"):
                raise Verstoss(f"{co} was not activated and now draws Initiative Commands (hq, card <no> <star number>, done) [RULE 3.3.2a p.16]")
            if s["phase"] == "3.3.2b":
                offen = [n for n, k in s["kommandos"].items() if n in s["einheiten"] and s["einheiten"][n].get("ebene") == "PLT"
                         and not k["aktiviert"] and not k["fertig"]]
                if offen:
                    raise Verstoss(f"Non-activated PLT HQs draw Initiative: {', '.join(offen)} [RULE 3.3.2b p.16]")
        if s["phase"] == "3.7.2":
            offen = [k for k, c in s["karten"].items() if c.get("pc") and auf(s, k, "US")]
            if offen:
                raise Verstoss(f"PC markers with friendly units not yet resolved: {', '.join(offen)} [RULE 3.7.2 p.17]")
        if s["phase"] == "3.4.2" and any(e["seite"] == "Feind" and e.get("check_offen") for e in s["einheiten"].values()):
            raise Verstoss("Enemy Activity Check not yet completed for all enemies (enemycheck / enemyaction) [RULE 3.4.2 p.16]")
        if s["phase"] == "3.7.4" and s.get("kampf_offen"):
            raise Verstoss("Combat Effects still open for: " + ", ".join(s["kampf_offen"]) + " (ncm / hit) [RULE 3.7.4 p.17]")
        off = [n for n, e in s["einheiten"].items() if e.get("ziel_offen")]
        if off:
            raise Verstoss("Set open fire targets first with 'fire': " + ", ".join(off))
        if i + 1 >= len(ids):
            raise Verstoss("Last phase reached; use 'endturn' [RULE 3.8 p.17]")
        neu = ids[i + 1]
        if neu in AB_ZUG_2 and s["zug"] == 1:
            prot.append(f"{neu} does not apply in turn 1, skipped")
            neu = ids[i + 2]
        elif neu in AB_ZUG_2 and s.get("keine_ereignisse"):
            prot.append(f"{neu} does not apply, no events in this mission (FM1 p.38/p.40), skipped")
            neu = ids[i + 2]
        if s["phase"] == "3.1" and s["zug"] == 1:
            s["aufstellung_fertig"] = True
    else:
        if args[0] not in ids:
            raise Verstoss(f"Phase {args[0]} not in the sequence of play: {', '.join(ids)}")
        neu = args[0]
        if ids.index(neu) < ids.index(s["phase"]):
            prot.append("WARNING: jumping back in the sequence of play, for corrections only")
    s["_phase_alt"] = s["phase"]
    s["phase"] = neu
    if segment_hinweis(s, neu):
        prot.append(segment_hinweis(s, neu))
    s["aktiver_hq"] = None
    s["impuls_aktionen"] = {}
    if neu == "3.3.1a" and bn_leader(s):
        # [RULE 4.1.1 p.18/19] BN HQ 'on the map': highest-ranking Higher HQ leader receives 6 (night 4) Commands, cannot be saved
        bn = sorted(bn_leader(s), key=lambda x: 0 if x.startswith("Rgt") else 1)[0]
        s["kommandos"][bn].update(verfuegbar=MAX_IMPULS[s["sicht"]], aktiviert=True, fertig=False)
        s["aktiver_hq"] = bn
        prot.append(f"BN HQ is on the board: {bn} receives {MAX_IMPULS[s['sicht']]} Commands (cannot be saved); activate {s['co_hq']} only with communication (activate \"{s['co_hq']}\"), then done [4.1.1 p.18/19]")
    elif neu == "3.3.1a" and kompanie(s) and s.get("bn_hq") == "off-map" and s.get("bn_nicht_verfuegbar") == s["zug"]:
        prot.append(f"Comm Trouble: BN HQ does not activate {s['co_hq']} this turn; {s['co_hq']} draws Initiative in 3.3.2a [Normandy M1 p.18, 4.1.1 p.19]")
    elif neu == "3.3.1a" and kompanie(s) and s.get("bn_hq") == "off-map":
        co = s["co_hq"]
        kc = s["kommandos"].get(co, {"aktiviert": False})
        ok, grund = bn_verbindung(s)
        if co not in s["einheiten"]:
            prot.append(f"{co} not in play: BN HQ activates no one; 3.3.2a is skipped; reconstitution of a CO HQ per 6.5.2 p.49/50 [3.3.1a p.15]")
        elif kc["aktiviert"]:
            pass
        elif ft_seite(einheit(s, co)):
            prot.append(f"{co} is on its Fire Team side and cannot be activated; it draws Initiative in 3.3.2a [4.1.4 p.20]")
        elif ok:
            kc["aktiviert"] = True
            prot.append(f"BN HQ (off-map) activates {co} ({grund}); flip Command marker {co} to Commands Available [3.3.1a p.15, 4.1.1 p.18]")
        else:
            prot.append(f"BN HQ not available: {grund}; {co} is not activated and draws Initiative in 3.3.2a [4.1.1 p.19]")
    if v4(s) and s.get("_phase_alt") == "3.3.2d":
        ereignis_flanke_pruefen(s, prot)
    if neu == "3.3.1b" and any(e["typ"] == "Runner" for e in s["einheiten"].values()):
        runner_zustellen(s, prot)
    if neu == "3.4.2":
        feind_cease_fire(s, prot)
        feindcheck_vorbereiten(s, prot)
        if s.get("ereignis_erledigt") == [s["zug"], "3.4.1"]:
            for n in s.get("ereignis_einheiten", []):
                if n in s["einheiten"]:
                    s["einheiten"][n]["check_offen"] = False                     # [RULE 3.4.1 p.16] no further check
    if neu == "3.5.1":
        capture_pruefen(s, prot)
    if neu == "3.5.2":
        retreat_pruefen(s, prot)
    if neu == "3.7.1":
        for kid, c in s["karten"].items():
            for x in list(c.get("extern", [])):
                if x["typ"] in ("Incoming", "AirStrike"):
                    c["extern"].remove(x)
                    prot.append(f"{kid}: remove {VOF_NAME[x['typ']]} marker [3.7.1]")
                    for pk in s.get("pakete", {}).values():
                        if not pk.get("einheit") and pk.get("im_spiel") and pk["name"] == x.get("quelle"):
                            pk["im_spiel"] = False
                            prot.append(f"Package '{pk['name']}' available again [8.3]")
            for x in c.get("extern", []):
                if x["typ"] == "Pending":
                    x["typ"] = "Incoming"
                    prot.append(f"{kid}: flip Pending Fire Mission to its active side (Incoming {x['wert']}); units there lose LOS out of the card [3.7.1, 5.4]")
                    for n, e in s["einheiten"].items():
                        if e["karte"] == kid and feuert(e) and e["ziel"] != kid:
                            e["ziel"] = None
                            prot.append(f"{n} ceases fire (LOS blocked) [6.1.2]")
        feuer_eroeffnen(s, prot)
    if neu == "3.7.2":
        offen = [k for k, c in s["karten"].items() if c.get("pc") and auf(s, k, "US")]
        if any(c.get("pc") == "?" for c in s["karten"].values()):
            prot.append("Reveal PC markers with '?' on cards with friendly units before resolving [8.2.4, E39]")
        if offen:
            prot.append("PC markers to resolve (alphabetically, equal letters by R#): " + ", ".join(f"{k} (PC {s['karten'][k]['pc']})" for k in offen) + " [8.2.4]")
        else:
            prot.append("no PC markers with friendly units")
    if neu == "3.7.3":
        for n, e in s["einheiten"].items():
            if pinned(e) and vof_gegen(s, e["karte"], e["seite"]) is None:
                e["status"].remove("Pinned")
                prot.append(f"{n}: remove Pinned marker (no VOF on {e['karte']}); if the unit fires, its VOF becomes Basic again [3.7.3]")
    if neu == "3.7.4":
        if any(ist_sniper(e) for e in s["einheiten"].values()):
            sniper_ziele_waehlen(s, prot)
        s["kampf_offen"] = [n for n, e in s["einheiten"].items() if vof_gegen(s, e["karte"], e["seite"], ohne_minen=True) is not None or e.get("grenade")
                            or karte(s, e["karte"]).get("grenade_miss") or e.get("mine_hit")]
        prot.append("Combat Effects for: " + (", ".join(s["kampf_offen"]) if s["kampf_offen"] else "no one (no VOF)") + "; VOF, PDF and level stay frozen until 3.8 [3.7.4]")
        # [RULE 3.7.4 p.17] 'do not update PDF or VOF markers until the Clean Up Phase': record NCM rows on entry
        s["kampf_ncm"] = {}
        for n in s["kampf_offen"]:
            try:
                s["kampf_ncm"][n] = [list(z) for z in ncm_zeilen(s, n)]
            except Verstoss:
                pass
        muni_3_7_4(s, prot)                                                             # [RULE 7.18.4 p.61] ammo of the firing units
        if any(c.get("leitungen") for c in s["karten"].values()):
            leitung_checks_3_7_4(s, prot)
    s.pop("_phase_alt", None)
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, f"Phase {neu} {phase_name(s)}" + ("; " + "; ".join(prot) if prot else ""), None)
    print(f"Phase {neu} {phase_name(s)}")
    ausgabe(prot, s)


# ---------------------------------------------------------------- Enemy behaviour (8.6, 3.4.2)
def los_verlust_cease(s, prot):
    """[RULE 6.1.2, 9.1, 9.2.1] Target no longer in LOS/range (e.g. Illumination removed in Clean Up): cease fire."""
    for n, e in s["einheiten"].items():
        zk = e.get("ziel")
        if not zk or zk == e.get("karte") or zk not in s["karten"] or e.get("karte") not in s["karten"]:
            continue
        ok = los(s, e["karte"], zk)[0] and in_reichweite(s, e, zk)
        if not ok:
            e["ziel"] = None
            e.pop("konzentriert", None)
            prot.append(f"{n} ceases fire on {zk}: no LOS/range anymore (night 9.1 without Illumination) [6.1.2]")


def feind_cease_fire(s, prot):
    """8.6.4 / 3.4.2 / 3.8: enemies without a valid target cease fire and open fire anew per 6.1.1."""
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and feuert(e):
            zk = feuerziel_effektiv(s, n)
            if not gueltiges_ziel(s, zk, "Feind"):
                e["ziel"] = None
                e.pop("konzentriert", None)
                prot.append(f"{n}: Cease Fire, no valid target left on {zk} [8.6.4]")
    feuer_eroeffnen(s, prot, nur=[n for n, e in s["einheiten"].items() if e["seite"] == "Feind"])


OFFENSIV_TAKTIK = ("Offensive Assault", "Assault", "Overrun")


def feind_zeile(s, n):
    """v4 wrapper: Sniper/Spotter/Out-of-Ammo (8.8, 8.10, 8.11), With Leader column (8.9), Offensive hierarchy (counterattack), G! unit without PDF."""
    e = s["einheiten"][n]
    if v4(s) or s.get("feind_taktik") in OFFENSIV_TAKTIK:
        z4 = feind_zeile_v4(s, n)
        if z4:
            return z4
    zeile, spalte, erg = feind_zeile_basis(s, n)
    pid = zeile.split(" ")[0]
    if pid in LAT_MIT_LEADER and leader_da(s, e):
        spalte, erg = LAT_MIT_LEADER[pid]
        return zeile + " (With Leader, 8.9)", spalte, erg
    if not (pinned(e) or ist_lat(e) or ft_seite(e)):
        kid = e["karte"]
        gegner_da = bool(gueltiges_ziel(s, kid, "Feind"))
        cover = e.get("bereich", "offen") != "offen"
        if s.get("feind_taktik") in OFFENSIV_TAKTIK:
            z, sp, er = feind_zeile_offensiv(s, n, gegner_da, cover, feuert(e))
            return z + f" [Enemy Offensive Activity Check Hierarchy, {s['feind_taktik']}]", sp, er
        if v4(s) and e.get("vof_rating") == "G" and not feuert(e) and pid in ("Z4", "keine", "none") and feuerkandidaten_g(s, n):
            T = {"Delay": 0, "Hasty": 1, "Deliberate": 2}.get(s.get("feind_taktik", "Hasty"), 2)
            return "Z5 G! unit without PDF with target in LOS (player aid)", ["3", "2", "Auto"][T], [
                {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
                {"Auto": "Grenade Attack (or Concentrate Fire)"}][T]
    return zeile, spalte, erg


def feind_zeile_basis(s, n):
    """Hierarchy row of an enemy (Enemy Activity Check Hierarchy Chart; Defensive Delay/Hasty/Deliberate or LAT/Pinned without Leader)."""
    e = s["einheiten"][n]
    kid = e["karte"]
    gegner_da = bool(gueltiges_ziel(s, kid, "Feind"))
    cover = e.get("bereich", "offen") != "offen"
    # [PLAYER AID Key 'Under Fire'] without unactivated Mines and Pending (BGG E35); mine hit = active VOF
    unter_feuer = vof_gegen(s, kid, "Feind", ohne_minen=True) is not None or bool(e.get("mine_hit"))
    T = {"Delay": 0, "Hasty": 1, "Deliberate": 2}.get(s.get("feind_taktik", "Hasty"), 2)
    if pinned(e) or ist_lat(e) or ft_seite(e):
        if pinned(e):
            if gegner_da and not cover:
                return "P1 Pinned, opponent on card, without cover", "5", {"1": "No Action", "2": "Move into or Seek Cover", "3": "Rally", "4-5": "Fall Back"}
            if gegner_da:
                return "P2 Pinned, opponent on card, under cover", "5", {"1-2": "No Action", "3": "Rally", "4-5": "Fall Back"}
            if not cover:
                return "P3 Pinned, without cover", "5", {"1-2": "No Action", "3": "Move into or Seek Cover", "4": "Rally", "5": "Fall Back"}
            return "P4 Pinned, under cover", "4", {"1-2": "No Action", "3": "Rally", "4": "Fall Back"}
        if e["typ"] == "Assault Team":
            if gegner_da:
                return "P6 Assault Team on opponent's card", "2", {"1": "No Action", "2": "Grenade Attack"}
            return "P7 Assault Team not on opponent's card", "2", {"1": "No Action", "2": "Infiltrate to nearest opponent"}
        if e["typ"] == "Fire Team" and gegner_da:
            if not cover:
                return "P8 Fire Team without cover on opponent's card", "5", {"1": "No Action", "2": "Move into or Seek Cover", "3-5": "Fall Back"}
            return "P9 Fire Team under cover on opponent's card", "5", {"1-2": "No Action", "3": "Grenade Attack", "4-5": "Fall Back"}
        if ft_seite(e):
            if ist_hq(e):
                return "P10 Leader on Fire Team side", "3", {"1": "No Action", "2-3": "Rally"}
            return "P11 Spotter/Sniper/Weapon Team on Fire Team side", "2", {"1": "No Action", "2": "Rally"}
        if e["typ"] == "Litter Team":
            if karte(s, kid).get("casualties_feind"):
                return "P12 Litter Team with Casualty", "3", {"1": "No Action", "2-3": "Fall Back with Casualty"}
            if any(c.get("casualties_feind") and los(s, kid, k)[0] for k, c in s["karten"].items() if k != kid):
                return "P13 Litter Team with Casualty in LOS", "3", {"1": "No Action", "2-3": "Move towards closest Casualty"}
            return "P14 Litter Team without Casualty in LOS", "3", {"1-2": "No Action", "3": "Rally"}
        if e["typ"] == "Paralyzed Team":
            return "P15 Paralyzed Team", "Auto", {"Auto": "No Action"}
        return "none (no LAT row applies)", "Auto", {"Auto": "No Action"}
    hat_los = bool(feuerkandidaten(s, n))
    if kompanie(s) or "optionen" in s or s.get("sonderregeln"):
        # [PLAYER AID Enemy Activity Hierarchy] 'no LOS to an opposing unit' is pure LOS (5.2), independent of weapon range
        # and bunker fire arc [RULE 5.3.2 p.37 'Being in a Bunker ... does not affect a unit's LOS']
        hat_los = hat_los or any(los(s, kid, k)[0] for k in s["karten"] if k != kid and auf(s, k, "US"))
    if gegner_da and not cover:
        return "Z1 opponent on card, without cover", ["5", "4", "3"][T], [
            {"1": "No Action", "2": "Move into or Seek Cover", "3-4": "Fall Back", "5": "Grenade Attack"},
            {"1": "No Action", "2": "Move into or Seek Cover", "3": "Fall Back", "4": "Grenade Attack"},
            {"1": "Move into or Seek Cover", "2": "Fall Back", "3": "Grenade Attack"}][T]
    if gegner_da:
        return "Z2 opponent on card, under cover", ["4", "3", "3"][T], [
            {"1": "No Action", "2-3": "Fall Back", "4": "Grenade Attack"},
            {"1": "No Action", "2": "Fall Back", "3": "Grenade Attack"},
            {"1": "No Action", "2-3": "Grenade Attack"}][T]
    if e.get("out_of_ammo") and e.get("vof_rating") in ("A", "G", "H"):
        return "Z3 A/G!/H with Out of Ammo", ["Auto", "3", "2"][T], [{"Auto": "Fall Back"}, {"1": "No Action", "2-3": "Fall Back"}, {"1": "No Action", "2": "Fall Back"}][T]
    if not unter_feuer and not hat_los and not feuert(e):
        if s.get("sonderregeln", {}).get("remove_pc_no_action"):
            # [FM1 p.36] Deliberate Defense: 'ignore a "Remove unit, place PC marker" action result and do "No Action" instead'
            return "Z4 not under fire, no LOS to opponents (special rule FM1 p.36: No Action instead of Remove)", "Auto", {"Auto": "No Action"}
        if "optionen" in s and opt(s, "U1_remove_pc_no_action"):
            return "Z4 not under fire, no LOS to opponents (special rule FM1 p.36 also in Run 2/3: No Action)" + offen(s, "U1_remove_pc_no_action"), "Auto", {"Auto": "No Action"}
        return "Z4 not under fire, no LOS to opponents", "Auto", {"Auto": "Remove unit; place PC marker"}
    if not unter_feuer and feuert(e):
        return "Z5 not under fire, target along PDF", ["3", "2", "Auto"][T], [
            {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
            {"Auto": "Grenade Attack (or Concentrate Fire)"}][T]
    if unter_feuer and not cover:
        return "Z6 under fire, without cover", ["5", "5", "3"][T], [
            {"1": "No Action", "2": "Move into or Seek Cover", "3-4": "Fall Back", "5": "Grenade Attack (or Concentrate Fire)"},
            {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back", "5": "Grenade Attack (or Concentrate Fire)"},
            {"1-2": "Move into or Seek Cover", "3": "Grenade Attack (or Concentrate Fire)"}][T]
    if unter_feuer and feuert(e) and any(k != e["ziel"] for k in pdfs_nach(s, kid, "Feind")):
        return "Z7 under fire from a direction other than own PDF", ["5", "5", "4"][T], [
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3": "Shift PDF", "4-5": "Fall Back"},
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3-4": "Shift PDF", "5": "Fall Back"},
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3-4": "Shift PDF"}][T]
    a_wertung = ("A", "H", "A/S") if ("optionen" in s and opt(s, "U4_as_zaehlt_als_a")) else ("A", "H")
    if feuert(e) and e.get("vof_rating") in a_wertung and e["ziel"] != kid and not e.get("konzentriert"):
        return "Z8 A/H unit that has opened fire" + (offen(s, "U4_as_zaehlt_als_a") if e.get("vof_rating") == "A/S" else ""), ["3", "3", "Auto"][T], [
            {"1-2": "No Action", "3": "Attempt to Concentrate Fire"},
            {"1": "No Action", "2-3": "Attempt to Concentrate Fire"},
            {"Auto": "Attempt to Concentrate Fire"}][T]
    if unter_feuer and feuert(e):
        eigener = VOF_WERT.get(vof_rating_aktuell(e, e["ziel"] == kid), 0)
        if eigener < vof_gegen(s, kid, "Feind")[1]:
            return "Z9 Trading fire, own VOF better", ["3", "2", "3"][T], [
                {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
                {"1": "No Action", "2-3": "Grenade Attack (or Concentrate Fire)"}][T]
        return "Z10 Trading fire, own VOF equal or worse", ["3", "5", "2"][T], [
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3": "Fall Back"},
            {"1-2": "No Action", "3-4": "Grenade Attack (or Concentrate Fire)", "5": "Fall Back"},
            {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"}][T]
    return "none (no row applies)", "Auto", {"Auto": "No Action"}


def feindcheck_vorbereiten(s, prot):
    if v4(s):
        for n, e in s["einheiten"].items():
            if e["seite"] == "Feind" and e.get("leader") and not ft_seite(e) and not [m for m in auf(s, e["karte"], "Feind") if m != n]:
                markieren(e, "Fire Team side")
                prot.append(f"{n}: Leader alone on {e['karte']}, flipped to Fire Team side [8.9 p.67]")
    feinde = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind"]
    for n in feinde:
        s["einheiten"][n]["check_offen"] = True
    # L60: units from an Enemy Higher HQ Event this turn do not check again [RULE 3.4.1 p.16]
    ohne = [n for n in s.get("ereignis_einheiten", []) if n in feinde] if s.get("ereignis_erledigt") == [s["zug"], "3.4.1"] else []
    if ohne:
        prot.append(f"no Activity Check for {', '.join(ohne)} (already affected by the Enemy Higher HQ Event) [3.4.1 p.16]")
        feinde = [n for n in feinde if n not in ohne]
        if not feinde:
            prot.append("no further enemies to check")
            return
    karten = sorted({s["einheiten"][n]["karte"] for n in feinde})
    if not feinde:
        prot.append("no enemies on the board, Activity Check skipped")
    elif len(karten) > 1:
        prot.append(f"card order by R# (column {len(karten)}) for {', '.join(karten)}; per card first Pinned/LAT, then Good Order, then Leader; then fof.py enemycheck [8.6.2]")
    else:
        prot.append(f"Activity Check for {', '.join(feinde)}: fof.py enemycheck [8.6.2]")


def cmd_feindcheck(s, args):
    if s["phase"] != "3.4.2":
        print(f"Note: Activity Check belongs in 3.4.2, currently {s['phase']}")
    for n, e in s["einheiten"].items():
        if e["seite"] != "Feind":
            continue
        zeile, spalte, erg = feind_zeile(s, n)
        print(f"{n} on {e['karte']}" + ("" if e.get("check_offen") else " (check done)") + f": {zeile} [Enemy Activity Chart, {s.get('feind_taktik', 'Hasty')}]")
        if spalte == "Auto":
            print(f"  Auto: {list(erg.values())[0]}   fof.py enemyaction \"{n}\" \"{list(erg.values())[0]}\" ...")
        else:
            print(f"  R# column {spalte}: " + "; ".join(f"{k} = {v}" for k, v in erg.items()))
            print(f"  then fof.py enemyaction \"{n}\" \"<action>\" [--target=K] [--success=yes|no] [--unit=<target unit>]")



def cf_stapel(s, ze):
    """[RULE 7.11.2 p.56] Target under a cover marker: CF affects all units under that marker."""
    z = s["einheiten"][ze]
    b = z.get("bereich", "offen")
    if b in (None, "offen"):
        return [ze]
    return [n for n, e in s["einheiten"].items() if e.get("karte") == z.get("karte") and e.get("seite") == z.get("seite") and e.get("bereich") == b]

def cmd_feindaktion(s, args):
    n = args[0]
    e = einheit(s, n)
    if e["seite"] != "Feind":
        raise Verstoss(f"{n} is not an enemy")
    aktion = args[1]
    ereignis_rally = s["phase"] == "3.4.1" and n in s.get("rally_offen", []) and aktion.lower().startswith("rally")
    if s["phase"] != "3.4.2" and not ereignis_rally:
        raise Verstoss(f"Enemy actions only in the Enemy Activity Check segment 3.4.2, currently {s['phase']}")
    o = opts_parse(args[2:])
    prot = []
    a = aktion.lower()
    if ereignis_rally:
        s["rally_offen"].remove(n)
    if e.get("unbeweglich") and any(w in a for w in ("fall back", "move", "infiltrate", "advance")):
        raise Verstoss(f"{n} is an immobile AT gun: draw the result again [RULE 8.12 p.68]")
    von_karte = e["karte"]
    unter_vof = vof_gegen(s, e["karte"], "Feind") is not None
    if a.startswith("no action"):
        prot.append(f"{n}: No Action, fire continues [Chart]")
    elif a.startswith("call for fire"):
        # [RULE 8.10 p.68] Spotter: Call for Fire by priority; number of cards per mission (experience included), +1 Target marker
        if not e.get("spotter") or e.get("missionen", 0) <= 0:
            raise Verstoss(f"{n} is not a Spotter with fire missions")
        ziel = o.get("--ziel")
        if not ziel:
            raise Verstoss("--target=<card by priority (enemycheck)>")
        tk = s.get("feind_target", {}).get(e.get("typname"))
        if o.get("--erfolg") not in ("ja", "nein"):
            raise Verstoss(f"Call for Fire: {e.get('karten_folge', 3) + (1 if tk == ziel else 0)} cards, Burst symbol; --success=yes|no [8.10 p.68]")
        if o["--erfolg"] == "ja":
            karte(s, ziel).setdefault("extern", []).append({"typ": "Pending", "wert": e.get("fm_wert", -3), "quelle": n, "seite": "Feind"})
            e["missionen"] -= 1
            s.setdefault("feind_target", {})[e.get("typname")] = ziel
            prot.append(f"{n}: Pending Fire Mission ({e.get('fm_wert', -3):+d}) on {ziel}, enemy Target marker moved there; becomes active in 3.7.1; {e['missionen']} mission(s) left [8.10 p.68, 3.7.1]")
        else:
            prot.append(f"{n}: Call for Fire failed, no mission used up (BGG E19)")
    elif "keine feuerauftraege" in a or "no fire missions" in a:
        feind_entfernen(s, n, prot, grund="Spotter without fire missions [8.10 p.68]")
    elif "advance" in a:
        # [PLAYER AID Offensive Hierarchy] one card towards Staging/MLR; row 1: Overrun off-map, Assault towards US units
        c = karte(s, e["karte"])
        ziel = karte_bei(s, c["reihe"] - 1, c["spalte"])
        if c["reihe"] == erste_kartenreihe(s):
            if s.get("feind_taktik") == "Overrun":
                feind_entfernen(s, n, prot, grund="Overrun: Advance from row 1 leaves the board")
                ziel = None
            else:
                ziel = o.get("--ziel")
                if not ziel or not benachbart(s, e["karte"], ziel) or (karte(s, ziel).get("staging") and not opt(s, "U24_assault_in_staging")):
                    raise Verstoss("Assault from row 1: --target=<adjacent card towards the nearest US unit>" + offen(s, "U24_assault_in_staging"))
        if ziel:
            granate_verfaellt(s, e, n, prot)
            e["karte"], e["bereich"] = ziel, "offen"
            markieren(e, "Exposed")
            prot.append(f"{n}: Advance Straight Ahead to {ziel}, Exposed [Offensive Hierarchy, 8.6.1C]")
            feuer_nach_bewegung(s, n, prot)
    elif "seek cover" in a or "move into" in a:
        kk = karte(s, e["karte"])
        frei = [c for c in kk.get("cover", []) if not any(s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == c["id"] for m in auf(s, e["karte"]))]
        if frei and e.get("bereich", "offen") == "offen":
            e["bereich"] = frei[0]["id"]
            markieren(e, "Exposed")
            prot.append(f"{n} moves under {frei[0]['id']} ({frei[0]['typ']}), Exposed [8.6.1C]")
        else:
            if o.get("--erfolg") not in ("ja", "nein"):
                n_k = (kk.get("cover_draw") or 2) + {"Green": -1, "Veteran": 1}.get(erfahrung(e), 0)
                raise Verstoss(f"Seek Cover: draw {n_k} cards (cover draw of the card, experience {erfahrung(e)}), word 'Cover'; --success=yes|no")
            if o["--erfolg"] == "ja":
                cid = neuer_cover(s, e["karte"], "Basic Cover", 1)
                e["bereich"] = cid
                markieren(e, "Exposed")
                prot.append(f"{n}: new cover marker {cid} (+1) on {e['karte']}, {n} under it, Exposed [4.2.2e]")
            else:
                prot.append(f"{n}: Seek Cover failed")
    elif "fall back" in a:
        ziel = o.get("--ziel")
        if ziel == "off-map":
            feind_entfernen(s, n, prot, grund="Fall Back off-map")
        else:
            if not ziel:
                raise Verstoss("Fall Back: --target=<card> (priority: off-map at own edge; card outside every US LOS; highest cover value; random on a tie) or --target=off-map [8.6.3]")
            karte(s, ziel)
            if not benachbart(s, e["karte"], ziel):
                raise Verstoss(f"{ziel} not adjacent to {e['karte']}")
            e["karte"], e["bereich"] = ziel, "offen"
            markieren(e, "Exposed")
            frei = [c for c in karte(s, ziel).get("cover", []) if not any(s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == c["id"] for m in auf(s, ziel))]
            if frei:
                e["bereich"] = max(frei, key=lambda c: c["wert"])["id"]
                prot.append(f"{n} falls back to {ziel} under {e['bereich']}, Exposed [8.6.3, 8.6.1E]")
            else:
                prot.append(f"{n} falls back to {ziel} (open), Exposed [8.6.3]")
            feuer_nach_bewegung(s, n, prot)
    elif "grenade" in a or "concentrate" in a:
        if o.get("--erfolg") not in ("ja", "nein"):
            raise Verstoss("Grenade Attack (only Point Blank or G! rating) or Attempt to Concentrate Fire: 2 cards (enemy experience, +1 with Leader), Grenade symbol or Crosshairs; --success=yes|no --unit=<target unit or cover stack> [7.10, 7.11]")
        granate_pb = "grenade" in a and bool(gueltiges_ziel(s, e["karte"], "Feind"))
        g_ohne_pdf = v4(s) and e.get("vof_rating") == "G" and not feuert(e) and not granate_pb
        if not feuert(e) and not granate_pb and not g_ohne_pdf:
            raise Verstoss(f"{n} is not firing, no Concentrate Fire possible [4.2.4b]")
        if g_ohne_pdf:
            zk_g = o.get("--ziel")
            if zk_g not in feuerkandidaten_g(s, n):
                raise Verstoss(f"G! unit without PDF: --target=<card with target in LOS/range> from {', '.join(feuerkandidaten_g(s, n)) or 'none'}")
            e["ziel"], e["nur_pdf"] = zk_g, True
            prot.append(f"{n} places PDF towards {zk_g} [7.3.2 p.53]")
        zk = e["karte"] if granate_pb else feuerziel_effektiv(s, n)
        if v4(s) and "grenade" in a and not granate_pb and muni(e) and (e.get("vof_rating") == "G" or e.get("grenade_ranged")):
            muni_verbrauch(s, n, e, 1, "Grenade Attack at range", prot)
        if v4(s) and o.get("--jam") == "ja" and not granate_pb and jam_anfaellig(e):
            jam(s, n, prot)
            o["--erfolg"] = "nein"
        cv = cover_marker(s, e)
        if granate_pb and cv and cv["typ"] in STRUKTUR:
            # [RULE 5.3 p.37] Grenade Attack against a Point Blank opponent: unit leaves Bunker/Pillbox and becomes Exposed
            e["bereich"] = "offen"
            markieren(e, "Exposed")
            prot.append(f"{n} leaves {cv['typ']} {cv['id']} for the Point Blank attack, Exposed [5.3 p.37]")
        if o["--erfolg"] == "ja":
            ze = o.get("--einheit")
            if not ze:
                raise Verstoss(f"specify --unit=<target unit> (cover stack or random unit without cover on {zk})")
            z = einheit(s, ze)
            gw = int(o.get("--wert", s.get("granate_vof", -3)))                   # Normandy p.13: German Grenade Attacks are also -4
            if "grenade" in a and (zk == e["karte"] or e.get("vof_rating") == "G"):
                z.setdefault("grenade", []).append(gw)
                prot.append(f"{n}: Grenade VOF {gw} on {ze}; target may freely throw back [7.10]")
            else:
                for _m in cf_stapel(s, ze):
                    s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
                e["konzentriert"] = True
                prot.append(f"{n}: Concentrated Fire marker on {ze} (stack: {', '.join(cf_stapel(s, ze))}; -1 NCM, cumulative) [7.11]")
                if muni(e):
                    muni_verbrauch(s, n, e, 1, "successful Concentrate Fire", prot)
        else:
            if "grenade" in a and zk == e["karte"]:
                karte(s, zk)["grenade_miss"] = True
                prot.append(f"{n}: Grenade Miss (-1) on {zk}; target may freely throw back [7.10]")
            else:
                prot.append(f"{n}: attempt failed")
    elif "shift" in a:
        ziel = o.get("--ziel")
        if bogen_richtung(s, e) or e.get("bunker_richtung"):
            raise Verstoss(f"{n} is in a Bunker/Pillbox: draw the 'Shift Fire' result again [RULE 5.3.2 p.37]")
        if not ziel:
            raise Verstoss("Shift PDF: --target=<card the fire comes from> (random if several; Bunker: draw again)")
        karte(s, ziel)
        # L59: Chart 'Shift Fire if possible to place VOF on opposing units' - only with LOS, range and a valid target
        _los = los(s, e["karte"], ziel)
        if not _los[0] or not in_reichweite(s, e, ziel) or not gueltiges_ziel(s, ziel, e["seite"]):
            grund = _los[1] if not _los[0] else ("out of range" if not in_reichweite(s, e, ziel) else "no valid target")
            prot.append(f"{n}: Shift PDF to {ziel} not possible ({grund}); fire continues [Enemy Activity Chart: 'Shift Fire if possible', 9.2.1]")
        else:
            e["ziel"] = ziel
            e.pop("konzentriert", None)
            prot.append(f"{n} shifts its PDF to {ziel} [Chart, 6.3.3]")
    elif a.startswith("rally"):
        if pinned(e):
            if unter_vof and o.get("--erfolg") not in ("ja", "nein"):
                kz, ez = feind_rally_karten(e)
                raise Verstoss(f"Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]")
            if not unter_vof or o["--erfolg"] == "ja":
                e["status"].remove("Pinned")
                prot.append(f"{n}: Pinned marker removed, VOF Basic again [6.5.1]")
            else:
                prot.append(f"{n}: Rally failed")
        elif ft_seite(e):
            if unter_vof and o.get("--erfolg") not in ("ja", "nein"):
                raise Verstoss("Flip to Front under VOF: 2 cards, word 'Rally'; --success=yes|no [4.2.3f]")
            if not unter_vof or o["--erfolg"] == "ja":
                e["status"].remove("Fire Team side")
                prot.append(f"{n}: back to the front side [4.2.3f]")
            else:
                prot.append(f"{n}: Rally failed")
        elif ist_lat(e):
            naechst = {"Paralyzed Team": "Litter Team", "Litter Team": "Fire Team", "Fire Team": "Assault Team"}.get(e["typ"])
            if unter_vof and o.get("--erfolg") not in ("ja", "nein"):
                kz, ez = feind_rally_karten(e)
                raise Verstoss(f"LAT Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]")
            if naechst and (not unter_vof or o["--erfolg"] == "ja"):
                e["typ"] = naechst
                lat_werte_setzen(e, naechst)
                prot.append(f"{n} becomes {naechst} [6.5.1]")
            else:
                prot.append(f"{n}: Rally failed")
    elif "remove" in a:
        feind_entfernen(s, n, prot, grund="Z4: no LOS, no fire", pc=True)
    elif "move towards" in a:
        # [PLAYER AID LAT/Pinned Hierarchy] 'Move towards closest Casualty'; [RULE 8.6.1C p.66] moved enemies become Exposed
        ziel = o.get("--ziel")
        if not ziel or not benachbart(s, e["karte"], ziel):
            raise Verstoss("Move towards closest Casualty: --target=<adjacent card towards the closest Casualty> [LAT/Pinned Hierarchy]")
        granate_verfaellt(s, e, n, prot)
        e["karte"], e["bereich"] = ziel, "offen"
        markieren(e, "Exposed")
        prot.append(f"{n} to {ziel} (towards Casualty), Exposed [8.6.1C]")
        feuer_nach_bewegung(s, n, prot)
    elif "infiltrate" in a:
        ziel = o.get("--ziel")
        if not ziel or o.get("--erfolg") not in ("ja", "nein"):
            raise Verstoss("Infiltrate: --target=<card towards nearest opponent> --success=yes|no (2 cards, Infiltrate symbol); failure = normal move with Exposed [8.6, 5.1.4]")
        e["karte"], e["bereich"] = ziel, "offen"
        if o["--erfolg"] == "nein":
            markieren(e, "Exposed")
        prot.append(f"{n} to {ziel}" + (", not Exposed (infiltrated)" if o["--erfolg"] == "ja" else ", Exposed"))
        feuer_nach_bewegung(s, n, prot)
    else:
        raise Verstoss(f"Action '{aktion}' unknown")
    if n in s["einheiten"]:
        s["einheiten"][n]["check_offen"] = False
        e2 = s["einheiten"][n]
        if v4(s) and e2["karte"] != von_karte:
            minencheck_anfordern(s, [n], e2["karte"], prot, "enemy enters mine card")
            if ist_sniper(e2) and not any(los(s, e2["karte"], k)[0] for k in s["karten"] if auf(s, k, "US") and not karte(s, k).get("staging")):
                for m in auf(s, e2["karte"], "Feind"):
                    s["einheiten"][m]["spotted"] = False
                prot.append(f"{n} out of LOS of all US units: Unspotted again [8.8 p.67]")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, f"Activity Check {n}: {aktion}; " + "; ".join(prot), "8.6.2 p.66, Enemy Activity Chart")
    ausgabe(prot, s)


def feind_entfernen(s, n, prot, grund="", pc=False):
    e = s["einheiten"][n]
    kid = e["karte"]
    if pc and not karte(s, kid).get("pc"):
        karte(s, kid)["pc"] = e.get("pc_herkunft", "A")
        prot.append(f"Place PC marker {karte(s, kid)['pc']} on {kid} [8.6.1]")
    pk = s.get("pakete", {}).get(str(e.get("paket")))
    if pk:
        pk["im_spiel"] = False
    munition_verloren(e, n, prot)
    del s["einheiten"][n]
    prot.append(f"{n} off the board ({grund}), counter back to the pool [8.3]")


def munition_verloren(e, name, prot):
    """L62 (the player 09.10.2026): remove the ammo marker of a counter removed from the board; 5.1.6E only drops Assets and
    Casualties, enemy ammo is not captured (BGG 3498471)."""
    m = e.get("munition")
    if m and m.get("punkte"):
        prot.append(f"Remove ammo marker of {name} ({m['punkte']} {m.get('typ', '')}) from {e.get('karte')}: ammo lost, "
                    f"no capture [5.1.6E, BGG 3498471]")


def capture_pruefen(s, prot):
    """3.5.1 / 8.15: enemy Casualties automatically captured (8.15.1); Litter/Paralyzed alone with opponents: note."""
    for kid, c in s["karten"].items():
        if c.get("casualties_feind") and not auf(s, kid, "Feind") and (not c.get("pc") or auf(s, kid, "US")):
            s["gefangene"] = s.get("gefangene", 0) + c["casualties_feind"]
            prot.append(f"{kid}: {c['casualties_feind']} enemy Casualties captured, remove marker [8.15.1]")
            xp_buchen(s, c["casualties_feind"] * (xp_tab(s, "feind_casualty_step") or 1), f"{c['casualties_feind']} enemy Casualties captured ({kid})", prot)
            c["casualties_feind"] = 0
        for n in auf(s, kid):
            e = s["einheiten"][n]
            if e["typ"] in ("Paralyzed Team", "Litter Team") and not [m for m in auf(s, kid, e["seite"]) if m != n]:
                geg = [m for m in auf(s, kid, gegner(e["seite"])) if good_order(s["einheiten"][m]) or (s["einheiten"][m]["typ"] in ("Assault Team", "Fire Team") and not pinned(s["einheiten"][m]))]
                if geg and (e["seite"] == "Feind" or True):
                    if v4(s):
                        prot.append(f"{kid}: {n} ({e['typ']}, {e['seite']}) is captured (both sides take prisoners, Normandy p.13): fof.py capture \"{n}\" <guard> [3.5.1, 8.15]")
                    else:
                        prot.append(f"{kid}: {n} ({e['typ']}, {e['seite']}) is captured: one guard step with VOF value goes along (both Removed from Play); enemies take no prisoners, US team then becomes a Casualty. Afterwards fof.py enemy/order to correct [8.15]")


def retreat_pruefen(s, prot):
    """3.5.2: Paralyzed Teams (unpinned, not Exposed) and Litter Teams with a Casualty under VOF retreat one card."""
    weg = []
    for n, e in s["einheiten"].items():
        v = vof_gegen(s, e["karte"], e["seite"])
        if e["typ"] == "Paralyzed Team" and not pinned(e) and "Exposed" not in e["status"] and v:
            if e["seite"] == "Feind" and karte(s, e["karte"])["reihe"] >= oberste_reihe(s):
                # [RULE 3.5.2 p.16] "Enemy units who retreat from a card at their side's edge of the map will retreat off the map. Remove them from play. Do not extend the map."
                weg.append(n)
                prot.append(f"{n} (enemy) retreats off-map from the map edge: Removed from Play, counter back to the pool [3.5.2]")
                continue
            prot.append(f"{n} ({e['seite']}) must retreat one card (priority: no VOF, then best cover, random on a tie), Exposed [3.5.2]")
        if e["typ"] == "Litter Team" and not pinned(e) and v and karte(s, e["karte"]).get("casualties" if e["seite"] == "US" else "casualties_feind"):
            prot.append(f"{n} ({e['seite']}) retreats one card with a Casualty, Exposed [3.5.2]")
    for n in weg:
        s.setdefault("removed_from_play", []).append(n) if isinstance(s.get("removed_from_play"), list) else None
        s["einheiten"].pop(n, None)


# ---------------------------------------------------------------- Activation, impulses, Commands
def bezahlen(s, hq_name, kosten, regel):
    k = s["kommandos"][hq_name]
    gi = hq_name == "GI"
    gesamt = k["verfuegbar"] + (0 if gi else k["gespart"])
    if gesamt < kosten:
        raise Verstoss(f"{hq_name} has {gesamt} Commands, action costs {kosten} [RULE {regel}]")
    ausg = s.setdefault("impuls_ausgegeben", {}).get(hq_name, 0)
    if not gi and ausg + kosten > MAX_IMPULS[s["sicht"]]:
        raise Verstoss(f"At most {MAX_IMPULS[s['sicht']]} Commands per impulse [RULE 4.1.3 p.20]")
    rest = kosten
    if k["verfuegbar"] >= rest:
        k["verfuegbar"] -= rest
    else:
        rest -= k["verfuegbar"]
        k["verfuegbar"] = 0
        k["gespart"] -= rest
    s["impuls_ausgegeben"][hq_name] = ausg + kosten


def cmd_aktivieren(s, args):
    hq = args[0]
    e = einheit(s, hq)
    if not ist_hq(e):
        raise Verstoss(f"{hq} is not an HQ/Staff [RULE 4.2.1a p.22]")
    if s["phase"] == "3.3.1a" and bn_leader(s):
        bn = s.get("aktiver_hq")
        if e.get("ebene") != "CO" or not bn:
            raise Verstoss("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        kommunikation(s, bn, hq)
        bezahlen(s, bn, 1, "4.2.1a p.22")
        s["kommandos"][hq]["aktiviert"] = True
        speichern(s, f"{bn} (BN HQ on the board) activates {hq}", "4.1.1 p.18, 4.2.1a p.22")
        print(f"ALLOWED: {bn} activates {hq} (1 Command, remaining {s['kommandos'][bn]['verfuegbar']}); Command marker on Commands Available [4.1.1 p.18]")
        ausgabe([], s)
        return
    if s["phase"] == "3.3.1a":
        if e.get("ebene") != "CO":
            raise Verstoss("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        if kompanie(s) and s.get("bn_nicht_verfuegbar") == s["zug"]:
            raise Verstoss("Comm Trouble: BN HQ does not activate the CO HQ this turn [Normandy M1 p.18]")
        if kompanie(s):
            ok, grund = bn_verbindung(s)
            if not ok:
                raise Verstoss(f"BN HQ off-map cannot activate {hq}: {grund}; continue with 3.3.2a CO HQ Initiative [RULE 4.1.1 p.18/19, 4.0 p.18 footnote]")
    elif s["phase"] == "3.3.1b":
        if e.get("ebene") == "CO":
            raise Verstoss("The CO HQ is only activated by the BN HQ (3.3.1a) [RULE 4.2.1a p.22]")
    elif s["phase"] == "3.3.2a" and kompanie(s):
        if not opt(s, "U6_aktivieren_im_initiative_impuls"):
            raise Verstoss("No PLT HQs are activated in the CO HQ Initiative Impulse; non-activated PLT HQs draw Initiative in 3.3.2b [RULE 3.3.1c p.16, 3.3.2b p.16]" + offen(s, "U6_aktivieren_im_initiative_impuls"))
        co = s["co_hq"]
        if s.get("aktiver_hq") != co:
            raise Verstoss(f"First 'hq {co}' and card draw")
        kommunikation(s, co, hq)
        bezahlen(s, co, 1, "4.2.1a p.22")
        speichern(s, f"{co} activates {hq} in the Initiative Impulse (option U6 reading a): 1 Command, no effect, {hq} draws Initiative in 3.3.2b", "4.2.1a p.22")
        print(f"ALLOWED under option U6: 1 Command paid, no effect; {hq} draws Initiative in 3.3.2b" + offen(s, "U6_aktivieren_im_initiative_impuls"))
        ausgabe([], s)
        return
    else:
        raise Verstoss(f"Activation only in 3.3.1a/b, currently {s['phase']} [RULE 3.3.1 p.15]")
    if ft_seite(e):
        raise Verstoss(f"{hq} is on its Fire Team side, cannot be activated, must draw Initiative [RULE 4.1.4 p.20]")
    k = s["kommandos"][hq]
    if k["aktiviert"]:
        raise Verstoss(f"{hq} is already activated")
    co = s.get("co_hq")
    if co and co != "off-map" and s["phase"] == "3.3.1b":
        if s.get("aktiver_hq") != co:
            raise Verstoss(f"First 'hq {co}' and card draw, then activate")
        ce = einheit(s, co)
        if ft_seite(ce):
            raise Verstoss(f"{co} on its Fire Team side cannot activate [RULE 4.2.1a p.22]")
        if not s.get("co_immer_in_kommunikation"):
            kommunikation(s, co, hq)
        bezahlen(s, co, 1, "4.2.1a p.22")
    k["aktiviert"] = True
    wer = "BN HQ (off-map)" if s["phase"] == "3.3.1a" else (co or "CO HQ (off-map)")
    speichern(s, f"{wer} activates {hq}; Command marker on Commands Available", "4.2.1a p.22")
    print(f"ALLOWED: {hq} activated. Flip Command marker to Commands Available." + (f" Cost 1 Command {co}, remaining {s['kommandos'][co]['verfuegbar']}+{s['kommandos'][co]['gespart']}." if kompanie(s) and s["phase"] == "3.3.1b" else ""))
    ausgabe([], s)


def cmd_hq(s, args):
    hq = args[0]
    e = einheit(s, hq)
    k = s["kommandos"][hq]
    ph = s["phase"]
    if ph not in IMPULSE - {"3.3.1a", "3.3.2d"}:
        raise Verstoss(f"No HQ impulse in phase {ph}")
    if ph in ("3.3.1b", "3.3.2a") and e.get("ebene") != "CO":
        raise Verstoss(f"In {ph} only the CO HQ acts")
    if ph == "3.3.1b" and not k["aktiviert"]:
        raise Verstoss("CO HQ not activated; impulse only in 3.3.2a [RULE 3.3.1b p.15]")
    if ph == "3.3.2a" and k["aktiviert"]:
        raise Verstoss("CO HQ was activated and has already acted [RULE 3.3.2a p.16]")
    if ph == "3.3.1c" and not (e.get("ebene") == "PLT" or e["typ"] == "Staff"):
        raise Verstoss("In 3.3.1c PLT HQs and CO Staff act")
    if ph == "3.3.1c" and not k["aktiviert"]:
        raise Verstoss(f"{hq} was not activated; impulse only in 3.3.2b/c (Initiative) [RULE 3.3.1c p.15]")
    if ph == "3.3.2b" and (k["aktiviert"] or e.get("ebene") != "PLT"):
        raise Verstoss(f"{hq}: PLT HQ Initiative only for non-activated PLT HQs [RULE 3.3.2b p.16]")
    if ph == "3.3.2c":
        if e["typ"] != "Staff" or k["aktiviert"]:
            raise Verstoss("3.3.2c: only non-activated CO Staff, exactly 1 Command without card draw [RULE 3.3.2c p.16]")
        k["verfuegbar"] = 1
    if k["fertig"]:
        raise Verstoss(f"{hq} has already ended its impulse this turn")
    s["aktiver_hq"] = hq
    s["impuls_aktionen"] = {}
    speichern(s, f"Impulse {hq} begins", None)
    if ph in ("3.3.2a", "3.3.2b"):
        print(f"Active HQ: {hq} (Initiative). Now draw an Action card: fof.py card <no> <small number in the star>; modifiers 4.1.2, minimum 0 [RULE {ph} p.16, 4.1.1 p.19]")
    else:
        print(f"Active HQ: {hq}." + (" Now draw an Action card: fof.py card <no> <helmet number>" if ph != "3.3.2c" else " 1 Command (Staff Initiative)."))


def cmd_karte(s, args):
    hq = s.get("aktiver_hq")
    if not hq or hq == "GI":
        raise Verstoss("No active HQ (first 'hq <name>')")
    if s["phase"] not in IMPULSE - {"3.3.1a", "3.3.2c", "3.3.2d"}:
        raise Verstoss(f"Card draw for Commands only in HQ impulses, currently {s['phase']}")
    k = s["kommandos"][hq]
    if k.get("gezogen") == [s["zug"], s["phase"]]:
        raise Verstoss(f"{hq} has already drawn in this impulse [RULE 4.1 p.18]")
    nr, roh = args[0], int(args[1])
    e = einheit(s, hq)
    mods = []
    if "--roh" not in args:
        ez = erfahrung(e)
        if ez == "Green":
            mods.append(("Green", -1))
        if ez == "Veteran":
            mods.append(("Veteran", +1))
        if pinned(e):
            mods.append(("Pinned", -1))
        if e.get("bereich", "offen") != "offen":
            mods.append(("under cover", +1))
        v = vof_gegen(s, e["karte"], e["seite"], ohne_minen=True)
        vm = CMD_VOF_MOD.get(v[0], -3) if v else 0
        vn = f"VOF {VOF_NAME.get(v[0], v[0])}" if v else ""
        if e.get("mine_hit") and vm > -3:
            vm, vn = -3, "Mines!-VOF"
        if sniper_auf_karte(s, e["karte"]) and vm > -3:
            vm, vn = -3, "Sniper on the card (7.15)"                            # [RULE 4.1.2B p.20, 7.15 p.57]
        if vm:
            mods.append((vn, vm))
        if s.get("aktivitaet") == "No Contact":
            mods.append(("No Contact", +1))
    total = max(1 if k["aktiviert"] else 0, roh + sum(m for _, m in mods))
    k["verfuegbar"] = total
    k["gezogen"] = [s["zug"], s["phase"]]
    txt = f"{hq} draws Action card #{nr}: {roh}" + (" " + " ".join(f"{n} {m:+d}" for n, m in mods) if mods else "") + f" = {total} Commands (saved {k['gespart']})"
    evp = []
    if v4(s):
        ereignis_pflicht_zahlen(s, hq, evp)
    speichern(s, txt + ("; " + "; ".join(evp) if evp else ""), "4.1.2 p.20")
    print(txt)
    for x in evp:
        print("Board: " + x)
    bez = f", after event payment {k['verfuegbar']} new" if k["verfuegbar"] != total else ""   # [Normandy M1 p.18] L53
    print(f"Command marker on box {k['verfuegbar'] + k['gespart']} (drawn {total}{bez}, saved {k['gespart']}); spend at most {MAX_IMPULS[s['sicht']]} in this impulse [4.1.3].")
    print(stempel(s))


def cmd_gi(s, args):
    if s["phase"] != "3.3.2d":
        raise Verstoss(f"General Initiative only in 3.3.2d, currently {s['phase']} [RULE 3.3.2d p.16]")
    nr, klein = args[0], int(args[1])
    total = klein // 2 if s.get("einzelzug") else klein
    o = opts_parse(args[2:])
    gi_skill = ""
    if o.get("--skill-von"):
        h = o["--skill-von"]
        e = einheit(s, h)
        if "General Initiative" not in (e.get("skills") or []):
            raise Verstoss(f"{h} does not hold the General Initiative skill [RULE 12.7 p.82]")
        e["skills"].remove("General Initiative")
        total += 1
        gi_skill = f"; General Initiative skill of {h}: +1 GI Command, return skill marker (12.7: PLT HQ skill for units of this platoon) [Player Aid 2]"
    s["kommandos"].setdefault("GI", {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    s["kommandos"]["GI"]["verfuegbar"] = total
    s["aktiver_hq"] = "GI"
    s["impuls_aktionen"] = {}
    txt = f"General Initiative: Action card #{nr}, small number {klein}" + (f", halved (single-platoon mission) = {total}" if s.get("einzelzug") else f" = {total}") + " Commands, unmodified, cannot be saved" + gi_skill
    speichern(s, txt, "3.3.2d p.16, 4.1.1 p.19")
    print(txt)
    print("Orders: fof.py order GI <unit> <action> ... (without HQ and communication; mandatory HQ actions with --originator=<HQ>).")
    print(stempel(s))


def cmd_fertig(s, args):
    hq = s.get("aktiver_hq")
    if not hq:
        raise Verstoss("No active HQ")
    k = s["kommandos"][hq]
    if hq == "GI":
        rest = k["verfuegbar"]
        k["verfuegbar"] = 0
        s["aktiver_hq"] = None
        s["impuls_aktionen"] = {}
        speichern(s, "General Initiative ended" + (f", {rest} Commands lost" if rest else ""), "3.3.2d p.16")
        print("General Initiative ended" + (f", {rest} Commands lost (cannot be saved)" if rest else ""))
        print(stempel(s))
        return
    e = einheit(s, hq)
    lim = 0 if e.get("ebene") == "BN" else SPAR_LIMIT[erfahrung(e)][0 if s["sicht"] == "tag" else 1]
    neu = k["gespart"] + k["verfuegbar"]
    verloren = max(0, neu - lim)
    neu = min(neu, lim)
    k["gespart"], k["verfuegbar"], k["fertig"] = neu, 0, True
    s["aktiver_hq"] = None
    s["impuls_aktionen"] = {}
    s.get("impuls_ausgegeben", {}).pop(hq, None)
    txt = f"{hq} ends impulse; saved {neu}" + (f", {verloren} lost (limit {erfahrung(e)} {lim})" if verloren else "")
    speichern(s, txt, "4.1.3 p.20")
    print(txt)
    print(f"Board: flip Command marker {hq} to Activation Completed, Saved Commands zone box {neu}" + (" (Zero Commands Box)" if neu == 0 else ""))
    print(stempel(s))


# ---------------------------------------------------------------- Orders (4.2)
def neuer_cover(s, kid, typ, wert):
    c = karte(s, kid)
    i = len(c.setdefault("cover", [])) + 1
    cid = f"C{i}"
    while any(x["id"] == cid for x in c["cover"]):
        i += 1
        cid = f"C{i}"
    c["cover"].append({"id": cid, "typ": typ, "wert": wert, "feld": typ != "Basic Cover"})
    return cid


def markieren(e, m):
    if m not in e["status"]:
        e["status"].append(m)


def neuer_name(s, typ):
    i = 1
    while f"{typ} {i}" in s["einheiten"] or f"{typ} {i}" in s.get("removed_from_play", []):
        i += 1
    return f"{typ} {i}"


def bereich_setzen(s, z, name, b):
    if b == "offen":
        z["bereich"] = "offen"
        return
    if not [c for c in karte(s, z["karte"]).get("cover", []) if c["id"] == b]:
        raise Verstoss(f"Cover {b} does not exist on {z['karte']}")
    belegt = {s["einheiten"][m]["seite"] for m in auf(s, z["karte"]) if s["einheiten"][m].get("bereich") == b}
    if belegt and belegt != {z["seite"]}:
        raise Verstoss(f"Cover {b} is occupied by the opposing side [5.3]")
    cv = [c for c in karte(s, z["karte"])["cover"] if c["id"] == b][0]
    if cv.get("kapazitaet"):
        st = sum(steps(s["einheiten"][m]) for m in auf(s, z["karte"]) if s["einheiten"][m].get("bereich") == b and s["einheiten"][m] is not z)
        if st + steps(z) > cv["kapazitaet"]:
            raise Verstoss(f"{cv['typ']} {b} holds at most {cv['kapazitaet']} steps, occupied {st} [RULE 5.3.2 p.37]")
    z["bereich"] = b


def pruefe_bewegung(s, e, n, ziel_k, akt):
    if "Exposed" in e["status"]:
        raise Verstoss(f"{n} is Exposed and may no longer change cards [RULE 5.1.2 p.31]")
    if not benachbart(s, e["karte"], ziel_k):
        raise Verstoss(f"{ziel_k} is not adjacent to {e['karte']} (diagonal counts too) [RULE 5.1.2 p.31]")
    zk = karte(s, ziel_k)
    if zk.get("ausserhalb") and e["seite"] == "US":
        raise Verstoss(f"{ziel_k} lies outside the mission boundaries (map extension); friendly units may not go there [RULE 2.4.1 p.10, 8.4.5 p.65]")
    if e["seite"] == "US" and s.get("hold_up") == s["zug"] and not auf(s, ziel_k):
        raise Verstoss(f"Hold up!: no movement onto an unoccupied card this turn ({ziel_k}) [Normandy M3 p.26]")
    if e.get("mine_hit"):
        raise Verstoss(f"{n} is under the Mine marker and may not move to an adjacent card this turn [RULE 7.9.1 p.54]")
    if v4(s):
        bewegung_ereignis(s, e, ziel_k, [])
    if pinned(e) or e["typ"] in ("Fire Team", "Litter Team", "Paralyzed Team") or ft_seite(e):
        freund = [m for m in auf(s, ziel_k, e["seite"]) if m != n]
        ok = (zk.get("staging") and akt in ("4.2.2a", "4.2.2b")) or (freund and vof_gegen(s, ziel_k, e["seite"]) is None)
        if not ok:
            raise Verstoss(f"{n} (Pinned/LAT/Fire Team side) may only move to a Staging Area or to a card occupied by friendly units without VOF [RULE 4.2.5 p.26]")
    if e["typ"] == "Paralyzed Team" and akt != "4.2.2a":
        raise Verstoss("Paralyzed Team: only Move to an Adjacent Card [RULE 4.2.5 p.26]")
    if (pinned(e) or e["typ"] == "Paralyzed Team") and (geraete(e) or e.get("traegt_casualties")):
        raise Verstoss(f"{n} is Pinned/Paralyzed and carries Assets or Casualties; drop them first (fof.py drop, no Command) [RULE 4.2.5 p.27, 5.1.6E p.33]")
    if akt in ("4.2.2c", "4.2.2d"):
        if vof_gegen(s, e["karte"], e["seite"]) is None and vof_gegen(s, ziel_k, e["seite"]) is None and not karte(s, e["karte"]).get("grenade_miss") and not zk.get("grenade_miss"):
            raise Verstoss("Infiltration only if the origin or destination card has a VOF marker [RULE 5.1.4 p.32]")
        if e.get("tripod") or e.get("vof_rating") == "H" or moerser(e):
            raise Verstoss(f"{n} (tripod/H VOF) may not infiltrate [RULE 4.2.2c p.23]")
    ka = karte(s, e["karte"])
    if abs(ka["reihe"] - zk["reihe"]) == 1 and abs(ka["spalte"] - zk["spalte"]) == 1:      # 5.1.2 diagonal through PDF
        e1, e2 = karte_bei(s, ka["reihe"], zk["spalte"]), karte_bei(s, zk["reihe"], ka["spalte"])
        if e1 and e2:
            for m, f in s["einheiten"].items():
                if feuert(f) and f["ziel"] != f["karte"]:
                    strecke = [f["karte"]] + (linie(s, f["karte"], f["ziel"]) or []) + [f["ziel"]]
                    for i in range(len(strecke) - 1):
                        if {strecke[i], strecke[i + 1]} == {e1, e2}:
                            raise Verstoss(f"Diagonal {e['karte']} to {ziel_k} crosses the PDF {strecke[i]} to {strecke[i+1]} [RULE 5.1.2 p.32]")


def gegenwurf_hinweis(s, werfer, ziel, erfolg):
    """7.10.5 Free Grenade Attack Response: a Good Order unit on the same card always responds (thrower must be Spotted);
    an unpinned LAT with VOF only responds to a successful attack by a Spotted thrower."""
    gleiche_karte = werfer["karte"] == ziel["karte"]
    lat = ziel["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team")
    werfer_spotted = werfer["seite"] == "US" or werfer.get("spotted")
    if not lat and gleiche_karte and werfer_spotted:
        return f"{ziel.get('typname', 'Ziel')}: free response throw at {werfer['karte']} (Good Order, same card) [7.10.5]"
    if lat and not pinned(ziel) and ziel.get("vof_rating") and erfolg and werfer_spotted:
        return "Target (LAT with VOF, unpinned): free response throw [7.10.5]"
    return "No response throw: only Good Order units on the same card or unpinned LATs with VOF [7.10.5]"


def granate_verfaellt(s, e, name, prot):
    """7.10.4: if the target of a successful Grenade Attack moves before 3.7.4 (card change or within the card), it becomes a Grenade Miss on the original card."""
    if e.get("grenade"):
        karte(s, e["karte"])["grenade_miss"] = True
        e["grenade"] = []
        prot.append(f"Grenade marker on {name} becomes Grenade Miss (-1) on {e['karte']}: target moved before 3.7.4 [7.10.4]")


def bewegen(s, n, ziel_k, bereich, exposed, prot):
    e = s["einheiten"][n]
    von = e["karte"]
    granate_verfaellt(s, e, n, prot)
    if v4(s):
        leitung_legen(s, n, e, von, prot, s.get("_befehl_opts"))
        muni_ueberschuss(s, n, e, von, prot)
        bewegung_ereignis(s, e, ziel_k, prot)
    alt_cover = cover_von(s, e)
    e["karte"] = ziel_k
    e["bereich"] = "offen"
    if bereich and bereich != "offen":
        bereich_setzen(s, e, n, bereich)
    neu_cover = cover_von(s, e)
    zk = karte(s, ziel_k)
    if karte(s, von).get("staging") and zk.get("staging"):
        exposed = False                                                                     # 5.1.3
    if alt_cover and neu_cover and alt_cover["typ"] in ("Trench", "Bunker", "Pillbox") and neu_cover["typ"] in ("Trench", "Bunker", "Pillbox"):
        exposed = False                                                                     # 5.1.2
    if exposed:
        markieren(e, "Exposed")
    prot.append(f"{n} to {ziel_k}" + (f" under {bereich}" if bereich and bereich != "offen" else "") + (", Exposed" if "Exposed" in e["status"] else ", not Exposed"))
    patrouille_bewegung(s, n, von, ziel_k, prot)
    feuer_nach_bewegung(s, n, prot)
    if auf(s, ziel_k, gegner(e["seite"])):
        prot.append(f"Point Blank on {ziel_k}: each side's VOF only hits the opposing side [6.2.1b]")
    if v4(s):
        minencheck_anfordern(s, [n], ziel_k, prot, "unit enters mined card")


def cff_vorpruefung(s, z, name, orig_name, o):
    """7.16.1 p.58: valid target (Spotted), eligible observer with LOS, connection to the firing unit; number of cards per observer."""
    fm = s.get("feuermissionen", 0)
    if not isinstance(fm, dict) and fm != "unbegrenzt" and (fm or 0) <= 0:
        raise Verstoss("No Fire Mission available any more [7.16.1]")
    beob = s.get("cff_beobachter", {})
    if z["typ"] != "FO" and not z.get("beobachter") and name not in beob:
        raise Verstoss(f"{name} is not an observer according to the mission [7.16.1]" + (f"; eligible: {', '.join(beob)}" if beob else ""))
    if ft_seite(z):
        raise Verstoss("Observer on its Fire Team side cannot call for fire [7.16.1]")
    zt = o.get("--ziel")
    if not zt:
        raise Verstoss("Specify --target=<card with Spotted enemy> [7.16.1]")
    karte(s, zt)
    wp = "WP" in (o.get("--agentur") or "")
    illum = "Illum" in (o.get("--agentur") or "")
    if illum:
        if karte(s, zt).get("staging"):
            raise Verstoss("Illumination only on terrain cards [7.16.2E]")
    elif not wp and not [m for m in auf(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
        raise Verstoss(f"No Spotted enemy on {zt} [7.16.1]" + (" (WP missions may hit empty/Unspotted cards, 7.16.2C)" if isinstance(fm, dict) else ""))
    if not illum:
        ok, grund = los(s, z["karte"], zt)
        if not ok:
            raise Verstoss(f"Observer needs LOS to the target: {grund} [7.16.1]")
    agentur = None
    if s.get("fm_werte"):
        fw = s["fm_werte"]
        agentur = o.get("--agentur") or (list(fw)[0] if len(fw) == 1 else None)
        if agentur not in fw:
            raise Verstoss(f"Specify --agency={'|'.join(fw)} ({', '.join(f'{a} {w:+d}' for a, w in fw.items())}) [FM1 p.36, 7.16.1 p.58]")
        if isinstance(fm, dict) and fm.get(agentur, 0) <= 0:
            raise Verstoss(f"No {agentur} Fire Mission left ({fm}) [7.16.1, Normandy M1 p.17]")
        sp = s.get("fm_gesperrt") or {}
        if sp.get("zug") == s["zug"] and s.get("fm_gruppe", {}).get(agentur, agentur) == sp.get("gruppe"):
            raise Verstoss(f"Artillery Displacing: {sp['gruppe']} not available this turn [Normandy M1 p.18]")
        # Connection to the firing unit [RULE 7.16.1 p.58]
        if z["typ"] == "FO":
            fd = [g for g in geraete(z) if "FD" in g.get("netz", "")]
            if not fd and funk_aktiv(s) and not opt(s, "U2_fo_fd_funk"):
                raise Verstoss(f"{name} has no FD radio, no connection to the firing unit [RULE 7.16.1 p.58]" + offen(s, "U2_fo_fd_funk"))
            if not fd and funk_aktiv(s):
                s.setdefault("_hinweise", []).append(f"{name} calls over its FD net (device implicit under option U2){offen(s, 'U2_fo_fd_funk')}")
        elif z.get("ebene") == "CO" and funk_aktiv(s) and not s.get("co_immer_in_kommunikation"):
            if not geraete(z, "SCR300", "BN TAC"):
                raise Verstoss(f"{name} calls over the BN TAC Net and needs its SCR300 [RULE 7.16.1 p.58]")
    tab = s.get("cff_tabelle") or {}
    if agentur in tab:
        if name not in tab[agentur]:
            raise Verstoss(f"{name} may not call {agentur}; eligible: {', '.join(tab[agentur])} [Normandy M2 p.22]")
        basis = tab[agentur][name]                                          # [Normandy M2 p.22] number of cards per firing unit and observer
    else:
        basis = beob.get(name, s.get("cff_karten", 2))
    extra = 1 if agentur and s.get("target_marker", {}).get(tm_schluessel(s, agentur)) == zt else 0     # [RULE 7.16.5 p.59]
    return basis, extra, agentur


def tm_schluessel(s, agentur):
    """Target marker per firing unit; HE and WP of the same battery share it [open U29]."""
    if s.get("fm_gruppe") and opt(s, "U29_ein_target_marker_he_wp"):
        return s["fm_gruppe"].get(agentur, agentur)
    return agentur


def jam_anfaellig(e):
    """[RULE 7.12 p.56] A, G! and H weapons teams, AT guns, A squads with ammo tracking."""
    r = e.get("vof_rating")
    if e["typ"] in ("Weapons Team", "AT Gun") and r in ("A", "G", "H"):
        return True
    return e["typ"] == "Squad" and r == "A" and bool(e.get("munition"))


def jam(s, n, prot):
    """[RULE 7.12 p.56] Jam: unit immediately out of play, its steps become generic Fire Teams; success of the attempt is lost."""
    e = s["einheiten"][n]
    neue = []
    for _ in range(steps(e)):
        nn = neuer_name(s, "Fire Team")
        s["einheiten"][nn] = lat_neu(e, "Fire Team", n)
        s["einheiten"][nn]["status"] = []
        neue.append(nn)
    entfernen_rfp(s, n, prot, f"JAM: weapon out of action, steps become {', '.join(neue)}", nachfolger=neue[0] if neue else None)
    prot.append("Jam cancels any success of this attempt [7.12 p.56]")


def short_platz(s, z, zt, o):
    """[RULE 7.16.4 p.59] Short: one card closer to the observer along the LOS; observer on the target card: random adjacent card."""
    if z["karte"] == zt:
        pl = o.get("--platz")
        if not pl or not benachbart(s, zt, pl):
            nb = [k for k in s["karten"] if benachbart(s, zt, k)]
            raise Verstoss(f"Short, observer is on the target card: draw a random adjacent card (R#/{len(nb)} from {', '.join(nb)}) and --place=<card> [RULE 7.16.4 p.59]")
        return pl
    zw = linie(s, z["karte"], zt) or []
    return zw[-1] if zw else z["karte"]


def indirect_lay(s, hq_name, orig_name, orig, mname, m, o, prot, gi):
    """4.2.4j p.25, 7.3.2 p.53: HQ with LOS calls Indirect Lay of the multi-step mortar unit; VOF H without PDF, terrain like Incoming."""
    if not moerser(m):
        raise Verstoss(f"{mname} is not an on-map mortar unit [RULE 4.2.4j p.25]")
    if gi and orig_name == mname:
        raise Verstoss("Indirect Lay needs an HQ eligible to give orders as observer: --originator=<HQ> [RULE 7.3.2 p.53]" + offen(s, "U12_indirekt_unter_gi"))
    if gi and not opt(s, "U12_indirekt_unter_gi"):
        raise Verstoss("Indirect Lay under General Initiative not allowed under option U12 (reading a); order it in the impulse of an eligible HQ [RULE 7.3.2 p.53]" + offen(s, "U12_indirekt_unter_gi"))
    if not ist_hq(orig):
        raise Verstoss(f"Originator must be an HQ or Staff [RULE 4.2.4j p.25]")
    kommandokette(s, orig_name, mname)          # [RULE 7.3.2 p.53] 'someone who is eligible to issue orders to the mortar'
    if steps(m) < 2:
        raise Verstoss(f"{mname} has {steps(m)} step; Indirect Lay only with at least two steps [RULE 4.2.4j p.25, 7.3.2 p.53]")
    if not good_order(m) or "Exposed" in m["status"]:
        raise Verstoss(f"{mname} must be Good Order and not Exposed [RULE 4.2.4j p.25, 7.3.1 p.53]")
    if karte(s, m["karte"]).get("staging"):
        raise Verstoss("No firing from the Staging Area [RULE 2.5 p.12]")
    vb = feuerstellung_verboten(s, m)
    if vb:
        raise Verstoss(vb)
    # Connection: visual-verbal/radio or mortar in the same card area as an HQ with radio/phone (relay) [RULE 7.3.2 p.53]
    try:
        kommunikation(s, orig_name, mname, "4.2.4j")
    except Verstoss as v:
        relais = [n for n, e in s["einheiten"].items() if ist_hq(e) and e["karte"] == m["karte"] and e.get("bereich", "offen") == m.get("bereich", "offen") and geraete(e)]
        if not relais:
            raise Verstoss(f"No connection {orig_name} with {mname}: {v}; also no HQ with radio in the same card area as relay [RULE 7.3.2 p.53]")
        prot.append(f"Order via relay {relais[0]} (HQ with radio in the same area) [7.3.2 p.53]")
    zt = o.get("--ziel")
    if not zt:
        raise Verstoss("Specify --target=<card with Spotted enemy> [RULE 4.2.4j p.25]")
    karte(s, zt)
    if not [x for x in auf(s, zt, "Feind") if s["einheiten"][x].get("spotted")]:
        raise Verstoss(f"No Spotted enemy on {zt} [RULE 4.2.4j p.25]")
    ok, grund = los(s, orig["karte"], zt)
    if not ok:
        raise Verstoss(f"Observer {orig_name} has no LOS to {zt}: {grund} [RULE 7.3.2 p.53]")
    lo, hi = reichweite_grenzen(s, m)
    d = abstand(s, m["karte"], zt)
    if not (max(1, lo) <= d <= hi):
        raise Verstoss(f"{zt} is {d} cards away from {mname}; range in cards (diagonals counted, own card excluded) {max(1, lo)} to {hi} [RULE 7.3.2 p.53]" + offen(s, "U12_moerser_reichweite"))
    if m.get("ziel"):
        prot.append(f"{mname}: remove Direct Lay PDF and VOF to {m['ziel']}, Indirect Lay takes precedence [RULE 7.3.2 p.53]")
        m["ziel"] = None
    m["indirekt"] = True
    karte(s, zt).setdefault("extern", []).append({"typ": "Indirect", "wert": VOF_WERT["H"], "quelle": mname, "seite": "US"})
    prot.append(f"Heavy Weapons VOF (-3, Indirect Lay) on {zt}, no PDF, no Crossfire; hits all units on the card; lower C&C value and Burst apply; remove in Clean Up"
                + offen(s, "U12_moerser_reichweite") + " [RULE 7.3.2 p.53, 5.2.3 p.36]")


def aufnehmen(s, z, name, was, prot):
    """4.2.2h p.23 Pick up: pick up a Casualty or radio from the card (5.1.6B)."""
    c = karte(s, z["karte"])
    if was.lower() == "casualty":
        if not c.get("casualties"):
            raise Verstoss(f"There is no friendly Casualty on {z['karte']} [RULE 5.1.6 p.33]")
        c["casualties"] -= 1
        z["traegt_casualties"] = z.get("traegt_casualties", 0) + 1
        prot.append(f"{name} picks up a Casualty (marker under the counter or in the Assets box) [5.1.6B p.33, FM1 p.43]")
        return
    boden = c.get("assets_boden", [])
    if was in boden:                                                    # [RULE 5.1.6B p.33] pick up a dropped Asset (e.g. Rifle Grenade, smoke)
        boden.remove(was)
        z.setdefault("assets", []).append(was)
        prot.append(f"{name} picks up Asset {was} from the card [5.1.6B p.33]")
        return
    liegt = [g for g in c.get("assets", []) if g["typ"] == was or f"{g['typ']} {g['netz']}" == was]
    if not liegt:
        raise Verstoss(f"On {z['karte']} there is no device '{was}'" + (f"; on the ground: {', '.join(boden)}" if boden else ""))
    if liegt[0].get("schaden_offen"):
        raise Verstoss(f"First draw R# 1/2 for {liegt[0]['typ']}: fof.py radio damage {z['karte']} {liegt[0]['typ']} intact|destroyed [RULE 4.3.5 p.30]")
    c["assets"].remove(liegt[0])
    z.setdefault("funk", []).append({"typ": liegt[0]["typ"], "netz": liegt[0]["netz"]})
    prot.append(f"{name} picks up {liegt[0]['typ']} {liegt[0]['netz']} [4.3.5 p.30, 5.1.6B p.33]")


def hq_zurueck(s, hqname, z, prot):
    """[RULE 6.5.2 p.49] reconstituted HQ on the card of the receiving unit, always Green."""
    alt = s.get("rfp_daten", {}).get(hqname, {})
    e = {"typ": "HQ", "ebene": alt.get("ebene", "PLT"), "platoon": alt.get("platoon", z.get("platoon")), "seite": "US", "erfahrung": "Green",
         "karte": z["karte"], "bereich": z.get("bereich", "offen"), "status": [], "steps": 1, "fire_team_seite": True,
         "ft_vof": alt.get("ft_vof", "S"), "vof_rating": None, "reichweite": "L", "ziel": None, "funk": []}
    s["removed_from_play"].remove(hqname)
    s["einheiten"][hqname] = e
    s["kommandos"].setdefault(hqname, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    s["kommandos"][hqname].update(gespart=0, verfuegbar=0)
    prot.append(f"{hqname} reconstituted on {z['karte']}, Green (saves at most {SPAR_LIMIT['Green'][0]}) [RULE 6.5.2 p.49]")
    return e


def schritt_abgeben(s, n, prot, team):
    """Receiving unit loses a step; if only one step of the squad remains, it becomes a Fire/Assault Team [RULE 6.5.2 p.49]."""
    z = s["einheiten"][n]
    if steps(z) > 1:
        z["steps"] = steps(z) - 1
        prot.append(f"{n} down to {z['steps']} steps")
        if steps(z) == 1 and z.get("letzter_step"):
            lat = (team or "Fire") + " Team"
            neu = neuer_name(s, lat)
            s["einheiten"][neu] = lat_neu(z, lat, n)
            s["einheiten"][neu]["status"] = []
            entfernen_rfp(s, n, prot, f"last step becomes {lat} ({neu}) [6.5.2 p.49]", nachfolger=neu)
    else:
        entfernen_rfp(s, n, prot, "used for the reconstitution [6.5.2 p.49]")


def befehl_bn(s, ziel_name, akt, o):
    """[RULE 6.5.2 p.50] 'While off-map, the BN HQ can order the Reconstitution of the CO HQ from an eligible unit with a BN TAC
    radio/phone during the BN HQ Impulse.' Order: Any Platoon HQ, Arty FO, CO Staff."""
    if akt != "4.2.1e":
        raise Verstoss("The BN HQ (off-map) only gives 'Reconstitute the CO HQ' (4.2.1e) here [RULE 6.5.2 p.50]")
    if s["phase"] != "3.3.1a" or s.get("bn_hq") != "off-map":
        raise Verstoss("BN HQ off-map: reconstitution of the CO HQ only in the BN HQ Impulse 3.3.1a [RULE 6.5.2 p.50]")
    co = s.get("co_hq")
    if co in s["einheiten"] or co not in s.get("removed_from_play", []):
        raise Verstoss(f"{co} is not Removed from Play")
    z = einheit(s, ziel_name)
    plt = [n for n, e in s["einheiten"].items() if e.get("ebene") == "PLT" and e["typ"] == "HQ"]
    if z.get("ebene") != "PLT" and plt:
        raise Verstoss(f"A PLT HQ first ({', '.join(plt)}); on the Fire Team side rally first [RULE 6.5.2 p.49/50]")
    if z.get("ebene") != "PLT" and not (z["typ"] == "FO" and "Arty" in ziel_name) and z["typ"] != "Staff":
        raise Verstoss(f"{ziel_name} is not eligible (Any Platoon HQ, Arty FO, CO Staff) [RULE 6.5.2 p.49]")
    if ft_seite(z) or not good_order(z):
        raise Verstoss(f"{ziel_name} must be on its Good Order side (rally first) [RULE 6.5.2 p.50]")
    if funk_aktiv(s) and not geraete(z, "SCR300", "BN TAC"):
        raise Verstoss(f"{ziel_name} carries no BN TAC device; first pick up an SCR300 BN TAC (4.2.2h) [RULE 6.5.2 p.50, FM1 p.38] [open U8]")
    prot = []
    if not funk_aktiv(s):
        prot.append("Mission without radio: BN TAC connection assumed per mission [open U8]")
    funk = [dict(g) for g in geraete(z)]
    z["funk"] = []
    e = hq_zurueck(s, co, z, prot)
    e["ebene"] = "CO"
    e["funk"] = funk
    entfernen_rfp(s, ziel_name, prot, f"becomes {co} [6.5.2 p.49]")
    speichern(s, f"BN HQ orders Reconstitute the CO HQ: {ziel_name}; " + "; ".join(prot), "4.2.1e p.22, 6.5.2 p.50")
    print("ALLOWED [RULE 4.2.1e p.22, 6.5.2 p.50]")
    ausgabe(prot, s)


def granate_pruefen(s, z, ziel_name, o):
    """7.10.1: legality of a Grenade Attack (before the card draw and when booking). v4: Rifle Grenade (7.6), Mortar Team (7.3), ammo."""
    zt = o.get("--ziel", z["karte"])
    karte(s, zt)
    rg = v4(s) and "Rifle Grenade" in z.get("assets", []) and z.get("vof_rating") != "G" and not z.get("grenade_ranged")
    if zt != z["karte"] and z.get("vof_rating") != "G" and not z.get("grenade_ranged") and not rg:
        raise Verstoss("Grenade Attack without G! rating only Point Blank (own card) [RULE 7.10.1 p.54]")
    if zt != z["karte"]:
        if rg:
            hi = REICHWEITE.get(s.get("rifle_grenade_reichweite", "C"), 1)
            cv = cover_marker(s, z)
            if cv and cv["typ"] in STRUKTUR + ("Building", "Strong Building", "Light Building", "Cave"):
                raise Verstoss("Rifle Grenades not from Building/Bunker/Cave/Pillbox [RULE 7.6 p.54]")
            if abstand(s, z["karte"], zt) > hi or not los(s, z["karte"], zt)[0]:
                raise Verstoss(f"Rifle Grenade: target in LOS up to {s.get('rifle_grenade_reichweite', 'C')} (range per Asset counter UNVERIFIED) [RULE 7.10.1 p.55]")
        elif not in_reichweite(s, z, zt) or not los(s, z["karte"], zt)[0]:
            raise Verstoss("Ranged Grenade Attack: target must be in LOS and range [RULE 7.10.1 p.55]")
        if muni(z) and muni(z)["punkte"] <= 0 and not rg:
            raise Verstoss(f"{ziel_name} has no ammo left for ranged Grenade Attacks [RULE 7.18.2 p.61]")
        if moerser(z):
            vb = feuerstellung_verboten(s, z)
            if vb or "Exposed" in z["status"]:
                raise Verstoss(vb or "Mortar with Exposed marker does not fire [RULE 7.3.1 p.53]")
        pdf_ziele = {feuerziel_effektiv(s, m) for m in auf(s, z["karte"], z["seite"]) if feuert(s["einheiten"][m])}
        pdf_ziele.discard(z["karte"])
        if pdf_ziele and zt not in pdf_ziele:
            raise Verstoss(f"Ranged Grenade Attack must follow the card's PDF (PDF from {z['karte']} to {', '.join(sorted(pdf_ziele))}); Shift Fire first [RULE 7.10.1 p.55]")
        if auf(s, z["karte"], "Feind"):
            raise Verstoss("No Ranged Grenade Attack out of Point Blank combat [RULE 7.10.1 p.55]")
        if any(auf(s, zw, None if not moerser(z) else gegner(z["seite"])) for zw in (linie(s, z["karte"], zt) or [])):
            raise Verstoss("Ranged Grenade Attack not through other units (mortar: over friendly units, 7.3.1) [RULE 7.10.1 p.55]")
    if not [m for m in auf(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
        raise Verstoss(f"No Spotted enemy on {zt} [7.10]")
    return zt



# [RULE 12.7 p.82, Player Aid 2 Skills] Skills in use
SKILL_AUTO = {"Auto Spot": ("4.2.4a",), "Auto Cover": ("4.2.2e",), "Auto Concentrate Fire": ("4.2.4b",),
              "Auto Infiltrate": ("4.2.2c", "4.2.2g"), "Auto Grenade": ("4.2.4d",)}


def skill_halter(s, z_name, skill):
    """12.7: PLT HQ skill for every unit of the platoon; CO HQ and Staff skill only for the unit itself."""
    z = s["einheiten"][z_name]
    if skill in (z.get("skills") or []) and (z["typ"] in ("HQ", "Staff")):
        return z_name
    p = z.get("platoon")
    if p:
        for n, e in s["einheiten"].items():
            if e.get("seite") == "US" and e["typ"] == "HQ" and e.get("ebene") == "PLT" and str(e.get("platoon")) == str(p) and skill in (e.get("skills") or []):
                return n
    raise Verstoss(f"Skill {skill} is not available to {z_name}: PLT HQ skills only for units of this platoon, CO HQ/Staff skills only for the unit itself [RULE 12.7 p.82]")

def cmd_befehl(s, args):
    hq_name, ziel_name, akt = args[0], args[1], args[2]
    o = opts_parse(args[3:])
    if hq_name == "BN":
        return befehl_bn(s, ziel_name, akt, o)
    s["_befehl_opts"] = o
    if v4(s):
        minen_sperre(s)
        if akt in ("4.2.1g", "4.2.1h") and ziel_name in s.get("runner_box", []):
            return befehl_runner_box(s, hq_name, ziel_name, akt, o)
    if s["phase"] not in IMPULSE:
        raise Verstoss(f"Orders only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]")
    if s.get("aktiver_hq") != hq_name:
        raise Verstoss(f"Active HQ is {s.get('aktiver_hq')}, not {hq_name}")
    if akt not in AKTIONEN:
        raise Verstoss(f"Action {akt} not in the table. Known: {', '.join(AKTIONEN)}")
    if akt in ("4.2.2a", "4.2.2b", "4.2.2c", "4.2.2d") and o.get("--ziel") and o["--ziel"] in s["karten"] and not s["karten"][o["--ziel"]].get("staging"):
        _z = einheit(s, ziel_name)
        _mit = [_z] if akt in ("4.2.2a", "4.2.2c") else [e for e in s["einheiten"].values() if e["seite"] == "US" and e["karte"] == _z["karte"] and e.get("platoon") == _z.get("platoon") and "Exposed" not in e["status"] and e["typ"] not in ("Litter Team", "Paralyzed Team")]
        _st = sum(e["steps"] for e in s["einheiten"].values() if e["seite"] == "US" and e["karte"] == o["--ziel"] and e["typ"] != "Casualty") + sum(e["steps"] for e in _mit)
        if _st > 16:
            raise Verstoss(f"Stacking: {o['--ziel']} would have {_st} US steps, at most 16 per card [RULE 5.1.5 p.32]")
    name, kosten, zug, orig_art, regel = AKTIONEN[akt]
    gi = hq_name == "GI"
    z = einheit(s, ziel_name)
    if z["seite"] != "US":
        raise Verstoss("Orders only to friendly units")
    if gi:
        orig_name = o.get("--originator", ziel_name)
        if akt in HQ_PFLICHT_GI and orig_name == ziel_name and not ist_hq(z):
            raise Verstoss(f"{name} needs an HQ/Staff even under General Initiative: --originator=<HQ> [RULE 4.1.1 p.19, Clarification 3]")
        if orig_art in ("PLT", "CO_BN", "CO_ONLY") and orig_name == ziel_name:
            raise Verstoss(f"{name} needs the responsible HQ as originator (--originator=<HQ>) [RULE {regel}]")
        orig = einheit(s, orig_name)
        if orig_art == "CO_ONLY" and not (orig.get("ebene") == "CO" and orig["typ"] == "HQ"):
            raise Verstoss(f"{name}: originator only the CO HQ [RULE {regel}]")
    else:
        orig_name, orig = hq_name, einheit(s, hq_name)
        if orig_art == "PLT" and not (orig["typ"] == "HQ" and orig.get("ebene") == "PLT"):
            raise Verstoss(f"{name} may only be ordered by a PLT HQ [RULE {regel}]")
        if orig_art == "CO_BN" and orig.get("ebene") not in ("CO", "BN"):
            raise Verstoss(f"{name} may only be ordered by the CO HQ or BN HQ [RULE {regel}]")
        if orig_art == "CO_ONLY" and not (orig.get("ebene") == "CO" and orig["typ"] == "HQ"):
            raise Verstoss(f"{name}: originator only the CO HQ [RULE {regel}]")
        if ft_seite(orig) and ziel_name != hq_name:
            raise Verstoss(f"{hq_name} on its Fire Team side may only order itself [RULE 4.1.4 p.20]")
    if orig_art == "CO":
        # [RULE 4.2.1l p.22] Originator 'CO HQ or CO Staff (or PLT HQ in a single-platoon mission)', Recipient 'The HQ itself'
        if not (orig.get("ebene") == "CO" or orig["typ"] == "Staff" or (s.get("einzelzug") and orig.get("ebene") == "PLT")):
            raise Verstoss(f"{name}: only CO HQ or CO Staff (PLT HQ only in single-platoon missions) [RULE {regel}]")
        if ziel_name != orig_name:
            raise Verstoss(f"{name}: recipient is the HQ itself [RULE {regel}]")
    if orig_name != ziel_name:
        if akt not in ("4.2.4k", "4.2.4l", "4.2.4j"):
            kommandokette(s, orig_name, ziel_name)
        if akt != "4.2.4j":
            kommunikation(s, orig_name, ziel_name, akt)
    ex = s.get("exhort_frei")
    exhort_nach = bool(ex and ex[0] == ziel_name and ex[1] == akt and ex[2] == s["phase"] and o.get("--gratis") == "ja")
    if o.get("--gratis") == "ja" and not exhort_nach:
        raise Verstoss("--free=yes only for the effect of a successful Exhort (4.2.1b) with the same unit and action [RULE 4.2.1b p.22]")
    schon = s["impuls_aktionen"].setdefault(ziel_name, [])
    if akt in schon and akt != "4.2.2f" and not exhort_nach:
        raise Verstoss(f"{ziel_name} has already carried out '{name}' in this impulse; only Move within a Card may be repeated [RULE 4.2 p.21]")
    aktion_erlaubt(z, ziel_name, akt)
    k = s["kommandos"][hq_name]
    if k["verfuegbar"] + (0 if gi else k["gespart"]) < kosten and not exhort_nach:
        raise Verstoss(f"{hq_name} has {k['verfuegbar'] + (0 if gi else k['gespart'])} Commands, action costs {kosten} [RULE {regel}]")
    erfolg = o.get("--erfolg")
    skill = o.get("--skill")
    skill_text = None
    if skill:
        if skill not in SKILL_AUTO and skill != "Extra Draw":
            raise Verstoss(f"Skill in an order: {', '.join(list(SKILL_AUTO) + ['Extra Draw'])} [RULE 12.7 p.82]")
        if skill in SKILL_AUTO and akt not in SKILL_AUTO[skill]:
            raise Verstoss(f"{skill} only applies to {', '.join(SKILL_AUTO[skill])} [Player Aid 2, Skills]")
        halter = skill_halter(s, ziel_name, skill)
        if skill in SKILL_AUTO:
            erfolg = "ja"
            skill_text = (f"Skill {skill} of {halter}: attempt automatically successful; Commands are spent anyway"
                          + (", draw cards only for Critical Hit/Jam" if akt in ("4.2.4b", "4.2.4d") else ", no cards needed")
                          + " [RULE 12.7 p.82]")
        s["einheiten"][halter]["skills"].remove(skill)
        skill_text = (skill_text or f"Skill Extra Draw of {halter}: one extra card [Player Aid 2]") + f"; return skill marker"
    if exhort_nach and erfolg != "ja":
        raise Verstoss("After a successful Exhort enter the effect with --success=yes --free=yes")
    if o.get("--short") == "ja":
        erfolg = "ja"            # [RULE 7.16.4 p.59] 'Short' takes precedence; the Pending marker is placed anyway
    prot, bewegte = [], []
    if skill_text:
        prot.append(skill_text)
    zk = karte(s, z["karte"])
    mods = []
    basis_cff = None
    if akt == "4.2.4i":
        basis_cff, extra_cff, agentur = cff_vorpruefung(s, z, ziel_name, orig_name, o)
    if zug in ("attempt", "cover", "cff") or (zug == "attempt_vof" and vof_gegen(s, z["karte"], z["seite"]) is not None):
        extra = 0
        if akt == "4.2.4i":
            extra = extra_cff
            if extra:
                mods = [(f"Target marker {agentur} on {o['--ziel']}", extra)]
        if akt == "4.2.4a":
            zielk = o.get("--ziel")
            if not zielk:
                raise Verstoss("Spot: specify --target=<card with Unspotted enemies> [4.2.4a]")
            karte(s, zielk)
            if not [m for m in auf(s, zielk, "Feind") if not s["einheiten"][m].get("spotted")]:
                raise Verstoss(f"There is no Unspotted enemy on {zielk} [8.5]")
            if zk.get("staging"):
                raise Verstoss("No spotting from the Staging Area [8.5 Note]")
            ok, grund = los(s, z["karte"], zielk)
            if not ok:
                raise Verstoss(f"No LOS from {z['karte']} to {zielk}: {grund}")
            mods = spot_modifikatoren(s, z, zielk)
            extra = sum(m for _, m in mods)
        if akt == "4.2.4d":
            granate_pruefen(s, z, ziel_name, o)
        if skill == "Extra Draw":
            extra += 1
            mods = list(mods) + [("Skill Extra Draw", 1)]
        if akt not in ("4.2.2d",) and erfolg not in ("ja", "nein"):
            n_k, wer, basis = kartenzahl(s, akt, orig, z, extra, basis_cff)
            wort = {"4.2.2c": "Infiltrate symbol", "4.2.2g": "Infiltrate symbol", "4.2.2e": "word Cover", "4.2.4a": "Crosshairs",
                    "4.2.4b": "Crosshairs", "4.2.4d": "Grenade symbol", "4.2.4i": "Burst symbol (also 3 Bursts; 'Short!' takes precedence)"}.get(akt, "word Rally")
            msg = f"{name}: draw {n_k} Action cards (base {basis}" + ("" if akt == "4.2.4a" else f", experience {erfahrung(wer)} of the {'originator' if akt.startswith('4.2.3') else 'recipient'}")
            if mods:
                msg += ", " + ", ".join(f"{t} {m:+d}" for t, m in mods) + (", minimum 1" if akt == "4.2.4a" else "")
            msg += f"); success on {wort}. Then --success=yes|no" + (" (on 'Short' --short=yes)" if akt == "4.2.4i" and s.get("fm_werte") else "") + f" [RULE 4.2 p.21, {regel}]"
            raise Verstoss(msg)
    # ---------------- Movement
    if akt in ("4.2.2a", "4.2.2c"):
        ziel_k = o.get("--ziel")
        if not ziel_k:
            raise Verstoss("--target=<card> missing")
        karte(s, ziel_k)
        pruefe_bewegung(s, z, ziel_name, ziel_k, akt)
        bewegen(s, ziel_name, ziel_k, o.get("--bereich"), exposed=(akt == "4.2.2a" or erfolg == "nein"), prot=prot)
        bewegte = [ziel_name]
    elif akt in ("4.2.2b", "4.2.2d"):
        ziel_k = o.get("--ziel")
        if not ziel_k:
            raise Verstoss("--target=<card> missing")
        karte(s, ziel_k)
        erg = {}
        for t in (erfolg or "").split(","):
            if ":" in t:
                a, b = t.split(":")
                erg[a] = b
        kand = []
        for n, e in s["einheiten"].items():
            if e["seite"] != "US" or e["karte"] != orig["karte"]:
                continue
            try:
                kommandokette(s, orig_name, n)
                kommunikation(s, orig_name, n)
            except Verstoss:
                continue
            if not good_order(e) or "Exposed" in e["status"]:
                continue
            if akt == "4.2.2d" and (e.get("tripod") or e.get("vof_rating") == "H"):
                continue
            kand.append(n)
        if not kand:
            raise Verstoss("No Good Order unit of the platoon without Exposed in communication on the HQ's card [RULE 4.2.2b p.23]")
        if akt == "4.2.2d" and any(n not in erg for n in kand):
            raise Verstoss("Platoon Infiltrate: each unit draws itself (2 cards, own experience, Infiltrate symbol): --success=" + ",".join(f"{n}:yes|no" for n in kand) + " [RULE 4.2 Notes p.21]")
        for n in kand:
            pruefe_bewegung(s, s["einheiten"][n], n, ziel_k, akt)
        for n in kand:
            bewegen(s, n, ziel_k, o.get("--bereich"), exposed=(akt == "4.2.2b" or erg.get(n) == "nein"), prot=prot)
        bewegte = kand
    elif akt == "4.2.2e":
        if z.get("bereich", "offen") != "offen":
            raise Verstoss(f"{ziel_name} is already under cover [RULE 4.2.2e p.23]")
        vorhanden = len([c for c in zk.get("cover", []) if not c.get("feld")])
        if zk.get("cover_max") is not None and vorhanden >= zk["cover_max"]:
            raise Verstoss(f"{z['karte']} has reached its Cover Potential ({zk['cover_max']}) [RULE 5.3 p.36]")
        if erfolg == "ja":
            if zk.get("gebaeude_tabelle") and v4(s):
                # [CSR 8 p.15, 5.3.3 p.38] urban card: cover type by R# column 8
                if not o.get("--gebaeude"):
                    raise Verstoss("Seek Cover on Village/Farm/Cemetery/Church: R# column 8 on the building table, --building=<R#> [--building-value=<n>] [CSR 8 p.15]")
                gt, gw, oben = gebaeude_cover(s, z["karte"], z, o["--gebaeude"], o.get("--gebaeude_wert"))
                cid = neuer_cover(s, z["karte"], gt, gw)
                if gt != "Basic Cover":
                    [c_ for c_ in zk["cover"] if c_["id"] == cid][0]["feld"] = False
                if oben:
                    prot.append("additional Upper Story/Church Tower marker (does not count toward Cover Potential, Church Tower only 1 step) [5.3.3 p.38]")
            else:
                cid = neuer_cover(s, z["karte"], "Basic Cover", int(o.get("--wert", 1)))
            z["bereich"] = cid
            markieren(z, "Exposed")
            prot.append(f"new cover marker {cid} ({[c_ for c_ in zk['cover'] if c_['id'] == cid][0]['typ']}) on {z['karte']}, {ziel_name} beneath it, Exposed")
            if v4(s) and opt(s, "U20_mine_bei_seek_cover"):
                minencheck_anfordern(s, [ziel_name], z["karte"], prot, "movement under new cover" + offen(s, "U20_mine_bei_seek_cover"))
        else:
            prot.append(f"{ziel_name}: Seek Cover failed, nothing happens")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt in ("4.2.2f", "4.2.2g"):
        b = o.get("--bereich")
        if not b:
            raise Verstoss("Specify --area=<cover-id|open>")
        if akt == "4.2.2g" and vof_gegen(s, z["karte"], z["seite"]) is None:
            raise Verstoss("Infiltrate within a Card requires a VOF on the card [RULE 4.2.2g p.23]")
        if z.get("mine_hit"):
            raise Verstoss(f"{ziel_name} is under the Mine marker and may not move this turn [RULE 7.9.1 p.54]")
        alt_cv = cover_von(s, z)
        granate_verfaellt(s, z, ziel_name, prot)
        bereich_setzen(s, z, ziel_name, b)
        neu_cv = cover_von(s, z)
        fest = bool(alt_cv and neu_cv and alt_cv["typ"] in FESTE_DECKUNG and neu_cv["typ"] in FESTE_DECKUNG)
        if (akt == "4.2.2f" or erfolg == "nein") and not fest:
            markieren(z, "Exposed")
        if fest:
            prot.append("between Trench/Bunker/Pillbox markers of the same card without Exposed [RULE 5.1.1 p.31]")
        prot.append(f"{ziel_name} to {b} on {z['karte']}" + (", Exposed" if "Exposed" in z["status"] else ", not Exposed"))
        if moerser(z) and feuert(z) is False and z.get("ziel"):
            prot.append(f"{ziel_name} (mortar) is Exposed and does not fire, VOF is removed until Exposed is removed [RULE 7.3.1 p.53]")
        if v4(s):
            minencheck_anfordern(s, [ziel_name], z["karte"], prot, "movement within the mined card")
    elif akt == "4.2.2h":
        was = o.get("--was")
        if was and ":" in was and was.split(":")[0] in MUNITION_KAP:
            muni_aufnehmen(s, z, ziel_name, was, prot)
        elif was and was.startswith("Leitung"):
            nz = int(was.split(":")[1]) if ":" in was else 1
            if zk.get("leitung_assets", 0) < nz:
                raise Verstoss(f"On {z['karte']} there are not {nz} Phone Line(s)")
            zk["leitung_assets"] -= nz
            z["leitungen"] = z.get("leitungen", 0) + nz
            prot.append(f"{ziel_name} picks up {nz} Phone Line(s) [4.3.4, 5.1.6]")
        elif was:
            aufnehmen(s, z, ziel_name, was, prot)
        markieren(z, "Exposed")
        prot.append(f"{ziel_name}: pick up/load, Exposed [5.1.6]")
    # ---------------- Rally
    elif akt == "4.2.3a":
        if not pinned(z):
            raise Verstoss(f"{ziel_name} is not Pinned [RULE 4.2.3a p.24]")
        if vof_gegen(s, z["karte"], z["seite"]) is None or erfolg == "ja":
            z["status"].remove("Pinned")
            prot.append(f"{ziel_name}: remove Pinned marker" + ("" if erfolg == "ja" else " (automatic, no VOF)") + (", VOF back to Basic" if feuert(z) else "") + " [6.5.1]")
            s["letzter_versuch"] = None
        else:
            prot.append(f"{ziel_name}: Rally failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt in ("4.2.3b", "4.2.3c", "4.2.3d"):
        von = {"4.2.3b": "Paralyzed Team", "4.2.3c": "Litter Team", "4.2.3d": "Fire Team"}[akt]
        nach = {"4.2.3b": "Litter Team", "4.2.3c": "Fire Team", "4.2.3d": "Assault Team"}[akt]
        if z["typ"] != von or pinned(z):
            raise Verstoss(f"{ziel_name} must be an Unpinned {von} [RULE {regel}]")
        if vof_gegen(s, z["karte"], z["seite"]) is None or erfolg == "ja":
            z["typ"] = nach
            z["erfahrung"] = LAT_ERFAHRUNG[nach]
            lat_werte_setzen(z, nach)
            prot.append(f"{ziel_name} becomes {nach} (swap counter)" + ("" if erfolg == "ja" else ", automatic without VOF") + " [6.5.1]")
        else:
            prot.append(f"{ziel_name}: conversion failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.3e":
        if z["typ"] != "Assault Team" or pinned(z):
            raise Verstoss("Only an Unpinned Assault Team [RULE 4.2.3e p.24]")
        z["typ"], z["erfahrung"] = "Fire Team", "Green"
        lat_werte_setzen(z, "Fire Team")
        prot.append(f"{ziel_name} becomes Fire Team")
    elif akt == "4.2.3f":
        if not ft_seite(z) or pinned(z):
            raise Verstoss(f"{ziel_name} must be Unpinned on its Fire Team side [RULE 4.2.3f p.24]")
        if vof_gegen(s, z["karte"], z["seite"]) is None or erfolg == "ja":
            z["status"].remove("Fire Team side")
            prot.append(f"Flip {ziel_name} to its front side (experience back to {z.get('erfahrung', 'Line')}) [6.5.1]")
        else:
            prot.append(f"{ziel_name}: Flip failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.3g":
        if not good_order(z) or not ((z["typ"] == "Squad" and steps(z) >= 3) or (z["typ"] == "Weapons Team" and steps(z) == 2)):
            raise Verstoss("Detach Team: Good Order squad with 3-4 steps or 2-step Weapons Team [RULE 4.2.3g p.24]")
        team = o.get("--team", "Assault") + " Team"
        z["steps"] = steps(z) - 1
        neu = neuer_name(s, team)
        s["einheiten"][neu] = lat_neu(z, team, ziel_name)
        s["einheiten"][neu]["status"] = []
        prot.append(f"{ziel_name} down to {z['steps']} steps, place {neu} on {z['karte']}")
    elif akt == "4.2.3h":
        sq = o.get("--squad")
        if not sq:
            raise Verstoss("Specify --squad=<squad with 2-3 steps>")
        q = einheit(s, sq)
        if z["typ"] not in ("Fire Team", "Assault Team") or pinned(z) or q["typ"] != "Squad" or not good_order(q) or not (2 <= steps(q) <= 3) or q["karte"] != z["karte"]:
            raise Verstoss("Supplement: Unpinned Fire/Assault Team plus Good Order squad with 2-3 steps on the same card [RULE 4.2.3h p.24]")
        q["steps"] = steps(q) + 1
        del s["einheiten"][ziel_name]
        prot.append(f"{ziel_name} out of play, {sq} up to {q['steps']} steps (check experience on the Multi-Step Chart)")
    elif akt == "4.2.3i":
        teams = [ziel_name] + [t for t in o.get("--mit", "").split(",") if t]
        sq = o.get("--squad")
        if not sq or sq not in s.get("removed_from_play", []):
            raise Verstoss("Specify --squad=<Removed from Play squad> and --with=<further teams, comma-separated> [RULE 4.2.3i p.24]")
        for t in teams:
            te = einheit(s, t)
            if te["typ"] not in ("Fire Team", "Assault Team") or pinned(te) or te["karte"] != z["karte"]:
                raise Verstoss(f"{t}: only Unpinned Fire/Assault Teams on the same card [RULE 4.2.3i p.24]")
        if not 2 <= len(teams) <= 4:
            raise Verstoss("2 to 4 teams [RULE 4.2.3i p.24]")
        if erfolg == "ja":
            for t in teams:
                del s["einheiten"][t]
            s["removed_from_play"].remove(sq)
            s["einheiten"][sq] = {"typ": "Squad", "seite": "US", "platoon": z.get("platoon"), "erfahrung": o.get("--erfahrung", "Green"), "karte": z["karte"], "bereich": z["bereich"], "status": [], "steps": len(teams), "ziel": None, "vof_rating": "S", "reichweite": "L", "letzter_step": "Fire Team"}
            prot.append(f"{sq} back in play with {len(teams)} steps; experience per Multi-Step Unit Experience Chart from the teams (Assault Line, others Green), here {o.get('--erfahrung', 'Green')} [6.5.2]")
            feuer_eroeffnen(s, prot, nur=[sq])
        else:
            prot.append("Reconstitute failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.3j":
        if not z.get("fire_team_seite") or ft_seite(z):
            raise Verstoss("Only units with a named Fire Team side [RULE 4.2.3j p.24]")
        markieren(z, "Fire Team side")
        prot.append(f"Flip {ziel_name} to its Fire Team side")
    # ---------------- Combat
    elif akt == "4.2.4a":
        zielk = o["--ziel"]
        if erfolg == "ja":
            for m in auf(s, zielk, "Feind"):
                s["einheiten"][m]["spotted"] = True
            prot.append(f"Enemies on {zielk} Spotted: remove Unspotted markers [8.5]")
            feuer_eroeffnen(s, prot)
            s["letzter_versuch"] = None
        else:
            prot.append("Spotting failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.4b":
        if not feuert(z):
            raise Verstoss(f"{ziel_name} is not firing [RULE 4.2.4b p.25]")
        zt = feuerziel_effektiv(s, ziel_name)
        if not [m for m in auf(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
            raise Verstoss(f"No Spotted enemy on {zt} [RULE 4.2.4b p.25]")
        if o.get("--jam") == "ja" and jam_anfaellig(z):
            jam(s, ziel_name, prot)
            erfolg = "nein"
        elif erfolg == "ja":
            ze = o.get("--einheit")
            if not ze:
                raise Verstoss(f"Specify --unit=<target enemy> (stack under a cover marker or random unit without cover on {zt})")
            f = einheit(s, ze)
            for _m in cf_stapel(s, ze):
                s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
            prot.append(f"Concentrated Fire marker on {ze} (stack: {', '.join(cf_stapel(s, ze))}; -1 NCM, cumulative; 2 ammo with ammo tracking) [7.11]")
            if muni(z):
                muni_verbrauch(s, ziel_name, z, 1, "successful Concentrate Fire", prot)    # [RULE 7.11.3 p.56]
        else:
            prot.append("Concentrate Fire failed")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.4d":
        zt = granate_pruefen(s, z, ziel_name, o)
        if zt != z["karte"] and v4(s):
            if "Rifle Grenade" in z.get("assets", []) and z.get("vof_rating") != "G" and not z.get("grenade_ranged"):
                z["assets"].remove("Rifle Grenade")
                prot.append(f"{ziel_name}: Rifle Grenade used up (1 shot, hit or not) [7.6 p.54]")
            elif muni(z):
                muni_verbrauch(s, ziel_name, z, 1, "ranged Grenade Attack", prot)   # [RULE 8.1 p.61 box]
            if moerser(z) and not feuert(z):
                z["ziel"], z["nur_pdf"] = zt, True
                prot.append(f"{ziel_name} (Mortar Team) lays its own PDF to {zt} (counts for Crossfire, removed in Clean Up) [7.3.2 p.53]")
            if o.get("--jam") == "ja" and jam_anfaellig(z):
                jam(s, ziel_name, prot)
                erfolg = "nein"
        if erfolg == "ja" and zt == z["karte"] and v4(s):
            xp_buchen(s, xp_tab(s, "pb_granate") or 1, f"successful Point Blank Grenade Attack ({ziel_name})", prot)
        if erfolg == "ja":
            ze = o.get("--einheit")
            if not ze:
                raise Verstoss("--unit=<target enemy or cover stack>")
            f = einheit(s, ze)
            f.setdefault("grenade", []).append(int(o.get("--wert", -4)))
            prot.append(f"Grenade VOF {o.get('--wert', -4)} on {ze} (cumulative) [7.10.6]")
            prot.append(gegenwurf_hinweis(s, z, f, True))
        else:
            karte(s, zt)["grenade_miss"] = True
            prot.append(f"Grenade Miss Modifier (-1) on {zt} [7.10.4]")
            for m in auf(s, zt, "Feind"):
                prot.append(gegenwurf_hinweis(s, z, s["einheiten"][m], False))
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.4i":
        zt = o["--ziel"]
        if erfolg == "ja":
            platz = o.get("--platz", zt)
            if o.get("--short") == "ja":
                platz = short_platz(s, z, zt, o)
            if s.get("fm_werte") and "Illum" in agentur:
                # [RULE 7.16.2E p.58, 9.2 p.70] Illumination: on any terrain card, without LOS, immediately, no Pending
                iv = (s.get("illum_werte") or {}).get(agentur)
                if o.get("--illum"):
                    ob, _, un = o["--illum"].partition("/")
                    iv = {"oben": int(ob), "unten": int(un) if un else None}
                if not iv:
                    raise Verstoss(f"Illumination values for {agentur} not recorded: read them off the marker, --illum=<top>/<bottom> [9.2]")
                karte(s, platz).setdefault("illum", []).append({"oben": iv["oben"], "unten": iv.get("unten"), "quelle": agentur})
                if isinstance(s.get("feuermissionen"), dict):
                    s["feuermissionen"][agentur] -= 1
                prot.append(f"Illumination marker {iv['oben']:+d}" + (f"/{iv['unten']:+d}" if iv.get("unten") is not None else "") + f" ({agentur}) immediately on {platz}"
                            + (f" (Short instead of {zt})" if platz != zt else "") + f"; Fire Missions: {s['feuermissionen']}; removed in Clean Up [RULE 7.16.2E p.58, 9.2 p.70]")
                if platz == zt and o.get("--target") != "nein":
                    # [RULE 7.16.5 p.59 "after a successful Fire Mission"; BGG Shonai_Dweller 3520262: Illumination also moves the Target marker]
                    alt = s.setdefault("target_marker", {}).get(tm_schluessel(s, agentur))
                    s["target_marker"][tm_schluessel(s, agentur)] = platz
                    prot.append(f"Target marker ({agentur} Concentration) on {platz}" + (f", moved from {alt}" if alt and alt != platz else "") + " [RULE 7.16.5 p.59, BGG 3520262]")
                feuer_eroeffnen(s, prot)
            elif s.get("fm_werte"):
                wert = int(o.get("--wert", s["fm_werte"][agentur]))
                karte(s, platz).setdefault("extern", []).append({"typ": "Pending", "wert": wert, "quelle": ziel_name, "agentur": agentur, "seite": "US"})
                if isinstance(s.get("feuermissionen"), dict):
                    s["feuermissionen"][agentur] -= 1
                elif s.get("feuermissionen") != "unbegrenzt":
                    s["feuermissionen"] -= 1
                bat = liste_opt(o, "--bataillon")
                if bat:
                    gr = s.get("fm_gruppe", {}).get(agentur, agentur)
                    if gr not in s.get("bataillon_fm", []):
                        raise Verstoss(f"Battalion Fire Mission for {gr} not available per mission [RULE 7.16.2B p.58]")
                    if o.get("--short") == "ja" or len(bat) != 2 or len(set(bat)) != 2:
                        raise Verstoss("Battalion Fire Mission: 3 Bursts symbol, two different cards adjacent to the target card: --battalion=K1,K2 [RULE 7.16.2B p.58]")
                    for bk in bat:
                        if abstand(s, zt, bk) != 1 or karte(s, bk).get("staging"):
                            raise Verstoss(f"{bk} is not adjacent to {zt} (terrain card required) [RULE 7.16.2B p.58]")
                        karte(s, bk).setdefault("extern", []).append({"typ": "Pending", "wert": wert, "quelle": ziel_name, "agentur": agentur, "seite": "US"})
                    prot.append(f"Battalion Fire Mission: additional Pending markers {agentur} ({wert:+d}) on {', '.join(bat)}, without observer LOS [RULE 7.16.2B p.58]")
                prot.append(f"Pending Fire Mission Marker {agentur} (value {wert:+d}) on {platz}" + (f" (Short, one card closer to the observer instead of {zt})" if platz != zt else "")
                            + f"; Fire Missions: {s['feuermissionen']}; becomes active in 3.7.1 (Incoming!), takes effect in 3.7.4, is removed in 3.7.1 of the following turn [RULE 7.16.3 p.59, 3.7.1 p.17]")
                if platz == zt or opt(s, "U13_target_marker_bei_short"):
                    if o.get("--target") != "nein":
                        alt = s.setdefault("target_marker", {}).get(tm_schluessel(s, agentur))
                        s["target_marker"][tm_schluessel(s, agentur)] = platz
                        prot.append(f"Target marker ({agentur} Concentration) on {platz}" + (f", moved from {alt}" if alt and alt != platz else "") + "; later calls of this firing unit on this card +1 card [RULE 7.16.5 p.59, FM1 p.42]")
                else:
                    prot.append("Short: Target marker not moved automatically (7.16.5 does not cover this case)" + offen(s, "U13_target_marker_bei_short"))
            else:
                karte(s, platz).setdefault("extern", []).append({"typ": "Pending", "wert": int(o.get("--wert", s.get("fm_wert", -3))), "quelle": ziel_name})
                s["feuermissionen"] -= 1
                prot.append(f"Pending Fire Mission Marker on {platz} (value {o.get('--wert', s.get('fm_wert', -3))}), Fire Mission crossed off ({s['feuermissionen']} left); active from 3.7.1 of this turn [RULE 3.7.1 p.17, FM1 p.44]. On 'Short!': one card closer to the observer (--place) [7.16.3, 7.16.4]")
        else:
            prot.append("Call for Fire failed, no Fire Mission used")
            s["letzter_versuch"] = [ziel_name, akt, s["phase"]]
    elif akt == "4.2.4j":
        indirect_lay(s, hq_name, orig_name, orig, ziel_name, z, o, prot, gi)
    elif akt == "4.2.1l":
        alt = s.get("ccp")
        s["ccp"] = z["karte"]
        prot.append(f"Casualty Collection Point on {z['karte']}" + (f" (previously {alt}, only one CCP at a time)" if alt and alt != z["karte"] else "")
                    + "; Casualties lying there at the end of the turn are evacuated in Clean Up [RULE 5.1.7 p.33/34, FM1 p.42]")
    elif akt == "4.2.4k":
        if not feuert(z):
            raise Verstoss(f"{ziel_name} is not firing [RULE 4.2.4k p.26]")
        kk, zt = z["karte"], feuerziel_effektiv(s, ziel_name)
        for n, e in s["einheiten"].items():
            if e["seite"] == "US" and e["karte"] == kk and feuert(e) and feuerziel_effektiv(s, n) == zt:
                e["ziel"] = None
                e.pop("konzentriert", None)
        prot.append(f"Cease Fire: all units on {kk} firing at {zt} cease fire; they reopen fire immediately when a Spotted enemy is in LOS and range [6.3.3]")
        feuer_eroeffnen(s, prot)
    elif akt == "4.2.4l":
        zt = o.get("--ziel")
        if not zt or not feuert(z):
            raise Verstoss("Shift Fire: --target=<card in LOS>, unit must be firing [RULE 4.2.4l p.26]")
        karte(s, zt)
        if [m for m in auf(s, zt, "Feind") if not s["einheiten"][m].get("spotted")] and not auf(s, zt, "US"):
            raise Verstoss("Cards with Unspotted enemies may not be fired at [6.3.3]")
        ok, grund = los(s, orig["karte"], zt)
        if not ok:
            raise Verstoss(f"Originator has no LOS to {zt}: {grund}")
        kk, alt = z["karte"], feuerziel_effektiv(s, ziel_name)
        for n, e in s["einheiten"].items():
            if e["seite"] == "US" and e["karte"] == kk and feuert(e) and feuerziel_effektiv(s, n) == alt and in_reichweite(s, e, zt):
                e["ziel"] = zt
                e.pop("konzentriert", None)
        prot.append(f"Shift Fire: units on {kk} now fire at {zt} (move PDF)" + pdf_hinweis(s, kk, zt, None) + " [6.3.3]")
    elif akt == "4.2.1b":
        lv = s.get("letzter_versuch")
        if not lv or lv[0] != ziel_name or lv[2] != s["phase"]:
            raise Verstoss("Exhort only for a unit that has just failed an attempt [RULE 4.2.1b p.22]")
        if erfolg not in ("ja", "nein"):
            raise Verstoss("Exhort: draw one more Action card; --success=yes|no (symbol of the original attempt)")
        s["letzter_versuch"] = None
        if erfolg == "ja":
            s["exhort_frei"] = [ziel_name, lv[1], s["phase"]]    # [RULE 4.2.1b p.22] 'Draw one more Action card'
        prot.append(f"Exhort for {ziel_name} ({lv[1]}): " + ("attempt counts as successful; now enter the effect with the original order and --success=yes (costs no Command, add --free=yes)" if erfolg == "ja" else "again no success"))
    elif akt == "4.2.1c":
        if v4(s):
            pyro_ausfuehren(s, z, ziel_name, o, prot)
        else:
            prot.append(f"{ziel_name} uses pyrotechnics (effect per Mission Log) [4.4]")
    elif akt == "4.2.1d":
        hqn = o.get("--hq")
        if not hqn or hqn not in s.get("removed_from_play", []):
            raise Verstoss("Specify --hq=<Removed from Play PLT HQ> [RULE 4.2.1d p.22]")
        ziel_plt = s.get("rfp_daten", {}).get(hqn, {}).get("platoon")
        if hqn not in s.get("rfp_daten", {}):
            ziel_plt = z.get("platoon")
            prot.append(f"Platoon of {hqn} not stored (game state before v3), check the platoon of {ziel_name} on the board")
        if not good_order(z) or not (z["typ"] == "Staff" or (ziel_plt and z.get("platoon") == ziel_plt)):
            raise Verstoss(f"Recipient: CO Staff or a Good Order step of platoon {ziel_plt} [RULE 6.5.2 p.49]")
        hq_zurueck(s, hqn, z, prot)
        schritt_abgeben(s, ziel_name, prot, (o.get("--team") or "Fire").capitalize())
    elif akt == "4.2.1e":
        raise Verstoss("Reconstitute the CO HQ is given by the BN HQ in the BN HQ Impulse: fof.py order BN <unit> 4.2.1e [RULE 6.5.2 p.50]")
    elif befehl_v4(s, hq_name, ziel_name, akt, o, orig, prot):
        pass
    else:
        raise Verstoss(f"Action {akt} not implemented yet")
    if exhort_nach:
        s["exhort_frei"] = None
    elif o.get("--gratis") != "ja":
        bezahlen(s, hq_name, kosten, regel)
    for n in (bewegte or [ziel_name]):
        if not exhort_nach:
            s["impuls_aktionen"].setdefault(n, []).append(akt)
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    s.pop("_befehl_opts", None)
    txt = f"{hq_name} orders {ziel_name}: {name}" + (f" to {o['--ziel']}" if o.get("--ziel") else "") + (f", attempt {erfolg}" if erfolg else "") + (f" (with {', '.join(bewegte)})" if len(bewegte) > 1 else "") + f"; cost {0 if o.get('--gratis') == 'ja' else kosten}, remaining {k['verfuegbar']}+{k['gespart']}"
    speichern(s, txt + "; " + "; ".join(prot), regel)
    print("ALLOWED [RULE " + regel + "]")
    print(txt)
    ausgabe(prot, s)


def cmd_feuer(s, args):
    n, ziel = args[0], args[1]
    e = einheit(s, n)
    prot = []
    if ziel == "aus":
        e["ziel"] = None
        e.pop("ziel_offen", None)
        e.pop("konzentriert", None)
        prot.append(f"{n} no longer fires (correction)")
    else:
        karte(s, ziel)
        if e.get("ziel_offen") and ziel not in e["ziel_offen"]:
            raise Verstoss(f"{ziel} not among the candidates {', '.join(e['ziel_offen'])}")
        e["ziel"] = ziel
        e.pop("ziel_offen", None)
        prot.append(f"{n} fires at {ziel}" + ("" if ziel == e["karte"] else f", PDF from {e['karte']} to {ziel}" + pdf_hinweis(s, e['karte'], ziel, n)))
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, "; ".join(prot), "6.1.1 p.39")
    ausgabe(prot, s)


# ---------------------------------------------------------------- PC / packages / external
def paket_einheiten(pk):
    """Units of a package: list 'einheiten' (v3, e.g. package 7 'Squad in Trench + LMG in Bunker') or flat package (v2)."""
    if pk.get("einheiten"):
        return pk["einheiten"]
    if pk.get("einheit") or pk.get("einheit_wahl"):
        return [pk]
    return []


def im_spiel_zahl(s, typname):
    return sum(1 for e in s["einheiten"].values() if e["seite"] == "Feind" and e.get("typname") == typname)


def cover_zahl(s, typ):
    return sum(1 for c in s["karten"].values() for cv in c.get("cover", []) if cv["typ"] == typ)


def typ_frei(s, u, bedarf=None):
    """Free counter types for a package unit; 'einheit_wahl' = choose the type at random [FM1 p.48], type in use: take another [RULE 8.3 p.62]."""
    cm, bedarf = s.get("countermix", {}), bedarf or {}
    namen = u.get("einheit_wahl") or [u["einheit"]]
    return [n for n in namen if im_spiel_zahl(s, n) + bedarf.get(n, 0) < (cm.get(n, 1) if cm.get(n, 1) is not None else 1)]


def paket_verfuegbar(s, p, wahl=None):
    """[RULE 8.3 p.62/63, FM1 p.48 'Respect the counter mix'] all counters and markers of the package must be free.
    Marker packages without a unit (Incoming) are occupied as long as their marker is on the board ('im_spiel')."""
    pk = s["pakete"][p]
    if pk.get("wahl"):
        return any(all(typ_frei(s, u) for u in opt_) for opt_ in pk["wahl"].values())     # v4: package with a choice (Normandy package 5)
    einh = [u for u in paket_einheiten(pk) if not u.get("optional_r") and not u.get("nur_wenn_verfuegbar")]
    if not einh and "place_vof" in pk:
        return True
    if not einh:
        return not pk.get("im_spiel")
    cm = s.get("countermix", {})
    bedarf, cbedarf = {}, {}
    for u in einh:
        frei = typ_frei(s, u, bedarf)
        if wahl and u.get("einheit_wahl"):
            frei = [x for x in frei if x == wahl]
        if not frei:
            return False
        bedarf[frei[0]] = bedarf.get(frei[0], 0) + 1
        if u.get("cover"):
            cbedarf[u["cover"]] = cbedarf.get(u["cover"], 0) + 1
    return all(cover_zahl(s, t) + n <= cm[t] for t, n in cbedarf.items() if cm.get(t) is not None)   # limit only cover types counted in the counter mix (Basic Cover unlimited); null = not recorded


def feind_pdf_oder_vof(s, k):
    """[RULE 8.4.3 p.63] 'cannot place a package on a card which is along the PDF of another enemy unit or if it has an enemy VOF marker'."""
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and feuert(e) and e["ziel"] != e["karte"]:
            if k in (linie(s, e["karte"], e["ziel"]) or []) + [e["ziel"]]:
                return f"along the PDF of {n}"
    for x in karte(s, k).get("extern", []):
        if x.get("seite") == "Feind" or any(pk.get("name") == x.get("quelle") for pk in s.get("pakete", {}).values()):
            return "enemy VOF marker"
    return None


def gueltige_plaetze(s, pk, kid):
    out = []
    einh = paket_einheiten(pk) or [pk]
    ohne_pb = all(u.get("cover") in STRUKTUR for u in einh)
    hi = min(REICHWEITE.get((u.get("reichweite") or "L").split("-")[-1], 2) for u in einh)
    v3 = kompanie(s) or "optionen" in s
    for k, c in s["karten"].items():
        if pk.get("reihe") and c["reihe"] != pk["reihe"]:
            continue
        if c.get("staging") or auf(s, k, "Feind"):
            continue
        if auf(s, k, "US") and k != kid and not (v3 and ohne_pb):
            continue            # [RULE 8.4.3 p.63] '(unless Point Blank fire is not possible for the units in the package)'
        if v3 and ohne_pb and k == kid:
            continue            # a bunker cannot fire Point Blank, but must be able to open fire on the trigger card
        if k != kid:
            if abstand(s, k, kid) > hi or not los(s, k, kid)[0]:
                continue
            if any(auf(s, zw, "US") for zw in (linie(s, k, kid) or [])):
                continue
        if v3 and feind_pdf_oder_vof(s, k):
            continue
        out.append(k)
    return out


def cmd_pc(s, args):
    if args and args[0] in ("aufdecken", "setzen") and cmd_pc_v4(s, args):
        return
    if not args:
        offen_ = [k for k, c in s["karten"].items() if c.get("pc") and auf(s, k, "US")]
        print("PC markers with friendly units: " + (", ".join(f"{k} (PC {s['karten'][k]['pc']})" for k in offen_) if offen_ else "none"))
        return
    if args[0] not in ("kontakt", "frei"):
        kid = args[0]
        c = karte(s, kid)
        if not c.get("pc"):
            raise Verstoss(f"{kid} has no PC marker")
        if not auf(s, kid, "US"):
            raise Verstoss(f"{kid}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62]")
        if s["phase"] != "3.7.2":
            print(f"Note: PC resolution belongs in 3.7.2, currently {s['phase']}")
        # E39 (the player 07.10.2026): reveal ?-markers only on cards with friendly units (8.2.4; developer AAR BGG 2585005)
        if "?" in (c.get("pc"), c.get("pc2")) or any("?" in (cc.get("pc"), cc.get("pc2")) for kk, cc in s["karten"].items() if auf(s, kk, "US")):
            raise Verstoss("First reveal the PC markers showing '?' on cards with friendly units: fof.py pc reveal <card> <A|B|C> [RULE 8.2.4 p.62, E39]")
        hoeher = [k for k, cc in s["karten"].items() if cc.get("pc") and auf(s, k, "US") and cc["pc"] < c["pc"]]
        if hoeher:
            raise Verstoss(f"First resolve the higher letters: {', '.join(hoeher)} [RULE 8.2.4 p.62]")
        n = PC_DRAWS[c["pc"]][s["aktivitaet"] or "No Contact"]
        print(f"PC {c['pc']} on {kid} at {s['aktivitaet']}: " + ("Auto, contact without a draw" if n == 0 else f"draw {n} Action cards (all), contact if one shows 'Contact' at the top") + " [8.2.4, Charts 1]")
        tab = s.get("paket_tabelle", {}).get("PC " + c["pc"], {})
        if s.get("gegenangriff") and c["pc"] == "A" and s.get("paket_tabelle_gegenangriff") and opt(s, "U28_gegenangriff_alle_pc_a"):
            tab = s["paket_tabelle_gegenangriff"]["PC A"]
            print("Counter-attack active: PC A uses the Counter-Attack list" + offen(s, "U28_gegenangriff_alle_pc_a") + " [Normandy M1 MSR 1 p.19]")
        print("On contact: draw an Action card, column PC " + c["pc"] + ": " + "; ".join(f"R# {v} = package {p} ({s['pakete'][p]['name']}, {'free' if paket_verfuegbar(s, p) else 'IN USE'})" for p, v in tab.items() if p in s["pakete"]))
        if v4(s):
            rt = s.get("richtung_tabelle", {})
            print(f"Package that cannot be placed: draw again (8.3 p.63, Normandy p.19; E6); if none can be placed, no contact. Direction per unit on the friendly card: R# column {rt.get('spalte', 8)}: "
                  + ", ".join(f"{b} {v}" for b, v in rt.items() if b != "spalte") + " [8.4.2 p.63]. Then fof.py pc contact <card> <package> --direction=.. (the tool names any further inputs)")
        elif kompanie(s):
            print("Occupied package drawn: ignore the draw and choose from the placeable packages (E6, FM1 p.48); if none can be placed, no contact. Squad type (A or A/S) at random [FM1 p.48].")
        else:
            print("Occupied package drawn: ignore the draw and draw again until an available package comes up (8.3); FM1 p.26 instead allows choosing from the available ones; if none can be placed, no contact.")
        return
    if args[0] == "frei":
        kid = args[1]
        c = karte(s, kid)
        if not c.get("pc"):
            raise Verstoss(f"{kid} has no PC marker")
        alt = c["pc"]
        c["pc"] = None
        speichern(s, f"PC {alt} on {kid}: no contact, PC marker removed", "8.2.4 p.62")
        print(f"No contact on {kid}. Remove the PC marker [8.2.4].")
        print(stempel(s))
        return
    kid, paket = args[1], args[2]
    o = opts_parse(args[3:])
    c = karte(s, kid)
    if not c.get("pc"):
        raise Verstoss(f"{kid} has no PC marker")
    pk = s.get("pakete", {}).get(paket)
    if not pk:
        raise Verstoss(f"Package {paket} unknown")
    if not auf(s, kid, "US"):
        raise Verstoss(f"{kid}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62, 3.7.2 p.17]")
    if "place_vof" in pk:
        if c.get("pc") == "?":
            raise Verstoss("Reveal the PC marker first: fof.py pc reveal <card> <A|B|C>")
        return pc_kontakt_v4(s, kid, paket, pk, o)
    if not paket_verfuegbar(s, paket):
        raise Verstoss(f"Package {paket} not available (counter mix); ignore the draw [8.3 p.63, FM1 p.26]")
    prot = []
    pc_alt = c["pc"]
    einh = paket_einheiten(pk)
    if einh:
        platz = o.get("--platz", kid if pk["platz"].startswith("trigger") else None)
        gueltig = gueltige_plaetze(s, pk, kid)
        if not platz:
            raise Verstoss(f"Package {paket} ('{pk['platz']}'): valid cards {', '.join(gueltig) if gueltig else 'NONE (redraw the package; if none can be placed, remove the PC marker without contact)'}; draw a random card, column {len(gueltig)}, and --place=<card> [8.4.3]")
        karte(s, platz)
        if platz not in gueltig:
            raise Verstoss(f"{platz} is not a valid place (row, LOS, range, enemies, friendly units in between, enemy PDF/VOF). Valid: {', '.join(gueltig) or 'none'} [8.4.3 p.63]")
        # determine the counter type for each unit
        bedarf, typen = {}, []
        for u in einh:
            frei = typ_frei(s, u, bedarf)
            if u.get("einheit_wahl") and len(frei) > 1:
                w = o.get("--typ")
                if w not in frei:
                    raise Verstoss(f"Choose the squad type at random (R#/{len(frei)}): {', '.join(frei)}; then --type=<counter name> [FM1 p.48]")
                prot.append(f"Squad type at random: {w} [FM1 p.48]")
                frei = [w]
            elif u.get("einheit_wahl") and len(frei) == 1 and len(u["einheit_wahl"]) > 1:
                prot.append(f"Squad type: only {frei[0]} is free, this one is taken [RULE 8.3 p.62]")
            bedarf[frei[0]] = bedarf.get(frei[0], 0) + 1
            typen.append(frei[0])
        neue = []
        for u, typname in zip(einh, typen):
            werte = dict(u)
            werte.update(u.get("varianten", {}).get(typname, {}))
            fname = neuer_name(s, typname)
            cid = None
            if werte.get("cover"):
                cid = neuer_cover(s, platz, werte["cover"], werte.get("cover_wert", 1))
                cv = [x for x in karte(s, platz)["cover"] if x["id"] == cid][0]
                if werte.get("cover_kapazitaet"):
                    cv["kapazitaet"] = werte["cover_kapazitaet"]
                if werte["cover"] in STRUKTUR and platz != kid:
                    cv["richtung"] = list(richtung(s, platz, kid))
                prot.append(f"{werte['cover']} marker {cid} (+{werte.get('cover_wert', 1)}) on {platz}")
            e = {"typ": werte.get("typ", "Weapons Team"), "typname": typname, "seite": "Feind", "erfahrung": werte.get("erfahrung", "Line"),
                 "karte": platz, "bereich": cid or "offen", "status": [], "steps": werte.get("steps", 1), "vof_rating": werte["vof_rating"],
                 "reichweite": werte.get("reichweite", "L"), "spotted": bool(pk.get("spotted", werte.get("spotted"))), "paket": paket, "pc_herkunft": pc_alt,
                 "fire_team_seite": werte.get("fire_team_seite", werte.get("steps", 1) == 1), "ft_vof": werte.get("ft_vof", "S"),
                 "letzter_step": werte.get("letzter_step"), "ziel": None, "kein_point_blank": werte.get("cover") in STRUKTUR}
            if werte.get("breakdown_hinweis"):
                e["breakdown_hinweis"] = werte["breakdown_hinweis"]
            s["einheiten"][fname] = e
            if werte.get("cover") in STRUKTUR:
                e["bunker_richtung"] = kid
                prot.append(f"Point the bunker arrow at {kid}; fires only in this direction, never Point Blank; redraw Shift Fire results [5.3.2]")
            prot.append(f"Enemy {fname} ({typname}, VOF {werte['vof_rating']}, {werte.get('steps', 1)} steps) on {platz}" + (f" under {cid}" if cid else " without cover") + (", Spotted" if e["spotted"] else ", place an Unspotted marker"))
            e["ziel"] = kid
            prot.append(f"{fname} opens fire on {kid}" + ("" if platz == kid else f", PDF from {platz} to {kid}" + pdf_hinweis(s, platz, kid, fname)) + " [8.4.3]")
            neue.append(fname)
        for zw in (linie(s, platz, kid) or []):
            if karte(s, zw).get("pc") and karte(s, zw).get("elevation", 1) == karte(s, platz).get("elevation", 1):
                karte(s, zw)["pc"] = None
                prot.append(f"PC marker on {zw} removed (fired over) [8.4.4]")
        if s["einheiten"][neue[0]]["spotted"]:
            for m, f in s["einheiten"].items():
                if f["seite"] == "US" and f["karte"] == platz and feuert(f) and f["ziel"] != platz and not kein_pb(s, f):
                    f["ziel"] = platz
                    f.pop("konzentriert", None)
                    prot.append(f"{m} shifts fire to its own card (Point Blank), the old PDF lapses [6.1.2]")
            feuer_eroeffnen(s, prot)
        else:
            prot.append("Enemy Unspotted: no return fire, spot it first [8.5, 6.1.1]")
    else:
        c.setdefault("extern", []).append({"typ": "Incoming", "wert": pk.get("wert", -3), "quelle": pk["name"], "seite": "Feind"})
        prot.append(f"{pk['name']}: Incoming marker (VOF {pk.get('wert', -3)}) active on {kid}, takes effect in this Combat Effects Segment; blocks LOS out of {kid} [8.10, 5.4]")
        for n, e in s["einheiten"].items():
            if e["karte"] == kid and feuert(e) and e["ziel"] != kid:
                e["ziel"] = None
                prot.append(f"{n} loses LOS out of the card, remove the PDF [6.1.2]")
    pk["im_spiel"] = True
    c["pc"] = None
    prot.append(f"Remove the PC marker from {kid} [8.2.4]")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, f"Contact on {kid}: package {paket} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4.3 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    ausgabe(prot, s)


def cmd_aufstellen(s, args):
    """[RULE 2.3.5 p.10] Offensive mission: setup in the Staging Area; [RULE 2.3.3 p.10] attachments before the game starts, fixed afterwards."""
    if not in_aufstellung(s):
        raise Verstoss("Setup and attachments only before turn 1 starts (phase 3.1); no regrouping afterwards [RULE 2.3.3 p.10]")
    n = args[0]
    e = einheit(s, n)
    if e["seite"] != "US":
        raise Verstoss("Friendly units only")
    o = opts_parse(args[1:])
    prot = []
    if "--platoon" in o:
        p = o["--platoon"]
        if ist_hq(e) or e["typ"] == "Squad":
            raise Verstoss(f"{n} belongs permanently to its platoon; attachments and company units can be assigned [RULE 2.3.2 p.10]")
        hqs = {x.get("platoon"): m for m, x in s["einheiten"].items() if x.get("ebene") == "PLT"}
        if p == "keiner":
            e["platoon"], e["attached_an"] = None, []
            prot.append(f"{n} assigned to no platoon; orders only from the CO HQ (and via General Initiative) [RULE 2.3.3 p.10]")
        else:
            if p not in hqs:
                raise Verstoss(f"Platoon {p} unknown; available: {', '.join(sorted(k for k in hqs if k))}")
            e["platoon"], e["attached_an"] = p, [hqs[p]]
            prot.append(f"{n} assigned to {hqs[p]} for the whole mission [RULE 2.3.3 p.10]")
    if v4(s):
        aufstellen_v4(s, n, e, o, prot)
        e = s["einheiten"].get(n, e)
    kz = [a for a in args[1:] if not a.startswith("--")]
    if kz:
        k = kz[0]
        if n not in s["einheiten"] and n == "Mtr Sec" and s.get("moerser_wahl") == "teams" and karte(s, k).get("staging"):
            for tn in s.get("reserve_einheiten", {}):
                if tn in s["einheiten"]:
                    s["einheiten"][tn]["karte"] = k
            prot.append(f"Mortar Teams into the Staging Area {k}")
            speichern(s, "Setup: " + "; ".join(prot), "2.3.3 p.10, 2.3.5 p.10")
            ausgabe(prot, s)
            return
        if n not in s["einheiten"]:
            raise Verstoss(f"{n} is no longer in play")
        if s.get("patrouille_mission"):
            kc = karte(s, k)
            cop = s.get("ziele", {}).get("cop")
            if e.get("stationaer"):
                if kc["reihe"] != 1 and k != cop:
                    raise Verstoss(f"{n} is not on patrol: only into the fortifications of row 1 or into the Combat Outpost [MSR 1]")
                if k == cop:
                    plts = {x.get("platoon") for m, x in s["einheiten"].items() if x["seite"] == "US" and x.get("karte") == cop and m != n}
                    if e.get("platoon") and plts - {None, e.get("platoon")}:
                        raise Verstoss("Units of at most one platoon in the Combat Outpost [MSR 1]")
                if kc.get("cover") and not o.get("--bereich"):   # L55: "Place any others in the fortifications on Row 1"
                    raise Verstoss(f"{n} is not on patrol: set it up in the fortifications, --area=" + "|".join(c["id"] for c in kc["cover"])
                                   + " [Normandy M3 p.26 MSR 1: 'Place any others in the fortifications on Row 1']")
            elif kc["reihe"] != 1:
                raise Verstoss(f"The patrol sets up on row 1 [2.6.1, MSR 4]")
        elif not karte(s, k).get("staging") and not (s.get("reattempt_setup") and gesichert(s, k)):
            raise Verstoss(f"{k} is not a staging card; offensive mission: setup in the Staging Area [RULE 2.3.5 p.10]"
                           + ("; in a reattempt also secured cards (3.9 step 5)" if s.get("reattempt_setup") else ""))
        e["karte"], e["bereich"] = k, "offen"
        if o.get("--bereich") and (s.get("reattempt_setup") or s.get("patrouille_mission")):
            bereich_setzen(s, e, n, o["--bereich"])
        prot.append(f"{n} {'into the Staging Area' if karte(s, k).get('staging') else 'on card' if s.get('patrouille_mission') else 'onto the secured card'} {k}" + (f" under {e['bereich']}" if e["bereich"] != "offen" else ""))
    if not prot:
        raise Verstoss("setup <unit> <staging card> and/or --platoon=<no>|none" + (" | --net= --mortar= --asset= --lines= --pyro= --device=" if v4(s) else ""))
    speichern(s, "Setup: " + "; ".join(prot), "2.3.3 p.10, 2.3.5 p.10")
    ausgabe(prot, s)


def cmd_funk(s, args):
    """Radio overview, single check, R# 1/2 on radio damage."""
    if not args:
        if not kompanie(s):
            print("No CO HQ on the board; communication as specified by the mission.")
            return
        for t in funk_uebersicht(s):
            print("- " + t)
        return
    if args[0] == "pruefen":
        a, b = args[1], args[2]
        einheit(s, a), einheit(s, b)
        try:
            kommunikation(s, a, b)
            print(f"ALLOWED: {a} and {b} in communication [RULE 4.3 p.27]")
        except Verstoss as v:
            print(f"VIOLATION: {v}")
        for h in dict.fromkeys(s.pop("_hinweise", [])):
            print("Note: " + h)
        return
    if args[0] == "schaden":
        kid, typ, erg = args[1], args[2], args[3]
        c = karte(s, kid)
        g = [x for x in c.get("assets", []) if x["typ"] == typ and x.get("schaden_offen")]
        if not g:
            raise Verstoss(f"On {kid} there is no {typ} with a pending damage draw")
        if erg == "zerstoert":
            c["assets"].remove(g[0])
            s.setdefault("funk_zerstoert", []).append(f"{g[0]['typ']} {g[0]['netz']}")
            prot = [f"{typ} {g[0]['netz']} on {kid} destroyed, removed from play [RULE 4.3.5 p.30]"]
        elif erg == "heil":
            g[0]["schaden_offen"] = False
            prot = [f"{typ} {g[0]['netz']} lies on {kid}, can be picked up with 4.2.2h (--what={typ}) [RULE 4.3.5 p.30]"]
        else:
            raise Verstoss("heil (intact) | zerstoert (destroyed)")
        speichern(s, "; ".join(prot), "4.3.5 p.30")
        ausgabe(prot, s)
        return
    raise Verstoss("radio | radio check <hq> <unit> | radio damage <card> <device> intact|destroyed")


def cmd_ablegen(s, args):
    """[RULE 5.1.6B p.33] Drop without spending a command, at any time."""
    n, was = args[0], args[1]
    e = einheit(s, n)
    c = karte(s, e["karte"])
    if was.lower() == "casualty":
        if not e.get("traegt_casualties"):
            raise Verstoss(f"{n} is not carrying a casualty")
        e["traegt_casualties"] -= 1
        c["casualties"] = c.get("casualties", 0) + 1
        prot = [f"{n} drops a casualty on {e['karte']}" + (" (CCP: evacuation in Clean Up)" if s.get("ccp") == e["karte"] else "")]
    elif ":" in was and was.split(":")[0] in MUNITION_KAP:
        prot = []
        muni_ablegen(s, e, n, was, prot)
    elif was.startswith("Leitung"):
        nz = int(was.split(":")[1]) if ":" in was else 1
        if e.get("leitungen", 0) < nz:
            raise Verstoss(f"{n} is not carrying {nz} Phone Line(s)")
        e["leitungen"] -= nz
        c["leitung_assets"] = c.get("leitung_assets", 0) + nz
        prot = [f"{n} drops {nz} Phone Line(s) as an asset on {e['karte']} (no phone line marker) [5.1.6B, BGG D3]"]
    else:
        g = [x for x in geraete(e) if x["typ"] == was or f"{x['typ']} {x['netz']}" == was]
        if not g:
            raise Verstoss(f"{n} is not carrying '{was}'")
        e["funk"].remove(g[0])
        c.setdefault("assets", []).append({"typ": g[0]["typ"], "netz": g[0]["netz"], "schaden_offen": False})
        prot = [f"{n} drops {g[0]['typ']} {g[0]['netz']} on {e['karte']}"]
    speichern(s, "; ".join(prot), "5.1.6B p.33")
    ausgabe(prot, s)


def cmd_optionen(s, args):
    if "optionen" not in s:
        print("This mission has no open rules questions (no field 'optionen' in the setup).")
        return
    for k, (std, txt) in OPTIONEN_STANDARD.items():
        if not v4(s) and int(re.match(r"U(\d+)", k).group(1)) > 13:
            continue
        wert = opt(s, k)
        print(f"- {k.split('_')[0]} {k}: {wert}" + (" (default)" if wert == std else f" (default {std})") + f"; default reading: {txt}")
    print("Change only by the player's decision (E entry in data/klarstellungen.md) and by adjusting 'optionen' in the setup or game state.")


def cmd_notiz(s, args):
    """Free text into the log (corrections, card numbers supplied later)."""
    text = " ".join(args)
    speichern(s, "NOTE: " + text, None)
    ausgabe([text], s)


def cmd_extern(s, args):
    kid = args[0]
    c = karte(s, kid)
    prot = []
    if args[1] == "weg":
        c["extern"] = []
        prot.append(f"external VOF on {kid} removed")
    else:
        typ, wert = args[1], int(args[2])
        if typ not in ("Incoming", "Mines", "AirStrike", "Smoke", "Pending"):
            raise Verstoss("Type: Incoming | Mines | AirStrike | Smoke | Pending")
        c.setdefault("extern", []).append({"typ": typ, "wert": wert, "quelle": args[3] if len(args) > 3 else typ})
        prot.append(f"{typ} {wert} on {kid}")
        if typ in ("Incoming", "AirStrike", "Smoke"):
            for n, e in s["einheiten"].items():
                if e["karte"] == kid and feuert(e) and e["ziel"] != kid:
                    e["ziel"] = None
                    prot.append(f"{n} loses LOS out of the card, remove the PDF [6.1.2]")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, "; ".join(prot), "5.4 p.38")
    ausgabe(prot, s)


def cmd_sicht(s, args):
    """visibility <light> [<weather>] [--this-turn-only=yes]: [RULE 9.0 p.69] set Light Level and Weather."""
    if not args:
        l, w = licht_wetter(s)
        print(f"Light {l:+d}, weather {w:+d}, total {l + w:+d}: {'Limited Visibility (9.1)' if l + w >= 2 else 'normal visibility'}")
        return
    s["licht"] = int(args[0])
    s.pop("visibility", None)
    o = opts_parse(args[1:])
    if len(args) > 1 and not args[1].startswith("--"):
        s["wetter"] = int(args[1])
        if o.get("--nur_zug") == "ja":
            s["wetter_nur_zug"] = True
    sicht_aktualisieren(s)
    l, w = licht_wetter(s)
    txt = f"Visibility: light {l:+d}, weather {w:+d}, total {l + w:+d}" + (": Limited Visibility, 4 Commands per impulse, saving G2/L4/V6, LOS Close Range [9.1]" if l + w >= 2 else "")
    feuer_eroeffnen(s, [])
    speichern(s, txt, "9.0 p.69")
    print(txt)
    print(stempel(s))


def cmd_illum(s, args):
    """illum <card> <top> [<bottom>] [--origin=..] | illum <card> remove: [RULE 9.2 p.70] immediately, no Pending, removed in Clean Up."""
    kid = args[0]
    c = karte(s, kid)
    if len(args) > 1 and args[1] == "weg":
        c["illum"] = []
        txt = f"Illumination on {kid} removed"
    else:
        o = opts_parse(args[1:])
        rest = [a for a in args[1:] if not a.startswith("--")]
        m = {"oben": int(rest[0]), "unten": int(rest[1]) if len(rest) > 1 else None, "quelle": o.get("--quelle", "?")}
        c.setdefault("illum", []).append(m)
        txt = (f"Illumination marker {m['oben']:+d}" + (f"/{m['unten']:+d}" if m["unten"] is not None else "") + f" ({m['quelle']}) on {kid}: "
               f"top value for {kid}" + (", bottom value for the adjacent cards" if m["unten"] is not None else "") + "; not cumulative, light plus illum never better than +0 [9.2]")
        if licht_wetter(s)[1] >= 2:
            txt += "; weather +2 or more: cards do not count as illuminated (9.2.1)"
    feuer_eroeffnen(s, [])
    speichern(s, txt, "9.2 p.70")
    print(txt)
    print(stempel(s))


def cmd_feind(s, args):
    name = args[0]
    f = einheit(s, name)
    if f["seite"] != "Feind":
        raise Verstoss(f"{name} is not an enemy unit")
    prot = []
    for a in args[1:]:
        if a == "spotted":
            for m in auf(s, f["karte"], "Feind"):
                s["einheiten"][m]["spotted"] = True
            prot.append(f"Enemies on {f['karte']} Spotted (per card) [8.5]")
            feuer_eroeffnen(s, prot)
        elif a == "unspotted":
            if f.get("typname") != "Sniper" and not f.get("out_of_ammo"):
                prot.append("WARNING: only snipers and Out-of-Ammo Fire Teams become Unspotted again [8.8, 8.11.1]")
            for m in auf(s, f["karte"], "Feind"):
                s["einheiten"][m]["spotted"] = False
            prot.append(f"Enemies on {f['karte']} Unspotted")
        elif a == "pinned":
            markieren(f, "Pinned")
            prot.append(f"{name} Pinned (its VOF becomes 'All Pinned' +2)")
        elif a == "unpinned":
            f["status"] = [x for x in f["status"] if x != "Pinned"]
            prot.append(f"{name} Pinned removed")
        elif a == "weg":
            feind_entfernen(s, name, prot, grund="correction/removal")
            break
        elif a.startswith("karte="):
            karte(s, a[6:])
            granate_verfaellt(s, f, name, prot)
            f["karte"], f["bereich"] = a[6:], "offen"
            markieren(f, "Exposed")
            prot.append(f"{name} to {f['karte']}, Exposed [8.6.1C]")
            feuer_nach_bewegung(s, name, prot)
            if v4(s):
                minencheck_anfordern(s, [name], f["karte"], prot, "enemy enters a mined card")
        elif a.startswith("cover="):
            granate_verfaellt(s, f, name, prot)
            bereich_setzen(s, f, name, a[6:])
            prot.append(f"{name} under {a[6:]}")
        elif a.startswith("steps="):
            f["steps"] = int(a[6:])
            prot.append(f"{name} {f['steps']} steps")
        else:
            raise Verstoss(f"Unknown entry {a}")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, "; ".join(prot), None)
    ausgabe(prot, s)


# ---------------------------------------------------------------- NCM and hits (6.4)
def cc_zeile(s, e):
    """[RULE 5.2.3 p.36] Two C&C values: the higher one if any fire comes across a dark edge; the lower one if all
    fire comes across white edges, as Incoming/indirect mortar fire, or from within the card itself."""
    kid = e["karte"]
    c = karte(s, kid)
    if c.get("cc2") is None:
        return (f"Terrain {c['terrain']}", c.get("cc", 0))
    dunkel = []
    for x in vof_eintraege(s, kid):
        if x[3] not in (None, e["seite"]) or x[4] is None or x[4] == kid:
            continue                                  # external (Incoming, Indirect), Point Blank, or does not hit this side
        if rand(c, richtung(s, kid, x[4])) != "weiss":
            dunkel.append(f"{x[2]} from {x[4]}")
    if dunkel:
        return (f"Terrain {c['terrain']} (higher value, fire across a dark edge: {', '.join(dunkel)})", c["cc"])
    return (f"Terrain {c['terrain']} (lower value: fire only across white edges, as Incoming/Indirect or from within the card)", c["cc2"])


def ncm_zeilen(s, name):
    e = einheit(s, name)
    c = karte(s, e["karte"])
    v = vof_gegen(s, e["karte"], e["seite"], ohne_minen=True)
    kand = []
    if v:
        kand.append((f"VOF {VOF_NAME.get(v[0], v[0])} from {','.join(v[2])}", v[1], v[0]))
    if e.get("mine_hit"):
        mw = min([x["wert"] for x in c.get("extern", []) if x["typ"] == "Mines"] or [-4])
        kand.append(("Mines! VOF (mine check lost)", mw, "Mines"))             # [RULE 7.9.1 p.54, 6.3.6]
    for sn, sz in s.get("sniper_ziele", {}).items():
        if sz == name and sn in s["einheiten"]:
            kand.append((f"Sniper VOF from {sn}", -3, "Sniper"))                     # [RULE 7.15 p.57]
    if e.get("grenade"):
        kand.append(("Grenade VOF (cumulative)", sum(e["grenade"]), "G"))
    if not kand and c.get("grenade_miss"):
        kand.append(("Grenade Miss als VOF", -1, "G"))
    if not kand:
        raise Verstoss(f"No VOF against {name} on {e['karte']} [3.7.4]")
    basis = min(kand, key=lambda x: x[1])
    # L61 [RULE 6.4 p.45 "When multiple VOF are affecting a card, take into account their value after modifiers ... Light levels (9.0)
    # and cover modifiers (5.3) may modify different weapons in different ways"; 5.2.3: Incoming takes the lower C&C value; K15]
    if v and v[0] in TERRAIN_WIE_INCOMING:
        tr = [x for x in vof_eintraege(s, e["karte"]) if x[3] in (None, e["seite"]) and x[0] != "Mines"]
        ext = [x for x in tr if x[0] in TERRAIN_WIE_INCOMING]
        dir_ = [x for x in tr if x[0] not in TERRAIN_WIE_INCOMING]
        if ext:
            bx = min(ext, key=lambda x: x[1])
            kand = [k for k in kand if not k[0].startswith("VOF ")] + [(f"VOF {VOF_NAME.get(bx[0], bx[0])} ({bx[2]})", bx[1], bx[0])]
        if dir_ and not s.get("_ncm_alt"):
            bd = min(dir_, key=lambda x: x[1])
            s["_ncm_alt"] = True
            try:
                alt_z = _ncm_direkt(s, e, c, (f"VOF {VOF_NAME.get(bd[0], bd[0])} from {','.join(x[2] for x in dir_)}", bd[1], bd[0]))
            finally:
                s.pop("_ncm_alt", None)
        else:
            alt_z = None
        basis = min(kand, key=lambda x: x[1])
    else:
        alt_z = None
    typ = basis[2]
    zeilen = [(basis[0], basis[1])]
    if c.get("grenade_miss") and basis[0] != "Grenade Miss als VOF":
        zeilen.append(("Grenade Miss", -1))
    if crossfire(s, e["karte"], e["seite"]):
        zeilen.append(("Crossfire (two PDF directions)", -1))
    for _ in range(e.get("cf", 0)):
        zeilen.append(("Concentrated Fire", -1))
    if typ in TERRAIN_WIE_INCOMING and c.get("cc2") is not None:
        zeilen.append((f"Terrain {c['terrain']} (lower value against {VOF_NAME.get(typ, typ)}) [5.2.3]", c["cc2"]))
    else:
        zeilen.append(cc_zeile(s, e))
    cv = cover_von(s, e)
    if cv:
        zeilen.append((f"Cover {cv['id']} {cv['typ']}", cv["wert"]))
    if pinned(e):
        zeilen.append(("Pinned", +1))
    if "Exposed" in e["status"]:
        zeilen.append(("Exposed", -2))
    if typ in TERRAIN_WIE_INCOMING and c.get("burst") is not None:
        zeilen.append(("Burst symbol", c["burst"]))     # [RULE 5.2.3 p.36, Charts 1: only Incoming and indirect mortar fire]
    rauch = [x.get("wert") or 0 for x in c.get("extern", []) if x["typ"] == "Smoke"]
    if rauch and typ not in ("Incoming", "AirStrike", "Mines", "G") and max(rauch):
        zeilen.append(("Smoke (best value)", max(rauch)))                           # [RULE 5.4 p.38]
    if cv and typ in ("Incoming", "AirStrike", "G"):
        st = sum(steps(s["einheiten"][m]) for m in auf(s, e["karte"], e["seite"]) if s["einheiten"][m].get("bereich") == cv["id"])
        if st > 3:
            zeilen.append((f"Stacking {st} steps under cover", -(st - 3)))
    sk = sicht_karte(s, e["karte"])
    if sk and typ not in ("Incoming", "AirStrike", "G", "Mines"):
        il = illum_wert(s, e["karte"])
        zeilen.append(("Visibility (ch. 9)" + (f", illumination {il:+d} included" if il is not None else ""), sk))   # [RULE 9.0 p.69]
    if alt_z is not None and sum(x[1] for x in alt_z) < sum(x[1] for x in zeilen):
        return alt_z
    return zeilen


def _ncm_direkt(s, e, c, basis):
    """L61: comparison value for direct fire alongside Incoming (6.4 'value after modifiers')."""
    typ = basis[2]
    z = [(basis[0], basis[1])]
    if c.get("grenade_miss"):
        z.append(("Grenade Miss", -1))
    if crossfire(s, e["karte"], e["seite"]):
        z.append(("Crossfire (two PDF directions)", -1))
    for _ in range(e.get("cf", 0)):
        z.append(("Concentrated Fire", -1))
    z.append(cc_zeile(s, e))
    cv = cover_von(s, e)
    if cv:
        z.append((f"Cover {cv['id']} {cv['typ']}", cv["wert"]))
    if pinned(e):
        z.append(("Pinned", +1))
    if "Exposed" in e["status"]:
        z.append(("Exposed", -2))
    rauch = [x.get("wert") or 0 for x in c.get("extern", []) if x["typ"] == "Smoke"]
    if rauch and max(rauch):
        z.append(("Smoke (best value)", max(rauch)))
    sk = sicht_karte(s, e["karte"])
    if sk:
        il = illum_wert(s, e["karte"])
        z.append(("Visibility (ch. 9)" + (f", Illumination {il:+d} included" if il is not None else ""), sk))
    return z


def cmd_ncm(s, args):
    name = args[0]
    if s["phase"] == "3.7.4" and name in s.get("kampf_ncm", {}):
        zeilen = [tuple(z) for z in s["kampf_ncm"][name]]       # state on entering 3.7.4 [RULE 3.7.4 p.17]
    else:
        zeilen = ncm_zeilen(s, name)
    roh = sum(v for _, v in zeilen)
    ncm = max(-4, min(6, roh))
    print(f"NCM {name}:")
    for t, v in zeilen:
        print(f"- {t}: {v:+d}")
    print(f"- Total {roh:+d}" + (f", capped at {ncm:+d}" if ncm != roh else "") + "  [RULE 6.4 p.45, Charts & Tables 1]")
    print(f"Draw an Action card, Combat Resolution at {ncm:+d}: HIT, PIN or MISS. Then fof.py hit \"{name}\" <HIT|PIN|MISS> [effect letters under {erfahrung(s['einheiten'][name])}]")


LAT_WERTE = {"Assault Team": ("A", "P"), "Fire Team": ("S", "C"), "Litter Team": (None, "C"), "Paralyzed Team": (None, "C")}   # Normandy Unit Breakdown p.47: Assault TM A/P, Fire Team S/C


def lat_werte_setzen(e, lat):
    e["vof_rating"], e["reichweite"] = LAT_WERTE[lat]


def lat_neu(e, lat, herkunft):
    return {"typ": lat, "seite": e["seite"], "platoon": e.get("platoon"), "erfahrung": LAT_ERFAHRUNG[lat], "karte": e["karte"],
            "bereich": e.get("bereich", "offen"), "status": ["Pinned"], "steps": 1, "herkunft": herkunft, "ziel": None,
            "vof_rating": LAT_WERTE[lat][0], "reichweite": LAT_WERTE[lat][1], "spotted": e.get("spotted", True),
            "typname": lat, **({"deep_bunker": e["deep_bunker"]} if e.get("deep_bunker") else {})}     # [CSR 5 p.14] LATs in a Deep Bunker also have no VOF


def casualty(s, e, prot, name):
    c = karte(s, e["karte"])
    key = "casualties" if e["seite"] == "US" else "casualties_feind"
    c[key] = c.get(key, 0) + 1
    if e["seite"] == "US" and v4(s):
        s["us_casualties_gesamt"] = s.get("us_casualties_gesamt", 0) + 1          # [RULE 12.4 p.81] all casualties of the mission
    prot.append(f"{name}: one step becomes a Casualty, Casualty marker on {e['karte']} [6.4.3]")


def assets_abgeben(s, e, name, prot, als_casualty=False, nachfolger=None):
    """Carried casualties and radios: [RULE 6.4.3 p.47] onto the card at the last step (5.1.6E);
    [RULE 4.3.5 p.30] casualty of the last step: radio destroyed on R# 1/2; LAT conversion per option U7."""
    c = karte(s, e["karte"])
    if e.get("traegt_casualties"):
        c["casualties"] = c.get("casualties", 0) + e["traegt_casualties"]
        prot.append(f"{name}: drop carried casualties ({e['traegt_casualties']}) on {e['karte']} [5.1.6E p.33, 6.4.3 p.47]")
        e["traegt_casualties"] = 0
    if e.get("leitungen"):
        c["leitung_assets"] = c.get("leitung_assets", 0) + e["leitungen"]
        prot.append(f"{name}: {e['leitungen']} Phone Line(s) remain as an asset on {e['karte']} (BGG D3)")
        e["leitungen"] = 0
    if e.get("traegt_munition"):
        prot.append(f"{name}: carried ammo is lost (BGG C6)")
        e.pop("traegt_munition")
    if e.get("assets"):                                                 # [RULE 5.1.6E p.33, 6.4.3 p.47] assets drop onto the card
        c.setdefault("assets_boden", []).extend(e["assets"])
        prot.append(f"{name}: Assets {', '.join(e['assets'])} lie on {e['karte']} (Pick Up 4.2.2h) [5.1.6E p.33]")
        e["assets"] = []
    gs = geraete(e)
    if not gs:
        return
    if nachfolger and not als_casualty and ("optionen" not in s or opt(s, "U7_lat_behaelt_funk")):
        s["einheiten"][nachfolger]["funk"] = [dict(g) for g in gs]
        prot.append(f"{nachfolger} keeps {', '.join(g['typ'] for g in gs)} (cannot give orders as a LAT){offen(s, 'U7_lat_behaelt_funk')} [5.1.6E p.33]")
    else:
        for g in gs:
            c.setdefault("assets", []).append({"typ": g["typ"], "netz": g["netz"], "schaden_offen": bool(als_casualty)})
        prot.append(f"{', '.join(g['typ'] + ' ' + g['netz'] for g in gs)} from {name} on {e['karte']}" + (": draw R# 1/2, destroyed on 1 (fof.py radio damage <card> <device> intact|destroyed) [RULE 4.3.5 p.30]" if als_casualty else f" dropped{offen(s, 'U7_lat_behaelt_funk')} [5.1.6E p.33]"))
    e["funk"] = []


def entfernen_rfp(s, name, prot, grund, als_casualty=False, nachfolger=None):
    e = s["einheiten"][name]
    if ist_hq(e) and e["seite"] == "US":
        s.setdefault("rfp_daten", {})[name] = {k: e.get(k) for k in ("ebene", "platoon", "ft_vof")}   # for 6.5.2
    assets_abgeben(s, e, name, prot, als_casualty, nachfolger)
    munition_verloren(e, name, prot)
    del s["einheiten"][name]
    s.setdefault("removed_from_play", []).append(name)
    if name in s["kommandos"]:
        s["kommandos"][name]["gespart"] = 0
    if e["seite"] == "Feind":
        pk = s.get("pakete", {}).get(str(e.get("paket")))
        if pk:
            pk["im_spiel"] = False
    prot.append(f"{name}: {grund}, Removed from Play [1.2.6, 6.4.3]")


def einheit_reduzieren(s, name, code, prot):
    """6.4.3: one letter applied to one step."""
    e = s["einheiten"][name]
    lat = LAT_TYPEN[code]
    if ist_lat(e):
        if e["typ"] == lat:
            markieren(e, "Pinned")
            prot.append(f"{name} is already {lat}: Pinned only [6.4.3]")
        elif code == "C":
            casualty(s, e, prot, name)
            assets_abgeben(s, e, name, prot, als_casualty=True)
            del s["einheiten"][name]
            prot.append(f"{name} ({e['typ']}) becomes a Casualty, remove counter")
        else:
            e["typ"], e["erfahrung"] = lat, LAT_ERFAHRUNG[lat]
            e["vof_rating"] = "S" if lat in ("Fire Team", "Assault Team") else None
            if e["vof_rating"] is None:
                e["ziel"] = None
            markieren(e, "Pinned")
            prot.append(f"{name} becomes {lat} (swap counter), Pinned [6.4.3]")
        return
    if ft_seite(e):
        if code in ("F", "A"):
            markieren(e, "Pinned")
            prot.append(f"{name} (named Fire Team): no further effect, Pinned [6.4.3]")
        elif code == "C":
            casualty(s, e, prot, name)
            entfernen_rfp(s, name, prot, "Casualty", als_casualty=True)
        else:
            neu = neuer_name(s, lat)
            s["einheiten"][neu] = lat_neu(e, lat, name)
            prot.append(f"{name} becomes {lat} ({neu})")
            entfernen_rfp(s, name, prot, "Fire Team side converted", nachfolger=neu)
        return
    if steps(e) == 1:
        if code in ("F", "A") and e.get("fire_team_seite"):
            markieren(e, "Fire Team side")
            markieren(e, "Pinned")
            prot.append(f"{name}: flip to the Fire Team side (VOF {e.get('ft_vof', 'S')}), Pinned" + ("; saved Commands remain, orders only itself, cannot be activated [4.1.4]" if ist_hq(e) else "") + " [6.4.3]")
            return
        neu = None
        if code == "C":
            casualty(s, e, prot, name)
        else:
            neu = neuer_name(s, lat)
            s["einheiten"][neu] = lat_neu(e, lat, name)
            prot.append(f"{name}: step becomes {lat} ({neu}) on {e['karte']}, Pinned")
        entfernen_rfp(s, name, prot, "last step converted", als_casualty=(code == "C"), nachfolger=neu)
        return
    if code in ("F", "A") and e.get("breakdown") == "mtr_sec" and v4(s):
        # [CSR 2 p.13, Normandy p.47] F/A hit on the Mortar Section: the step becomes a named 1-step Mortar Team (Fire Team side)
        tn = mtr_team_name(s, ("1/Mtr", "2/Mtr", "3/Mtr"))
        te = mtr_team(s, e, tn)
        te["status"] = ["Fire Team side", "Pinned"]
        s["einheiten"][tn] = te
        prot.append(f"{name}: one step becomes {tn} on the Fire Team side (S • C), Pinned, with the same ammo ({(e.get('munition') or {}).get('punkte')}) [CSR 2 p.13, 7.18.1B p.60]")
    elif code in ("F", "A") and e.get("breakdown") == "mtr_sec_de" and steps(e) == 2:
        # [CSR 4 p.14, Normandy p.48] last two steps: 1/81mm Mtr (Fire Team side) and 2/81mm Mtr, full ammo
        te = mtr_team_de(s, e, "1/81mm Mtr")
        te["status"] = ["Fire Team side", "Pinned"]
        s["einheiten"][neuer_name(s, "1/81mm Mtr")] = te
        prot.append(f"{name}: one step becomes 1/81mm Mtr on the Fire Team side (S • C), Pinned, ammo {(e.get('munition') or {}).get('punkte')} [CSR 4 p.14, Normandy p.48]")
    elif code == "C":
        casualty(s, e, prot, name)
    else:
        neu = neuer_name(s, lat)
        s["einheiten"][neu] = lat_neu(e, lat, name)
        if code == "F" and e.get("fj_breakdown") and steps(e) == 2 and e.get("vof_rating") == "A":
            fj = s.get("_fj_r")
            if fj not in ("1", "2"):
                raise Verstoss(f"{name}: F hit on the second step of an A-rated Fallschirmjaeger squad: draw an Action card, R# column 2: --fj=1 (two A Fire Teams) or --fj=2 (S and A) [CSR 3 p.14, Normandy p.48]")
            if fj == "1":
                s["einheiten"][neu].update(vof_rating="A", reichweite="C")
                if e.get("munition"):
                    m = e["munition"]
                    halb = m.get("punkte", 0) // 2
                    s["einheiten"][neu]["munition"] = dict(m, punkte=halb)
                    m["punkte"] = m.get("punkte", 0) - halb
                    prot.append(f"{neu}: A • C with {halb} MG ammo, remaining {m['punkte']} with the last team (rounded up for the second team, 7.18.1B)")
                prot.append("FJ R#1/2: two A-rated Fire Teams [CSR 3 p.14]")
            else:
                prot.append("FJ R#2/2: one S-rated and one A-rated Fire Team [CSR 3 p.14]")
        prot.append(f"{name}: one step becomes {lat} ({neu}) on {e['karte']}, Pinned"
                    + (offen(s, "U27_mtr_sec_nicht_fa") if e.get("breakdown") == "mtr_sec" else ""))
    e["steps"] = steps(e) - 1
    prot.append(f"{name}: flip to {e['steps']} steps")


def mtr_team_name(s, reihenfolge):
    for tn in reihenfolge:
        if tn not in s["einheiten"] and tn not in s.get("removed_from_play", []):
            return tn
    return neuer_name(s, "Mtr Team")


def mtr_team(s, sek, tn):
    """1-step Mortar Team from the Section: values from the setup data (CSR 2), ammo as the Section (7.18.1B)."""
    te = copy.deepcopy(s.get("aufbau_einheiten", {}).get(tn) or s.get("reserve_einheiten", {}).get("1/Mtr", {}))
    te.update(karte=sek["karte"], bereich=sek.get("bereich", "offen"), platoon=sek.get("platoon"), attached_an=list(sek.get("attached_an", [])),
              ziel=None, steps=1, seite="US", erfahrung=sek.get("erfahrung", "Line"))
    te.setdefault("typ", "Weapons Team")
    te["funk"] = []
    if sek.get("munition"):
        te["munition"] = copy.deepcopy(sek["munition"])
    return te


def mtr_team_de(s, sek, tn):
    """[CSR 4 p.14, Normandy p.48] German 81mm Mortar Team from the Section, full ammo of the Section."""
    te = copy.deepcopy(s.get("mtr_team_de", {}).get(tn, {}))
    te.update(karte=sek["karte"], bereich=sek.get("bereich", "offen"), ziel=None, steps=1, seite="Feind", erfahrung=sek.get("erfahrung", "Line"),
              spotted=sek.get("spotted", True), typname=tn, paket=sek.get("paket"), pc_herkunft=sek.get("pc_herkunft"))
    te.setdefault("typ", "Weapons Team")
    te.setdefault("status", [])
    if sek.get("munition"):
        te["munition"] = copy.deepcopy(sek["munition"])
    return te


def cmd_treffer(s, args):
    fjo = [a for a in args if a.startswith("--fj=")]
    args = [a for a in args if not a.startswith("--fj=")]
    s["_fj_r"] = fjo[0].split("=", 1)[1] if fjo else None
    name, erg = args[0], args[1].upper()
    effekt = args[2].upper() if len(args) > 2 else ""
    e = einheit(s, name)
    prot = []
    if erg == "MISS":
        if pinned(e):
            e["status"].remove("Pinned")
            prot.append(f"{name}: MISS, remove Pinned marker [6.4.2A]")
        else:
            prot.append(f"{name}: no effect")
    elif erg == "PIN":
        markieren(e, "Pinned")
        prot.append(f"{name} Pinned" + (" (its VOF becomes 'All Pinned' +2, adjust marker in 3.8)" if feuert(e) else ""))
    elif erg == "HIT":
        if not effekt:
            raise Verstoss(f"HIT: draw a second Action card, read Hit Effects under {erfahrung(e)} and give the letters [RULE 6.4.3 p.47]")
        codes = list(effekt[:1]) if steps(e) == 1 else list(effekt[:2])
        if e.get("breakdown_hinweis") and any(c in "FA" for c in codes):
            prot.append(f"{name}: {e['breakdown_hinweis']} [6.4.3 p.47]")
        for code in codes:
            if code not in LAT_TYPEN:
                raise Verstoss(f"Unknown effect {code} (C P L F A)")
            if name in s["einheiten"]:
                einheit_reduzieren(s, name, code, prot)
        if name in s["einheiten"]:
            e = s["einheiten"][name]
            if steps(e) == 1 and e.get("breakdown") == "mtr_sec_de":
                te = mtr_team_de(s, e, "2/81mm Mtr")
                te["status"] = ["Pinned"]
                tn = neuer_name(s, "2/81mm Mtr")
                s["einheiten"][tn] = te
                entfernen_rfp(s, name, prot, f"last step becomes {tn} (G! • C-V, ammo {(te.get('munition') or {}).get('punkte')}) [CSR 4 p.14, Normandy p.48]", nachfolger=tn)
            elif steps(e) == 1 and e.get("breakdown") == "mtr_sec" and v4(s):
                # [CSR 2 p.13] 'If only one step remains, place a 1-step mortar team'
                tn = mtr_team_name(s, ("3/Mtr", "2/Mtr", "1/Mtr"))
                te = mtr_team(s, e, tn)
                te["status"] = ["Pinned"]
                te["funk"] = [dict(g) for g in geraete(e)]
                e["funk"] = []
                s["einheiten"][tn] = te
                entfernen_rfp(s, name, prot, f"last step becomes 1-step Mortar Team {tn} (G! • C-L, ammo {(te.get('munition') or {}).get('punkte')}) [CSR 2 p.13]")
            elif steps(e) == 1 and e.get("letzter_step") and not ist_lat(e):
                lat2 = e["letzter_step"]
                neu2 = neuer_name(s, lat2)
                s["einheiten"][neu2] = lat_neu(e, lat2, name)
                if e.get("letzter_step_werte"):
                    s["einheiten"][neu2].update(e["letzter_step_werte"])                # Normandy p.48: A squad ends as an A-rated Fire Team
                    if e.get("munition"):
                        s["einheiten"][neu2]["munition"] = copy.deepcopy(e["munition"])
                    prot.append(f"{neu2}: {' • '.join(str(v) for v in e['letzter_step_werte'].values()) if isinstance(e['letzter_step_werte'], dict) else e['letzter_step_werte']} with the remaining ammo [Normandy p.48, 7.18.1B]")
                entfernen_rfp(s, name, prot, f"no 1-step side, last step becomes a generic {lat2} ({neu2}); can be reconstituted from 2-3 teams [6.4.3 p.47, FM1 p.31]", nachfolger=neu2)
            else:
                markieren(e, "Pinned")
                prot.append(f"{name} Pinned (every HIT pins) [6.4.3]")
    else:
        raise Verstoss("Result must be HIT, PIN or MISS")
    if s.get("kampf_offen") and name in s["kampf_offen"]:
        s["kampf_offen"].remove(name)
    s.pop("_fj_r", None)
    speichern(s, f"Combat Effects {name}: {erg} {effekt}; " + "; ".join(prot), "6.4.2 p.47, 6.4.3 p.47")
    ausgabe(prot, s)
    if s.get("kampf_offen"):
        print("Still open: " + ", ".join(s["kampf_offen"]))


# ---------------------------------------------------------------- End of turn (3.8)
def rundenende_v4(s, prot):
    """Clean Up (3.8) for the v4 elements: mines, snipers, ammo, G! PDF, Place-VOF-No, events, Checking Up, counterattack."""
    for n, e in list(s["einheiten"].items()):
        if e.pop("mine_hit", None):
            prot.append(f"{n}: remove from the Mine marker [3.8 p.17]")
        if e.get("munition_leer"):
            out_of_ammo(s, n, e, prot)
        if e.pop("nur_pdf", None):
            e["ziel"] = None
            prot.append(f"{n}: remove the Grenade Attack PDF [7.3.2 p.53]")
        if e.pop("kein_feuer_bis_clean_up", None):
            prot.append(f"{n} may now open fire (Place PDF/VOF No) [8.3 p.63]")
        if e.get("bis_zug") == s["zug"] and e.get("ebene") == "BN":
            del s["einheiten"][n]
            s["kommandos"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; BN HQ off-map again [Normandy M1 p.18]")
    for kid, c in s["karten"].items():
        for x in c.get("extern", []):
            if x["typ"] == "Mines" and x.get("aktiv"):
                x["aktiv"] = False
                prot.append(f"{kid}: Mine marker back to the Draw 3 side [3.8 p.17]")
        if c.pop("pyro", None):
            prot.append(f"{kid}: remove pyrotechnics [3.8 p.17]")
    for k in ("sniper_ziele", "sniper_offen", "ereignis_einheiten", "rally_offen", "leitung_checks", "ereignis_pflicht", "ereignis_flanke",
              "fm_gesperrt", "bn_nicht_verfuegbar", "ereignis_munition"):
        s.pop(k, None)
    ga = s.get("gegenangriff")
    if ga and ga.get("bis_zug") == s["zug"]:
        s["feind_taktik"] = ga.get("taktik_vorher") or s.get("feind_taktik")
        s.pop("gegenangriff")
        prot.append(f"Counterattack ends: enemy tactic back to {s['feind_taktik']} [Normandy M1 MSR 1 p.19]")


def cmd_rundenende(s, args):
    if s["phase"] != "3.8":
        raise Verstoss(f"End of turn only in phase 3.8, currently {s['phase']} [RULE 3.8 p.17]")
    prot = []
    for n, e in s["einheiten"].items():
        for m in ("Exposed", "Moved", "Fired"):
            if m in e["status"]:
                e["status"].remove(m)
                prot.append(f"{n}: remove {m}")
        if e.get("cf"):
            e["cf"] = 0
            prot.append(f"{n}: remove Concentrated Fire")
        if e.get("grenade"):
            e["grenade"] = []
            prot.append(f"{n}: remove Grenade VOF")
        e.pop("konzentriert", None)
    for kid, c in s["karten"].items():
        if c.get("illum"):
            c["illum"] = []
            prot.append(f"{kid}: remove Illumination marker [RULE 9.2 p.70]")
        if c.get("grenade_miss"):
            c["grenade_miss"] = False
            prot.append(f"{kid}: remove Grenade Miss")
        for x in list(c.get("extern", [])):
            if x["typ"] == "Smoke":
                c["extern"].remove(x)
                prot.append(f"{kid}: remove Smoke/Pyro")
            if x["typ"] == "Incoming":
                prot.append(f"{kid}: Incoming stays until 3.7.1 of the next turn (blocks LOS)")
            if x["typ"] == "Indirect":
                c["extern"].remove(x)
                prot.append(f"{kid}: remove Heavy Weapons VOF (Indirect Lay from {x.get('quelle')}) [RULE 7.3.2 p.53]")
        if s.get("ccp") == kid and c.get("casualties"):
            s["evakuiert"] = s.get("evakuiert", 0) + c["casualties"]
            prot.append(f"{kid}: {c['casualties']} casualties evacuated at the CCP, markers to the Holding Box [RULE 3.8 p.17, 5.1.7 p.34]")
            xp_buchen(s, c["casualties"] * (xp_tab(s, "evakuiert") or 1), f"{c['casualties']} casualties evacuated ({kid})", prot)
            c["casualties"] = 0
        if s["typ"] == "defensiv" and c.get("pc") and not auf(s, kid, "US"):
            c["pc"] = None
            prot.append(f"{kid}: unresolved PC marker removed (defensive mission)")
    for n, e in s["einheiten"].items():
        if e.get("indirekt"):
            e.pop("indirekt")
    if s.get("wetter_nur_zug"):
        s["wetter"] = 0
        s.pop("wetter_nur_zug")
        sicht_aktualisieren(s)
        prot.append("Remove Rain marker, weather back to +0 [Event It's Raining]")
    if v4(s):
        rundenende_v4(s, prot)
    los_verlust_cease(s, prot)
    feind_cease_fire(s, prot)
    # [RULE 3.8 p.17] 'Adjust VOF, PDF and Activity Levels resulting from the Combat Effects Segment and Clean Up';
    # e.g. mortars after removing Exposed [FM1 p.44]
    feuer_eroeffnen(s, prot)
    for n, k in s["kommandos"].items():
        k["aktiviert"], k["fertig"], k["verfuegbar"] = False, False, 0
        k.pop("gezogen", None)
    s["impuls_ausgegeben"] = {}
    s["kampf_offen"] = []
    s["letzter_versuch"] = None
    s.pop("kampf_ncm", None)
    s.pop("exhort_frei", None)
    prot.append("Command markers from the Saved zone to the Tracking zone (value stays), Zero Commands marker to the Holding Box [4.1.1]")
    prot.append("Check VOF markers on the board against the briefing: pinned shooters 'All Pinned' +2, unpinned back to Basic VOF [3.8, 4.2.5]")
    if s["zug"] >= s["max_zuege"] and v4(s):
        missionsende_v4(s, prot)
        speichern(s, f"Turn {s['zug']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17, 3.9 p.17")
        print("End of mission: last turn played.")
        ausgabe(prot, s)
        return
    if s["zug"] >= s["max_zuege"]:
        if s.get("ziel_regeln"):
            prot.append("Objective status: " + ziel_stand(s))
            if "optionen" in s:
                prot.append(("Reattempt per 3.9 provided for by option U9" if opt(s, "U9_reattempt") else "no Reattempt (FM1 names none)") + offen(s, "U9_reattempt") + " [RULE 3.9 p.17]")
        speichern(s, f"Turn {s['zug']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17")
        print("End of mission: last turn played.")
        ausgabe(prot, s)
        return
    s["zug"] += 1
    s["phase"] = sop(s)[0][0]
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, f"Clean Up; turn {s['zug']} begins; " + "; ".join(prot), "3.8 p.17")
    print(f"Turn {s['zug']} begins with phase {s['phase']} {phase_name(s)}.")
    ausgabe(prot, s)


# ================================================================ v4: Normandy campaign
# All functions in this section apply only if the setup data has the matching fields (kampagne, ereignistabellen,
# munition, terrain_katalog, ziele ...). FM1 games (run3, cac_run3) do not have them and run unchanged.

def v4(s):
    return "kampagne" in s


def in_aufstellung(s):
    """Before the first 'phase next' (turn 1, phase 3.1) or during Reattempt preparation (3.9)."""
    return (s["zug"] == 1 and s["phase"] == sop(s)[0][0] and not s.get("aufstellung_fertig")) or bool(s.get("reattempt_setup"))


def cm_zahl(s, name):
    """Countermix count; if missing (null in the setup data = UNVERIFIED), 1 is assumed and reported."""
    v = s.get("countermix", {}).get(name, 1)
    if v is None:
        s.setdefault("_hinweise", []).append(f"Countermix {name}: count not recorded (UNVERIFIED), 1 assumed")
        return 1
    return v


def karten_id(r, c):
    return f"{r}{c}" if 0 <= c <= 9 else f"{r}m{abs(c)}"


def us_front(s):
    """Row of the foremost US unit (Staging = row 1)."""
    rs = [karte(s, e["karte"])["reihe"] for e in s["einheiten"].values() if e["seite"] == "US" and e.get("karte") in s["karten"]]
    return max(rs) if rs else 1


def oberste_reihe(s):
    return max(c["reihe"] for c in s["karten"].values() if not c.get("ausserhalb"))


def xp_buchen(s, punkte, grund, prot=None):
    """[RULE 12.1 p.80] Experience Points of the mission; table Normandy p.13."""
    if not v4(s) or not punkte:
        return
    s.setdefault("xp", []).append({"zug": s["zug"], "versuch": s["kampagne"].get("versuch", 1), "punkte": punkte, "grund": grund})
    if prot is not None:
        summe = sum(x['punkte'] for x in s['xp'])
        if punkte < 0:   # L54: spending between patrols/missions
            prot.append(f"Experience {punkte} spent: {grund} (remaining {summe}) [12.3 p.81]")
        else:
            prot.append(f"Experience +{punkte}: {grund} (total {summe}) [12.1 p.80, Normandy p.13]")


def xp_tab(s, key):
    return s.get("kampagne", {}).get("xp_tabelle", {}).get(key, 0)


# ---------------------------------------------------------------- Terrain, map extension (2.2.1, 8.4.5)
def raender_parse(txt):
    if not txt:
        return None
    if txt in ("weiss", "gruen"):
        return txt
    r = {}
    for teil in txt.split(","):
        k, v = teil.split(":")
        if k not in ("oben", "unten", "links", "rechts", "diagonal") or v not in ("weiss", "gruen"):
            raise Verstoss("--edges=oben:weiss|gruen,unten:..,links:..,rechts:..,diagonal:.. (oben = toward the enemy)")
        r[k] = v
    for k in ("oben", "unten", "links", "rechts", "diagonal"):
        r.setdefault(k, "gruen")
    return r


def terrain_setzen(s, kid, typ, o):
    kat = s.get("terrain_katalog", {})
    if typ not in kat:
        raise Verstoss(f"Terrain type '{typ}' not in the catalog: {', '.join(k for k in kat if k != 'Hill')}; unknown types with all values: --typ-neu=ja --cc=.. --cover_max=.. --cover_draw=.. --edges=..")
    c = karte(s, kid)
    w = {k: v for k, v in kat[typ].items() if k not in ("quelle",)}
    c["terrain"] = typ
    for k in ("cc", "cc2", "burst", "cover_max", "cover_draw", "raender", "fahrzeuge", "moerser_verbot", "urban", "gebaeude_tabelle", "op"):
        if k in w:
            c[k] = w[k]
    for k in ("cc", "cc2", "burst", "cover_max", "cover_draw"):
        if o.get("--" + k) is not None:
            c[k] = int(o["--" + k])
    if o.get("--raender"):
        c["raender"] = raender_parse(o["--raender"])
    if o.get("--nr"):
        c["kartennummer"] = o["--nr"]
    hills = int(o.get("--hill", 0))
    c["elevation"] = 1 + hills                                                  # [RULE 2.2.1 p.9, 5.2.2A p.35] each Hill card +1
    if hills:
        c["terrain"] = f"{typ} on {hills} Hill"
        if isinstance(c.get("raender"), str) or c.get("raender") is None:
            c["raender"] = "gruen"                                              # E9: Hill cards have dark edges
    fehlt = [k for k in ("cc", "cover_max", "cover_draw", "raender") if c.get(k) is None]
    if fehlt:
        raise Verstoss(f"{typ}: values not recorded ({', '.join(fehlt)}); read them from the board and give them with --{' --'.join(fehlt)} (UNVERIFIED in the catalog)")
    if "UNVERIFIZIERT" in kat[typ].get("quelle", ""):
        s.setdefault("_hinweise", []).append(f"{typ}: catalog values partly UNVERIFIED ({kat[typ]['quelle']}); check on the board")
    c.pop("hinweis", None)


def cmd_terrain(s, args):
    """[RULE 2.2.1 p.9] Enter a randomly drawn terrain card: before turn 1 for all cards, later only for cards without terrain."""
    if len(args) < 2:
        raise Verstoss("terrain <card> <type> [--no=<card number>] [--hill=n] [--edges=..] [--cc=..]")
    kid, typ = args[0], args[1]
    o = opts_parse(args[2:])
    c = karte(s, kid)
    if c.get("staging"):
        raise Verstoss("Staging cards stay face down (2.2.1)")
    if c.get("terrain") and not in_aufstellung(s):
        raise Verstoss(f"{kid} already has terrain ({c['terrain']}); change only before turn 1")
    terrain_setzen(s, kid, typ, o)
    rt = c["raender"] if isinstance(c["raender"], str) else ", ".join(f"{a} {b}" for a, b in c["raender"].items())
    prot = [f"{kid}: {c['terrain']} (C&C +{c['cc']}" + (f"/+{c['cc2']}" if c.get("cc2") is not None else "") + f", Cover {c['cover_max']}/{c['cover_draw']}, edges {rt}"
            + (f", Elevation {c['elevation']}" if c.get("elevation", 1) > 1 else "") + ")"]
    speichern(s, "Terrain: " + prot[0], "2.2.1 p.9")
    ausgabe(prot, s)


def cmd_erweitern(s, args):
    """[RULE 8.4.5 p.65] Create a card for placing an enemy package; outside the mission boundaries it is off-limits to US (2.4.1)."""
    if len(args) < 3:
        raise Verstoss("extend <row> <column> <type> [--hill=n] [--edges=..] [--no=..]")
    r, c, typ = int(args[0]), int(args[1]), args[2]
    o = opts_parse(args[3:])
    kid = karten_id(r, c)
    if kid in s["karten"] or karte_bei(s, r, c):
        raise Verstoss(f"Card at row {r} column {c} already exists")
    if r <= 1:
        raise Verstoss("No extension behind the Staging Area")
    if not any(abs(v["reihe"] - r) <= 1 and abs(v["spalte"] - c) <= 1 for v in s["karten"].values()):
        raise Verstoss("Extension only adjacent to existing cards")
    spalten = [v["spalte"] for v in s["karten"].values() if not v.get("ausserhalb")]
    aus = r > oberste_reihe(s) or c < min(spalten) or c > max(spalten)
    s["karten"][kid] = {"terrain": None, "reihe": r, "spalte": c, "cover": [], "extern": [], "ausserhalb": aus}
    try:
        terrain_setzen(s, kid, typ, o)
    except Verstoss:
        del s["karten"][kid]
        raise
    prot = [f"Card {kid} (row {r}, column {c}) created: {s['karten'][kid]['terrain']}" + (", outside the mission boundaries: off-limits to friendly units [2.4.1, 8.4.5]" if aus else "")]
    speichern(s, "; ".join(prot), "8.4.5 p.65")
    ausgabe(prot, s)


# ---------------------------------------------------------------- Normandy setup (Tactical Controls, values, assets)
def cmd_ziel(s, args):
    """[RULE 2.4.1 p.10, Normandy M1 p.16] Primary/Secondary on row 3 (tool 4), Attack Position on row 2 (tool 3) next to an
    Objective; CCP anywhere before the mission starts (Normandy p.13, 5.1.7); Phase Lines between rows."""
    if not v4(s):
        raise Verstoss("Tactical Controls only in campaign missions")
    if not in_aufstellung(s):
        raise Verstoss("Tactical Controls only before turn 1; later only CCP via 4.2.1l [RULE 2.4.1 p.10]")
    z = s.setdefault("ziele", {})
    art = args[0]
    prot = []
    if art == "phaseline":
        n, reihe = args[1], int(args[2])
        z.setdefault("phaselines", {})[n] = reihe
        prot.append(f"Phase Line {n} between row {reihe} and {reihe + 1}")
    elif art == "route":
        nr, kid = int(args[1]), args[2]
        c = karte(s, kid)
        if not s.get("patrouille_mission") or nr not in (1, 2, 3, 4) or not 2 <= c["reihe"] <= oberste_reihe(s) or c.get("ausserhalb"):
            raise Verstoss("objective route <1-4> <card in rows 2-4> (Combat Patrol) [Normandy M3 MSR 2]")
        r = z.setdefault("route", {})
        if kid in [v for k_, v in r.items() if int(k_) != nr]:
            raise Verstoss("Route Points on four different cards [MSR 2]")
        r[str(nr)] = kid
        prot.append(f"Route Point {nr} on {kid}; enter in order 1-4, remove the marker on entering [MSR 2]")
    elif art == "konzentration":
        # L56: Artillery Concentration before the mission starts or before each patrol (7.16.5, Normandy M3 p.24)
        if len(args) < 3:
            raise Verstoss("objective concentration <card> <fire asset, e.g. '105mm HE'> [RULE 7.16.5 p.59]")
        kid, ag = args[1], " ".join(args[2:])
        karte(s, kid)
        if ag not in (s.get("fm_werte") or {}):
            raise Verstoss(f"Unknown fire asset: {ag}; available: {', '.join(s.get('fm_werte', {}))}")
        s.setdefault("target_marker", {})[tm_schluessel(s, ag)] = kid
        s["konzentration_gesetzt"] = True
        prot.append(f"Artillery Concentration: Target marker {tm_schluessel(s, ag)} on {kid}; Call for Fire of this fire asset on {kid} +1 card [RULE 7.16.5 p.59, Normandy M3 p.24]")
    else:
        kid = args[1]
        c = karte(s, kid)
        top = oberste_reihe(s)
        if art in ("primaer", "sekundaer"):
            if c["reihe"] != top or c.get("staging"):
                raise Verstoss(f"Primary/Secondary only on the top mission row (tool row {top}) [Normandy M1 p.16, M2 p.20]")
            ander = z.get("sekundaer" if art == "primaer" else "primaer")
            if ander == kid:
                raise Verstoss("Primary and Secondary on different cards")
        elif art == "ap":
            if c["reihe"] != top - 1:
                raise Verstoss(f"Attack Position on the second-to-last mission row (tool row {top - 1}) [Normandy M1 p.16, M2 p.20]")
            objs = [z.get("primaer"), z.get("sekundaer")]
            if not any(o_ and benachbart(s, kid, o_) for o_ in objs):
                raise Verstoss("Attack Position must be adjacent to Primary or Secondary; place the Objectives first [Normandy M1 p.16]")
        elif art == "ccp":
            s["ccp"] = kid
        elif art == "cop":
            if c["reihe"] != 2 or not s.get("patrouille_mission"):
                raise Verstoss("Combat Outpost on a card in row 2 (Combat Patrol mission) [Normandy M3 p.24, 2.6.1]")
            if c.get("pc"):
                c["pc"] = None
                s.get("pc_start", {}).pop(kid, None)
                prot.append(f"PC marker removed from {kid} (no PC on the COP) [Normandy M3 p.24, 2.6.1]")
            n_fh = sum(1 for cv in c.get("cover", []) if cv["typ"] == "Foxholes")
            for _ in range(max(0, 2 - n_fh)):
                prot.append(f"Foxholes marker {neuer_cover(s, kid, 'Foxholes', 1)} (+1) on {kid}")
        else:
            raise Verstoss("objective primary|secondary|ap|ccp|cop <card> | objective route <1-4> <card> | objective phaseline <n> <row>")
        if art != "ccp":
            z[art] = kid
        prot.append(f"{ {'primaer': 'Primary Objective', 'sekundaer': 'Secondary Objective', 'ap': 'Attack Position', 'ccp': 'Casualty Collection Point', 'cop': 'Combat Outpost'}[art]} on {kid}")
    speichern(s, "Tactical Control: " + "; ".join(prot), "2.4.1 p.10")
    ausgabe(prot, s)


WERTE_FELDER = ("vof_rating", "reichweite", "ft_vof", "ft_reichweite", "erfahrung", "steps")


def cmd_werte(s, args):
    """Enter unverified counter values from the components (setup only). Every entry is logged."""
    if not in_aufstellung(s):
        raise Verstoss("Enter counter values only before turn 1 or during Reattempt preparation")
    n = args[0]
    e = einheit(s, n)
    prot = []
    for a in args[1:]:
        k, v = a.split("=", 1)
        if k not in WERTE_FELDER:
            raise Verstoss(f"Field {k} cannot be changed; allowed: {', '.join(WERTE_FELDER)}")
        v2 = None if v in ("null", "-") else (int(v) if k == "steps" else v)
        e[k] = v2
        prot.append(f"{n}: {k} = {v2} (from the counter)")
    speichern(s, "; ".join(prot), None)
    ausgabe(prot, s)


def aufstellen_v4(s, n, e, o, prot):
    """Extra options of 'setup' for the campaign (CSR 1, CSR 2, 2.3.4, 4.4.1)."""
    if "--netz" in o:
        if n != s.get("co_hq"):
            raise Verstoss("give --net with the CO HQ: setup \"CO HQ\" --net=radio|phone")
        if o["--netz"] not in ("funk", "telefon"):
            raise Verstoss("--net=radio|phone")
        alt = s.get("co_tac_mittel")
        s["co_tac_mittel"] = o["--netz"]
        typ_neu, typ_alt = ("EE8", "SCR536") if o["--netz"] == "telefon" else ("SCR536", "EE8")
        for m, x in s["einheiten"].items():
            for g in x.get("funk", []):
                if g["netz"] == "CO TAC" and g["typ"] == typ_alt:
                    g["typ"] = typ_neu
        if o["--netz"] == "telefon":
            s["leitungen_pool"] = s.get("telefon_leitungen", 4) - sum(x.get("leitungen", 0) for x in s["einheiten"].values())
        else:
            for x in s["einheiten"].values():
                x.pop("leitungen", None)
            s.pop("leitungen_pool", None)
        prot.append(f"CO TAC Net with {'EE8 Field Phones, ' + str(s.get('telefon_leitungen', 4)) + ' Phone Lines' if o['--netz'] == 'telefon' else 'SCR536 radio'}"
                    + (f" (previously {alt})" if alt and alt != o["--netz"] else "") + "; BN TAC and FD nets stay radio [CSR 1 p.13, 4.3.3 p.27]")
    if "--moerser" in o:
        if o["--moerser"] not in ("sektion", "teams"):
            raise Verstoss("--mortar=section|teams")
        if s.get("moerser_wahl") == o["--moerser"]:
            pass
        elif o["--moerser"] == "teams":
            sek = s["einheiten"].pop("Mtr Sec", None)
            if sek is None:
                raise Verstoss("Mtr Sec no longer in play")
            for tn, td in s.get("reserve_einheiten", {}).items():
                te = copy.deepcopy(td)
                te.update(karte=sek["karte"], platoon=sek.get("platoon"), attached_an=list(sek.get("attached_an", [])), bereich="offen", status=[])
                te["funk"] = []
                s["einheiten"][tn] = te
            s["mtr_sec_funk_frei"] = sek.get("funk", [])
            prot.append("CSR 2: three 1-step Mortar Teams 1/Mtr, 2/Mtr, 3/Mtr (G!, 4 Mtr ammo each, each carries 2) instead of the Section; the Section radio "
                        "can be assigned freely: setup <unit> --device=SCR536 [CSR 2 p.13]")
        else:
            if "Mtr Sec" in s["einheiten"]:
                pass
            else:
                teams = [tn for tn in s.get("reserve_einheiten", {}) if tn in s["einheiten"]]
                ref = s["einheiten"][teams[0]] if teams else {}
                for tn in teams:
                    del s["einheiten"][tn]
                sek = copy.deepcopy(s["aufbau_einheiten"]["Mtr Sec"])
                sek.update(karte=ref.get("karte"), platoon=ref.get("platoon"), attached_an=list(ref.get("attached_an", [])))
                sek["funk"] = s.pop("mtr_sec_funk_frei", sek.get("funk", []))
                s["einheiten"]["Mtr Sec"] = sek
            prot.append("CSR 2: 60mm Mortar Section (H, 3 steps, 4 Mtr ammo, abstracted carriers) [CSR 2 p.13]")
        s["moerser_wahl"] = o["--moerser"]
    if "--geraet" in o:
        frei = s.get("mtr_sec_funk_frei", [])
        g = [x for x in frei if x["typ"] == o["--geraet"]]
        if not g:
            raise Verstoss("Only the Mortar Section's device can be assigned freely, and only if teams were chosen [CSR 2 p.13]")
        frei.remove(g[0])
        e.setdefault("funk", []).append(g[0])
        prot.append(f"{n} receives {g[0]['typ']} {g[0]['netz']} (Section device, CSR 2)")
    if "--asset" in o:
        pool = s.setdefault("assets_pool", {})
        for typ in o["--asset"].split(","):
            if pool.get(typ, 0) <= 0:
                raise Verstoss(f"Asset {typ} not (or no longer) in the pool: {', '.join(f'{k} {v}' for k, v in pool.items() if v)} [Normandy p.13]")
            if typ == "Rifle Grenade":
                if e["typ"] != "Squad" and not ist_lat(e):
                    s.setdefault("_hinweise", []).append("Rifle Grenade: intended for Rifle Squads (Unit Guide p.11)")
                pl = e.get("platoon")
                schon = [m for m, x in s["einheiten"].items() if "Rifle Grenade" in x.get("assets", []) and x.get("platoon") == pl]
                if pl and schon:
                    raise Verstoss(f"Rifle Grenades: at most 1 per platoon, platoon {pl} already has one ({schon[0]}) [Normandy p.13]")
            pool[typ] -= 1
            e.setdefault("assets", []).append(typ)
            prot.append(f"{n} receives asset {typ} [2.3.4 p.10]")
    if "--leitungen" in o:
        if s.get("co_tac_mittel") != "telefon":
            raise Verstoss("Phone Lines only if the CO TAC Net uses telephones: setup \"CO HQ\" --net=telefon [CSR 1 p.13]")
        k = int(o["--leitungen"])
        frei = s.get("leitungen_pool", 0) + e.get("leitungen", 0)
        if k > frei:
            raise Verstoss(f"Only {frei} Phone Lines available [CSR 1 p.13]")
        s["leitungen_pool"] = frei - k
        e["leitungen"] = k
        prot.append(f"{n} carries {k} Phone Line(s); lays one each time it leaves a card [4.3.4 p.28]")
    if "--pyro" in o:
        typ, code = o["--pyro"].split(":", 1)
        if typ not in PYRO_LUFT + PYRO_FARBE:
            raise Verstoss(f"Signal devices: {', '.join(PYRO_LUFT[:4] + PYRO_FARBE)} [4.4.1 p.30]")
        if s.get("patrouille_mission"):
            # [RULE 4.4.1 p.30] Patrol Mission Pyrotechnic Signal Options
            if code not in PYRO_CODES_PAT and not re.fullmatch(r"M2RP[1-4]", code):
                raise Verstoss(f"Code from the patrol list: CF, M2RP<1-4>, M2PO, M2S [4.4.1 p.30]")
        elif code not in PYRO_CODES_OFF and not re.fullmatch(r"XPL\d+", code):
            raise Verstoss(f"Code from the offensive list: {', '.join(PYRO_CODES_OFF)}, XPL<n> [4.4.1 p.30]")
        s.setdefault("pyro_belegung", {})[typ] = code
        prot.append(f"Mission Log: {typ} = {code} [4.4.1 p.30]")


def aufstellung_pruefen_v4(s):
    """Before the first 'phase next': mandatory mission choices done?"""
    f = []
    ohne = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and not e.get("karte")
            and (not s.get("patrouille_mission") or n in (s.get("patrouille") or {}).get("mitglieder", []))]
    if ohne:
        f.append("no starting card: " + ", ".join(ohne) + " (setup <unit> <11-14>)")
    if s.get("co_tac_mittel") is None and "telefon_leitungen" in s:
        f.append("CSR 1: setup \"CO HQ\" --net=radio|phone")
    if s.get("moerser_wahl") is None and s.get("reserve_einheiten"):
        f.append("CSR 2: setup \"Mtr Sec\" --mortar=section|teams")
    z = s.get("ziele", {})
    for k, t in (("primaer", "Primary Objective"), ("sekundaer", "Secondary Objective"), ("ap", "Attack Position")):
        if k in z and not z.get(k):
            f.append(f"{t}: objective {({'primaer': 'primary', 'sekundaer': 'secondary'}).get(k, k)} <card>")
    if s.get("patrouille_mission"):
        if s.get("licht") is None:
            f.append("Patrol visibility: draw R#4 (1=+2 ... 4=+5), fof.py visibility <light> [Normandy M3 p.24, M3-2]")
        z = s.get("ziele", {})
        if not z.get("cop"):
            f.append("Combat Outpost: objective cop <card in row 2> [p.24]")
        if not z.get("primaer"):
            f.append("Primary Objective: objective primary <card in row 4> [p.24]")
        if len(z.get("route", {})) < 4:
            f.append("Route Points: objective route <1-4> <card in rows 2-4> [MSR 2]")
        if not (s.get("patrouille") or {}).get("platoon"):
            f.append("Patrol: patrol start <1|2|3> [--with=..] [MSR 1]")
    oh = [k for k, c in s["karten"].items() if not c.get("staging") and not c.get("terrain")]
    if oh:
        f.append("Terrain missing: " + ", ".join(sorted(oh)) + " (terrain <card> <type>)")
    nv = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and e["typ"] in ("Squad", "Weapons Team") and e.get("vof_rating") is None
          and (e.get("karte") or not s.get("patrouille_mission"))]
    if nv:
        f.append("VOF missing (from the counter): " + ", ".join(nv) + " (set <unit> vof_rating=.. reichweite=..)")
    return f


# ---------------------------------------------------------------- Telephone (4.3.4)
def leitung_auf(s, kid):
    return [l for l in karte(s, kid).get("leitungen", []) if True]


def telefon_knoten(s):
    """Cards that are part of the phone line network: intact line, phone in use (implicit line, BGG E28), Staging (integrated)."""
    kn = set()
    for k, c in s["karten"].items():
        if c.get("staging") or any(not l.get("cut") for l in c.get("leitungen", [])):
            kn.add(k)
    for e in s["einheiten"].values():
        if e["seite"] == "US" and e.get("karte") in s["karten"] and geraete(e, "EE8"):
            kn.add(e["karte"])
    return kn


def telefon_netz_verbunden(s, a, b, diag=None):
    """[RULE 4.3.4 p.28] 'unbroken string of phone line markers or other phones'; Staging with integrated lines.
    Returns: False, True (without diagonal) or 'diagonal' (only via diagonal adjacency, open U14)."""
    if diag is None:
        if telefon_netz_verbunden(s, a, b, False):
            return True
        return "diagonal" if opt(s, "U14_telefon_diagonal") and telefon_netz_verbunden(s, a, b, True) else False
    kn = telefon_knoten(s)
    if a not in kn or b not in kn:
        return False
    gesehen, stapel = {a}, [a]
    while stapel:
        k = stapel.pop()
        if k == b:
            return True
        ck = karte(s, k)
        for m in kn:
            if m in gesehen:
                continue
            cm_ = karte(s, m)
            dr, dc = abs(ck["reihe"] - cm_["reihe"]), abs(ck["spalte"] - cm_["spalte"])
            nb = (dr + dc == 1) or (diag and dr == 1 and dc == 1) or (ck.get("staging") and cm_.get("staging"))
            if nb:
                gesehen.add(m)
                stapel.append(m)
    return False


def telefon_verbindung(s, a_name, b_name):
    """CO TAC by telephone: both with EE8 CO TAC, the CO HQ is the hub; cover, Pinned, areas do not matter (4.3.4 p.28)."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    for n, e in ((a_name, a), (b_name, b)):
        if not geraete(e, "EE8", "CO TAC"):
            return False, f"{n} has no EE8 CO TAC"
    co = s.get("co_hq")
    if co not in (a_name, b_name):
        if co not in s["einheiten"]:
            return False, "CO HQ (hub of the CO TAC Net) not in play [4.3.3 p.27]"
        ok1, g1 = telefon_verbindung(s, a_name, co)
        ok2, g2 = telefon_verbindung(s, co, b_name)
        return (ok1 and ok2), f"via the hub {co}: " + ("; ".join((g1, g2)) if ok1 and ok2 else (g1 if not ok1 else g2)) + offen(s, "U11_plt_mtr_ueber_hub")
    if a["karte"] == b["karte"]:
        return True, f"EE8 on the same card {a['karte']} [4.3.4 p.28]"
    vb = telefon_netz_verbunden(s, a["karte"], b["karte"])
    if vb:
        return True, f"EE8 CO TAC, line chain {a['karte']} to {b['karte']}" + (" (via diagonally adjacent cards)" + offen(s, "U14_telefon_diagonal") if vb == "diagonal" else "") + " [4.3.4 p.28]"
    return False, f"no unbroken line chain {a['karte']} to {b['karte']} (line cut or missing) [4.3.4 p.28]"


def leitung_legen(s, n, e, von, prot, o=None):
    """[RULE 4.3.4 p.28] 'lay down one phone line marker per card ... automatically when a laying unit leaves a card' [open U15]."""
    if not e.get("leitungen") or karte(s, von).get("staging"):
        return
    if (o or {}).get("--leitung") == "nein" or not opt(s, "U15_leitung_automatisch"):
        return
    c = karte(s, von)
    if any(not l.get("cut") for l in c.get("leitungen", [])):
        return
    c.setdefault("leitungen", []).append({"cut": False})
    e["leitungen"] -= 1
    prot.append(f"{n} lays a Phone Line on {von} ({e['leitungen']} left)" + offen(s, "U15_leitung_automatisch") + " [4.3.4 p.28]")


def cmd_leitung(s, args):
    """Phone lines: result of the damage check in 3.7.4 (ok|cut) or manual laying."""
    if not args:
        raise Verstoss("line <card> ok|cut | line lay <card> <unit>")
    prot = []
    if args[0] == "legen":
        kid, n = args[1], args[2]
        e = einheit(s, n)
        if e["karte"] != kid or not e.get("leitungen"):
            raise Verstoss(f"{n} is not on {kid} or carries no phone line")
        karte(s, kid).setdefault("leitungen", []).append({"cut": False})
        e["leitungen"] -= 1
        prot.append(f"{n} lays a Phone Line on {kid} (4.3.4: 'may lay down one phone line marker per card')")
    else:
        kid, erg = args[0], args[1]
        offen_ = s.get("leitung_checks", {})
        if kid not in offen_:
            raise Verstoss(f"No phone line check is pending for {kid}")
        grund = offen_.pop(kid)
        if erg == "cut":
            for l in karte(s, kid).get("leitungen", []):
                l["cut"] = True
            prot.append(f"Phone Line on {kid} cut ({grund}): marker to the Cut side; repair with 4.2.1k [4.3.4 p.29]")
        elif erg == "ok":
            prot.append(f"Phone Line on {kid} stays intact ({grund})")
        else:
            raise Verstoss("ok | cut")
    speichern(s, "; ".join(prot), "4.3.4 p.29")
    ausgabe(prot, s)


def leitung_checks_3_7_4(s, prot):
    """[RULE 4.3.4 p.29] Incoming/Air Strike: R#1/2 cut; Good Order enemy without Good Order friendly: R#1-2/3 cut."""
    ch = {}
    for kid, c in s["karten"].items():
        if not any(not l.get("cut") for l in c.get("leitungen", [])):
            continue
        if any(x["typ"] in ("Incoming", "AirStrike") for x in c.get("extern", [])):
            ch[kid] = "Incoming/Air Strike, R# 1/2 = cut"
        elif any(good_order(s["einheiten"][m]) for m in auf(s, kid, "Feind")) and not any(good_order(s["einheiten"][m]) for m in auf(s, kid, "US")):
            ch[kid] = "Good Order enemy without Good Order friendly, R# 1-2/3 = cut"
    if ch:
        s["leitung_checks"] = ch
        prot.append("Check phone lines: " + "; ".join(f"{k} ({g})" for k, g in ch.items()) + "; then fof.py line <card> ok|cut [4.3.4 p.29]")


# ---------------------------------------------------------------- Runner (4.3.2, 4.2.1f/g/h)
def runner_box(s):
    return s.setdefault("runner_box", [])


def runner_zahl(s):
    return len(runner_box(s)) + len([n for n, e in s["einheiten"].items() if e["typ"] == "Runner"])


def runner_zustellen(s, prot):
    """[RULE 4.3.2 p.27] In the CO HQ impulse of the following turn: Runner not Pinned, HQ still on the card and not on its Fire Team side:
    HQ activated, Runner back to the Assets box. Otherwise it returns at the start of the first CO HQ impulse in Good Order."""
    for n, e in list(s["einheiten"].items()):
        if e["typ"] != "Runner" or e["seite"] != "US":
            continue
        if e.get("unterwegs_seit") == s["zug"]:
            continue
        hq = e.get("runner_ziel")
        h = s["einheiten"].get(hq)
        if pinned(e) or not good_order(e):
            prot.append(f"{n}: Pinned/not Good Order, no delivery; returns in the first CO HQ impulse in Good Order [4.3.2 p.27]")
            continue
        if h and h["karte"] == e["karte"] and not ft_seite(h) and hq in s["kommandos"]:
            s["kommandos"][hq]["aktiviert"] = True
            prot.append(f"{n} delivers: {hq} activated (Command marker on Commands Available); Runner back to the CO HQ Assets box [4.3.2 p.27]")
        else:
            prot.append(f"{n}: {hq} no longer on {e['karte']} or on its Fire Team side; Runner returns to the Assets box [4.3.2 p.27]")
        del s["einheiten"][n]
        runner_box(s).append(n)


def cmd_runner(s, args):
    box = runner_box(s)
    auf_brett = [f"{n} on {e['karte']} for {e.get('runner_ziel')}" for n, e in s["einheiten"].items() if e["typ"] == "Runner"]
    print(f"Runners in the CO HQ Assets box: {', '.join(box) or 'none'}; en route: {', '.join(auf_brett) or 'none'}; at most two in play [4.3.2 p.27]")


# ---------------------------------------------------------------- Ammo (7.18, 8.11, 5.1.6)
def muni(e):
    return e.get("munition")


def muni_kap(e):
    m = muni(e)
    if not m or e.get("munition_traeger_abstrakt"):
        return None
    k = MUNITION_KAP.get(m["typ"])
    return None if k is None else k * steps(e)


def muni_verbrauch(s, n, e, punkte, grund, prot):
    m = muni(e)
    if not m:
        return
    alt = m["punkte"]
    m["punkte"] = max(0, alt - punkte)
    prot.append(f"{n}: {punkte} {m['typ']} ammo ({grund}), {alt} to {m['punkte']} [7.18 p.59]")
    if m["punkte"] == 0 and not e.get("out_of_ammo"):
        if opt(s, "U22_munition_leer_im_clean_up") and s["phase"] == "3.7.4":
            e["munition_leer"] = True
            prot.append(f"{n}: last ammo fired; Out of Ammo effects in Clean Up{offen(s, 'U22_munition_leer_im_clean_up')} [7.18.2 p.61]")
        else:
            out_of_ammo(s, n, e, prot)


def out_of_ammo(s, n, e, prot):
    """[RULE 7.18.2 p.61, 8.11 p.68] 1-step weapons team with S or A/S reverse: flip to the Fire Team side; otherwise Out of Ammo marker
    (VOF S, range Close). [RULE 7.18.1D p.60] SG! unit with rockets only loses the Close Range Grenade Attacks."""
    e.pop("munition_leer", None)
    m = muni(e)
    if m and m["typ"] == "RKT" and e.get("grenade_ranged") and e.get("vof_rating") == "S":
        e["grenade_ranged"] = False
        e["rkt_leer"] = True
        prot.append(f"{n}: no rockets left, no Grenade Attacks at range; Basic VOF S remains [7.18.1D p.60]")
        return
    if steps(e) == 1 and e.get("fire_team_seite") and e.get("ft_vof") in ("S", "A/S") and e["typ"] != "Squad":
        markieren(e, "Fire Team side")
        e["ziel"] = None
        prot.append(f"{n}: Out of Ammo, flip to the Fire Team side [7.18.2 p.61]" + (" (enemy: Spotted attempts Fall Back instead of the hierarchy in the Activity Check, 8.11)" if e["seite"] == "Feind" else ""))
        if e["seite"] == "Feind":
            e["ooa_fallback"] = True
        return
    e["out_of_ammo"] = True
    prot.append(f"{n}: Out of Ammo marker: VOF S, range Close until resupply [7.18.2 p.61, 8.11 p.68]")
    if e.get("ziel") and e["ziel"] != e["karte"] and not in_reichweite(s, e, e["ziel"]):
        prot.append(f"{n}: target {e['ziel']} now out of range, Cease Fire, reopens per 6.1.1 [3.8, 8.11 p.68, L40]")
        e["ziel"] = None


def muni_ueberschuss(s, n, e, von, prot):
    """[RULE 7.18 Note p.60, 8.11 p.68] A unit carrying more than its capacity leaves the rest behind when moving."""
    k = muni_kap(e)
    m = muni(e)
    if k is None or not m or m["punkte"] <= k:
        return
    rest = m["punkte"] - k
    m["punkte"] = k
    lager = karte(s, von).setdefault("munition", {})
    lager[m["typ"]] = lager.get(m["typ"], 0) + rest
    prot.append(f"{n} can only carry {k} {m['typ']} ammo: {rest} stay behind on {von} [5.1.6A p.33, 7.18 p.60]")


def cmd_munition(s, args):
    if args and args[0] == "lager":
        kid, typ, zahl = args[1], args[2], int(args[3])
        ev = s.get("ereignis_munition")
        if not ev:
            raise Verstoss("Ammo on cards only via event (Ammo Resupply) or dropping (drop <unit> <type>:<n>)")
        if karte(s, kid)["reihe"] != erste_kartenreihe(s) or karte(s, kid).get("staging"):
            raise Verstoss(f"Ammo Resupply: a card of mission row 1 (tool row {erste_kartenreihe(s)}) [Normandy M1 p.18]")
        if zahl != 4 or typ not in MUNITION_KAP:
            raise Verstoss("Ammo Resupply: 'four of any one type of ammo' (MG, MTR, RKT) [Normandy M1 p.18]")
        lager = karte(s, kid).setdefault("munition", {})
        lager[typ] = lager.get(typ, 0) + 4
        s.pop("ereignis_munition", None)
        prot = [f"4 {typ} ammo on {kid}; pick up with 4.2.2h --what={typ}:<n> [Normandy M1 p.18, 7.18.3 p.61]"]
        speichern(s, "; ".join(prot), "Normandy M1 p.18")
        ausgabe(prot, s)
        return
    for n, e in s["einheiten"].items():
        m = muni(e)
        if m:
            print(f"- {n} ({e['seite']}): {m['typ']} {m['punkte']}" + (f" of {m.get('start')}" if m.get("start") else "") + (" OUT OF AMMO" if e.get("out_of_ammo") else "")
                  + (f", carries {muni_kap(e)}" if muni_kap(e) is not None else ""))
        if e.get("traegt_munition"):
            print(f"- {n} additionally carries {e['traegt_munition']['punkte']} {e['traegt_munition']['typ']}")
    for k, c in s["karten"].items():
        if c.get("munition"):
            print(f"- on {k}: " + ", ".join(f"{t} {v}" for t, v in c["munition"].items() if v))


def muni_aufnehmen(s, z, name, was, prot):
    """[RULE 5.1.6 p.32, 7.18.3 p.61] Pick up ammo from the card; an Out of Ammo unit is resupplied."""
    typ, zahl = was.split(":")
    zahl = int(zahl)
    lager = karte(s, z["karte"]).setdefault("munition", {})
    if lager.get(typ, 0) < zahl:
        raise Verstoss(f"On {z['karte']} there are only {lager.get(typ, 0)} {typ}")
    m = muni(z)
    if m and m["typ"] == typ:
        k = muni_kap(z)
        neu = m["punkte"] + zahl if k is None else min(k, m["punkte"] + zahl)
        genommen = neu - m["punkte"]
        m["punkte"] = neu
        lager[typ] -= genommen
        prot.append(f"{name} picks up {genommen} {typ} (now {neu}) [7.18.3 p.61]")
        if z.get("out_of_ammo") or (ft_seite(z) and z.get("fire_team_seite") and z["typ"] != "HQ"):
            z.pop("out_of_ammo", None)
            if ft_seite(z):
                z["status"].remove("Fire Team side")
            prot.append(f"{name}: resupplied, Out of Ammo marker removed or back to the Good Order side, fires again with original VOF [7.18.3 p.61]")
        if z.get("rkt_leer"):
            z["grenade_ranged"] = True
            z.pop("rkt_leer")
        return
    kap = steps(z) * MUNITION_KAP.get(typ, 1)
    tm = z.get("traegt_munition")
    if tm and tm["typ"] != typ:
        raise Verstoss(f"{name} already carries {tm['typ']}; only one ammo type per unit [5.1.6A p.33]")
    if z.get("traegt_casualties"):
        raise Verstoss(f"{name} carries Casualties; Casualties or one ammo type [5.1.6A p.33]")
    have = tm["punkte"] if tm else 0
    if have + zahl > kap:
        raise Verstoss(f"{name} can carry at most {kap} {typ} ({steps(z)} step(s)) [5.1.6A p.33]")
    z["traegt_munition"] = {"typ": typ, "punkte": have + zahl}
    lager[typ] -= zahl
    prot.append(f"{name} picks up {zahl} {typ} for transport [5.1.6 p.32]")


def muni_ablegen(s, e, n, was, prot):
    typ, zahl = was.split(":")
    zahl = int(zahl)
    tm = e.get("traegt_munition")
    if not tm or tm["typ"] != typ or tm["punkte"] < zahl:
        raise Verstoss(f"{n} does not carry {zahl} {typ}")
    tm["punkte"] -= zahl
    if not tm["punkte"]:
        e.pop("traegt_munition")
    lager = karte(s, e["karte"]).setdefault("munition", {})
    lager[typ] = lager.get(typ, 0) + zahl
    prot.append(f"{n} drops {zahl} {typ} on {e['karte']} (no Command) [5.1.6B p.33, 7.18.3 p.61]")


def muni_3_7_4(s, prot):
    """[RULE 3.7.4 p.17, 7.18.4 p.61, 8.1 p.61] Every ammo-dependent unit that exercises a VOF (even Pinned, even Indirect Lay)
    uses one point."""
    for n, e in list(s["einheiten"].items()):
        if muni(e) and not e.get("out_of_ammo") and (feuert(e) or e.get("indirekt")) and not e.get("nur_pdf") and muni(e)["punkte"] > 0:
            if e.get("rkt_leer"):
                continue
            if muni(e)["typ"] == "RKT":
                continue                                                          # rockets only for Grenade Attacks (7.18.1D), S fire without ammo
            muni_verbrauch(s, n, e, 1, "VOF this turn", prot)


# ---------------------------------------------------------------- Mines (7.9.1, 8.7.1)
def minen_auf(s, kid):
    return [x for x in karte(s, kid).get("extern", []) if x["typ"] == "Mines"]


def minencheck_anfordern(s, namen, kid, prot, grund):
    if not minen_auf(s, kid):
        return
    namen = [n for n in namen if n in s["einheiten"] and s["einheiten"][n]["typ"] not in ("Casualty",)]
    if not namen:
        return
    s.setdefault("minen_checks", [])
    for n in namen:
        if n not in s["minen_checks"]:
            s["minen_checks"].append(n)
    prot.append(f"Mine check on {kid} ({grund}) for {', '.join(namen)}: 3 Action cards per unit, hit on a Burst symbol (also multiple Burst and Short); then fof.py mine <unit> yes|no [7.9.1 p.54]")


def cmd_mine(s, args):
    n, erg = args[0], args[1]
    if n not in s.get("minen_checks", []):
        raise Verstoss(f"No mine check pending for {n}")
    e = einheit(s, n)
    s["minen_checks"].remove(n)
    prot = []
    if erg == "ja":
        e["mine_hit"] = True
        for x in minen_auf(s, e["karte"]):
            x["aktiv"] = True
        prot.append(f"{n} hit by a mine: Mine marker to its explosion side, {n} beneath it; Mines! VOF -4 in 3.7.4; may not move within the card or to an adjacent card this turn [7.9.1 p.54]")
    elif erg == "nein":
        prot.append(f"{n}: no mine hit")
    else:
        raise Verstoss("yes | no")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, "; ".join(prot), "7.9.1 p.54")
    ausgabe(prot, s)


def minen_sperre(s):
    if s.get("minen_checks"):
        raise Verstoss("First resolve the pending mine checks: " + ", ".join(s["minen_checks"]) + " (fof.py mine <unit> yes|no) [7.9.1 p.54, 8.7.1 p.67]")


# ---------------------------------------------------------------- Sniper (7.15, 8.8)
def ist_sniper(e):
    return e.get("vof_rating") == "S!" and not ft_seite(e) and not ist_lat(e)


def sniper_auf_karte(s, kid):
    """Firing, non-pinned snipers whose VOF lies on kid (7.15: HQs there -3 Command draw)."""
    return [n for n, e in s["einheiten"].items() if ist_sniper(e) and feuert(e) and not pinned(e) and feuerziel_effektiv(s, n) == kid]


def sniper_ziele_waehlen(s, prot):
    """[RULE 7.15 p.57] At the start of 3.7.4: random target on the card, Exposed first."""
    s["sniper_ziele"] = {}
    s["sniper_offen"] = {}
    for n in [m for m, e in s["einheiten"].items() if ist_sniper(e) and feuert(e) and not pinned(e)]:
        kid = feuerziel_effektiv(s, n)
        kand = [m for m in auf(s, kid, gegner(s["einheiten"][n]["seite"]))]
        exp = [m for m in kand if "Exposed" in s["einheiten"][m]["status"]]
        if exp:
            kand = exp
        if len(kand) == 1:
            s["sniper_ziele"][n] = kand[0]
            prot.append(f"Sniper VOF (-3) from {n} on {kand[0]}; rest of the card Small Arms only [7.15 p.57]")
        elif kand:
            s["sniper_offen"][n] = kand
            prot.append(f"Sniper {n}: target by R# (column {len(kand)}) from {', '.join(kand)}" + (" (Exposed only)" if exp else "") + f"; then fof.py sniper \"{n}\" <target> [7.15 p.57]")


def cmd_sniper(s, args):
    n, z = args[0], args[1]
    kand = s.get("sniper_offen", {}).get(n)
    if not kand:
        raise Verstoss(f"No target choice pending for {n}")
    if z not in kand:
        raise Verstoss(f"{z} not among {', '.join(kand)}")
    s["sniper_offen"].pop(n)
    s.setdefault("sniper_ziele", {})[n] = z
    if z in s.get("kampf_ncm", {}) or z in s.get("kampf_offen", []):
        s.setdefault("kampf_ncm", {})[z] = [list(x) for x in ncm_zeilen(s, z)]
    prot = [f"Sniper VOF (-3) from {n} on {z} [7.15 p.57]"]
    speichern(s, "; ".join(prot), "7.15 p.57")
    ausgabe(prot, s)


# ---------------------------------------------------------------- Higher HQ Events (3.1, 3.4.1, Normandy M1 p.18)
def r_passt(bereich, r):
    if "-" in bereich:
        a, b = bereich.split("-")
        return int(a) <= r <= int(b)
    return r == int(bereich)


def ereignis_suchen(s, liste, r):
    for ev in liste:
        for zuege, rb in ev["r"].items():
            za, zb = (zuege.split("-") + [zuege])[:2]
            if int(za) <= s["zug"] <= int(zb) and r_passt(rb, r):
                return ev
    return None


def bn_leader(s):
    return [n for n, e in s["einheiten"].items() if e.get("ebene") == "BN" and e["seite"] == "US"]


def cmd_ereignis(s, args):
    """[RULE 3.1 p.15, 3.4.1 p.16] Action card: HQ radio symbol? Then a second card, R# on the mission's event table."""
    tab = s.get("ereignistabellen")
    if not tab:
        raise Verstoss("This mission has no event tables")
    if s["phase"] not in ("3.1", "3.4.1", "3.2.1") or s["zug"] < 2:
        raise Verstoss("Events only in 3.1 (Friendly) and 3.4.1 (Enemy), from turn 2 on [RULE 3.1 p.15, 3.4.1 p.16]")
    if s.get("ereignis_erledigt") == [s["zug"], s["phase"]]:
        raise Verstoss("The event of this segment has already been resolved")
    freund = s["phase"] == "3.1"
    nr, icon = args[0], args[1]
    o = opts_parse(args[2:])
    prot = []
    if icon == "nein":
        prot.append(f"Action card #{nr} without HQ radio symbol: no {'Friendly' if freund else 'Enemy'} Higher HQ Event")
    elif icon == "ja":
        if len(args) < 3 or args[2].startswith("--"):
            raise Verstoss(f"HQ symbol: draw a second Action card, give R# column {tab.get('spalte', 10)}: event {nr} yes <R#>")
        r = int(args[2])
        ev = ereignis_suchen(s, tab["freund" if freund else "feind"], r)
        if ev is None:
            raise Verstoss(f"R# {r} in turn {s['zug']} not in the table")
        prot.append(f"Action card #{nr} with HQ symbol, R# {r}: {ev['text']}")
        (ereignis_freund if freund else ereignis_feind)(s, ev, o, prot)
    else:
        raise Verstoss("event <cardno> yes <R#> | event <cardno> no")
    s["ereignis_erledigt"] = [s["zug"], s["phase"]]
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, "Event: " + "; ".join(prot), "3.1 p.15" if freund else "3.4.1 p.16")
    ausgabe(prot, s)


def ereignis_freund(s, ev, o, prot):
    i = ev["id"]
    co = s.get("co_hq")
    if i in ("situation_report", "comm_trouble"):
        n = 3 if i == "situation_report" else 2
        s["ereignis_pflicht"] = {"id": i, "commands": n, "zug": s["zug"], "stern": ev.get("stern")}
        if i == "comm_trouble":
            s["bn_nicht_verfuegbar"] = s["zug"]
            prot.append(f"BN HQ does not activate {co} this turn; {co} draws Initiative in 3.3.2a [4.1.1 p.19]")
        prot.append(f"{co} must spend its first {n} Commands on it; the tool deducts them at {co}'s first card draw"
                    + offen(s, "U16_erste_commands_mit_gespart") + "; no penalty if Commands are short [Normandy M1 p.18]")
    elif i == "artillery_displacing":
        s["fm_gesperrt"] = {"zug": s["zug"], "gruppe": ev.get("gruppe", "15th FA")}
        prot.append(f"{ev.get('gruppe', '15th FA')} not available this turn (no Call for Fire)")
    elif i == "checking_up":
        wer = o.get("--wer")
        if wer not in ("Rgt", "Bn"):
            raise Verstoss("Checking Up: choose Higher HQ Staff by R#/2 (Rgt Cmdr or Bn Cmdr) and --who=Rgt|Bn [Normandy M1 p.18]")
        if co not in s["einheiten"]:
            prot.append(f"{co} not in play: event not possible, no event [3.1 p.15]")
            return
        name = "Rgt Cmdr" if wer == "Rgt" else "Bn Cmdr"
        c = s["einheiten"][co]
        s["einheiten"][name] = {"typ": "HQ", "ebene": "BN", "platoon": None, "seite": "US", "erfahrung": "Line", "karte": c["karte"],
                                "bereich": c.get("bereich", "offen"), "status": [], "steps": 1, "vof_rating": None, "reichweite": "L", "ziel": None,
                                "fire_team_seite": True, "ft_vof": "S", "funk": [], "bis_zug": s["zug"] + 1,
                                "hinweis": "Higher HQ Staff (Line, 4.1.1); no BN TAC radio, activates the CO HQ only by Visual-Verbal (BGG E30)"}
        s["kommandos"][name] = {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False}
        prot.append(f"{name} on {c['karte']} (with {co}) through turn {s['zug'] + 1}; BN HQ counts as 'on the map': in the BN HQ impulse {name} receives "
                    f"{MAX_IMPULS[s['sicht']]} Commands and must activate {co} itself (communication required) [4.1.1 p.18/19]")
    elif i == "trouble_flank":
        s["ereignis_flanke"] = {"id": i, "zug": s["zug"]}
        prot.append(f"No unit may move this turn onto a new row ahead of the foremost US unit (now row {us_front(s)})")
    elif i in ("company_ahead", "screaming"):
        if us_front(s) >= oberste_reihe(s):
            prot.append("already on row 3: event lapses [Normandy M1 p.18]")
            return
        if i == "screaming" and not any(c.get("pc") for c in s["karten"].values() if c["reihe"] == us_front(s) + 1):
            s.setdefault("_hinweise", []).append("Screaming for Action: check whether a PC marker in the next row is reachable; otherwise the event lapses")
        s["ereignis_flanke"] = {"id": i, "zug": s["zug"], "reihe": us_front(s), "stern": ev.get("stern"), "erfuellt": False}
        prot.append(f"Mandatory (if Commands suffice): at least one unit onto a new row {us_front(s) + 1}" + (" with a PC marker" if i == "screaming" else "")
                    + "; fulfilled = 1 Experience Point [Normandy M1 p.18]")
    elif i == "hold_up":
        s["hold_up"] = s["zug"]
        prot.append("Hold up!: no friendly unit may move onto an unoccupied card this turn [Normandy M3 p.26]")
    elif i == "raining":
        s["wetter"], s["wetter_nur_zug"] = 2, True
        sicht_aktualisieren(s)
        prot.append(f"Rain marker: visibility +2 this turn (total {sum(licht_wetter(s)):+d}), Limited Visibility; no card counts as illuminated (9.2.1); remove in Clean Up [Normandy M3 p.26]")
    elif i == "lost_dark":
        wer, nach = o.get("--wer"), o.get("--nach")
        mit = pat(s).get("mitglieder", [])
        if not wer or not nach:
            raise Verstoss(f"Lost in the Dark: choose a patrol unit by R# ({', '.join(m for m in mit if m in s['einheiten'])}), direction by R#8, --who=<unit> --to=<card> "
                           "(if the card lies outside: first extend <row> <column> <type> and pc set <card> <letter of the row, row 5 = A>) [Normandy M3 p.26]")
        if wer not in mit:
            raise Verstoss(f"{wer} is not part of the patrol")
        karte(s, nach)
        if not benachbart(s, s["einheiten"][wer]["karte"], nach):
            raise Verstoss(f"{nach} is not adjacent to {s['einheiten'][wer]['karte']}")
        bewegen(s, wer, nach, "offen", True, prot)
        prot.append("Lost in the Dark: unit moved one card in a random direction and Exposed [Normandy M3 p.26]")
    elif i == "screaming_route":
        z = s.get("ziele", {})
        idx = pat(s).get("route_index", 0)
        if idx >= 4:
            prot.append("All four Route Points visited: event lapses [Normandy M3 p.26]")
            return
        s["ereignis_route"] = {"zug": s["zug"], "ziel": z.get("route", {}).get(str(idx + 1)), "stern": ev.get("stern"), "erfuellt": False}
        prot.append(f"Mandatory (if Commands suffice): at least one unit toward Route Point {idx + 1} ({s['ereignis_route']['ziel']}); fulfilled = 1 Experience Point [Normandy M3 p.26]")
    elif i == "ammo_resupply":
        s["ereignis_munition"] = s["zug"]
        prot.append("Four ammo of one type onto a card of mission row 1 of your choice: fof.py ammo depot <card> MG|MTR|RKT 4 [Normandy M1 p.18]")


def ereignis_feind(s, ev, o, prot):
    i = ev["id"]
    ohne_us = [k for k in s["karten"] if not auf(s, k, "US")]
    s["ereignis_einheiten"] = []
    if i == "evacuate":
        for k in ohne_us:
            c = s["karten"][k]
            if c.get("casualties_feind"):
                prot.append(f"{k}: {c['casualties_feind']} enemy Casualties removed")
                c["casualties_feind"] = 0
    elif i in ("displace_mortars", "displace_leaders", "displace_hmgs"):
        test = {"displace_mortars": lambda e: moerser(e), "displace_leaders": lambda e: bool(e.get("leader")),
                "displace_hmgs": lambda e: e.get("typname") == "German HMG"}[i]
        for n, e in list(s["einheiten"].items()):
            if e["seite"] == "Feind" and e["karte"] in ohne_us and test(e):
                feind_entfernen(s, n, prot, grund=ev["text"].split(":")[0])
        if len(prot) == 1:
            prot.append("no affected unit on a card without US troops")
    elif i == "rally":
        for n, e in s["einheiten"].items():
            if e["seite"] != "Feind" or not (pinned(e) or ist_lat(e) or ft_seite(e)):
                continue
            s["ereignis_einheiten"].append(n)
            e["check_offen"] = False
            if vof_gegen(s, e["karte"], "Feind") is None:
                if pinned(e):
                    e["status"].remove("Pinned")
                    prot.append(f"{n}: Pinned removed (no VOF, automatic) [6.5.1]")
                elif ist_lat(e) and e["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team"):
                    naechst = {"Paralyzed Team": "Litter Team", "Litter Team": "Fire Team", "Fire Team": "Assault Team"}[e["typ"]]
                    e["typ"] = naechst
                    lat_werte_setzen(e, naechst)
                    prot.append(f"{n} becomes {naechst} (no VOF, automatic) [6.5.1]")
                elif ft_seite(e):
                    e["status"].remove("Fire Team side")
                    prot.append(f"{n}: back to the front side (no VOF) [4.2.3f]")
            else:
                s.setdefault("rally_offen", []).append(n)
                prot.append(f"{n}: Rally under VOF: {feind_rally_karten(e)[0]} cards (base 2, experience {e.get('erfahrung')}), word Rally; fof.py enemyaction \"{n}\" Rally --success=yes|no")
        prot.append("These units make no further Activity Check in 3.4.2 [3.4.1 p.16]")
    elif i == "fall_back":
        for n, e in list(s["einheiten"].items()):
            if e["seite"] != "Feind" or pinned(e):
                continue
            if e.get("unbeweglich"):
                prot.append(f"{n} is immobile (AT gun), stays [8.12 p.68]")
                continue
            c = karte(s, e["karte"])
            ziel = karte_bei(s, c["reihe"] + 1, c["spalte"])
            s["ereignis_einheiten"].append(n)
            if ziel is None:
                if opt(s, "U18_fall_back_rand_offmap"):
                    feind_entfernen(s, n, prot, grund="Fall Back over the map edge" + offen(s, "U18_fall_back_rand_offmap"))
                continue
            granate_verfaellt(s, e, n, prot)
            e["karte"], e["bereich"] = ziel, "offen"
            markieren(e, "Exposed")
            frei = [cv for cv in karte(s, ziel).get("cover", []) if not any(s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == cv["id"] for m in auf(s, ziel))]
            if frei:
                e["bereich"] = max(frei, key=lambda x: x["wert"])["id"]
            prot.append(f"{n} falls straight back to {ziel}" + (f" under {e['bereich']}" if e["bereich"] != "offen" else "") + ", Exposed [8.6.1C, Normandy M1 p.18]")
            feuer_nach_bewegung(s, n, prot)
            minencheck_anfordern(s, [n], ziel, prot, "enemy enters a mined card")
        for n in s["ereignis_einheiten"]:
            if n in s["einheiten"]:
                s["einheiten"][n]["check_offen"] = False
    elif i == "shifting_lines":
        top = oberste_reihe(s)
        ks = sorted(k for k, c in s["karten"].items() if c["reihe"] == top and c.get("pc") and not c.get("ausserhalb"))
        for k in ks:
            s["karten"][k]["pc"] = "?"
        prot.append(f"Shifting Lines: remove unresolved PC markers of row 4 ({', '.join(ks) or 'none'}), redraw randomly from A, B and C, '?' side up; "
                    "letter when revealed: pc reveal <card> <A|B|C> [Normandy M3 p.26]")
    elif i == "counter_attack":
        ga = s.get("sonderregeln", {}).get("gegenangriff", {})
        karten_us = sorted({e["karte"] for e in s["einheiten"].values() if e["seite"] == "US" and e.get("karte") in s["karten"]
                            and (opt(s, "U17_gegenangriff_staging") or not karte(s, e["karte"]).get("staging"))})
        for k in karten_us:
            c = s["karten"][k]
            if c.get("pc"):
                c["pc2"] = "?"
            else:
                c["pc"] = "?"
        bis = s["zug"] + ga.get("zuege", 3) - 1
        if not s.get("gegenangriff"):
            s["gegenangriff"] = {"taktik_vorher": s.get("feind_taktik"), "bis_zug": bis}
        else:
            s["gegenangriff"]["bis_zug"] = bis
        s["feind_taktik"] = ga.get("taktik", "Offensive Assault")
        prot.append(f"Draw PC markers randomly from all not yet placed, '?' side up, onto {', '.join(karten_us) or 'no card'}"
                    + ("" if opt(s, "U17_gegenangriff_staging") else offen(s, "U17_gegenangriff_staging")) + "; if one is already there, the lower one is removed after revealing (8.2.3 p.62)")
        prot.append(f"Enemy tactic Offensive Assault through turn {bis}; 'Counter Attack Ends' marker on turn {bis + 1}; PC A with the Counter Attack list"
                    + offen(s, "U28_gegenangriff_alle_pc_a") + " [Normandy M1 MSR 1 p.19]")


def ereignis_pflicht_zahlen(s, hq, prot):
    """Situation Report / Comm Trouble: the first N Commands of the CO HQ go to the event (Normandy M1 p.18) [open U16]."""
    ev = s.get("ereignis_pflicht")
    if not ev or ev["zug"] != s["zug"] or hq != s.get("co_hq") or ev.get("bezahlt") is not None:
        return
    k = s["kommandos"][hq]
    pool = k["verfuegbar"] + (k["gespart"] if opt(s, "U16_erste_commands_mit_gespart") else 0)
    n = min(ev["commands"], pool)
    rest = n
    ab = min(rest, k["verfuegbar"])
    k["verfuegbar"] -= ab
    rest -= ab
    k["gespart"] -= rest
    ev["bezahlt"] = n
    s.setdefault("impuls_ausgegeben", {})[hq] = s["impuls_ausgegeben"].get(hq, 0) + n
    prot.append(f"{hq}: {n} Command(s) spent on '{ev['id'].replace('_', ' ')}'" + (" (fewer than required, no penalty)" if n < ev["commands"] else "")
                + f", remaining {k['verfuegbar']}+{k['gespart']}" + offen(s, "U16_erste_commands_mit_gespart") + " [Normandy M1 p.18]")
    if n == ev["commands"] and ev.get("stern"):
        xp_buchen(s, xp_tab(s, "hq_ereignis_stern") or 1, f"HQ event {ev['id']} fulfilled", prot)


def ereignis_flanke_pruefen(s, prot):
    """At the end of the Friendly Command Phase: Company on the Flank / Screaming for Action fulfilled? (Normandy M1 p.18)"""
    ev = s.get("ereignis_flanke")
    if not ev or ev["zug"] != s["zug"] or ev["id"] == "trouble_flank" or ev.get("geprueft"):
        return
    ev["geprueft"] = True
    if ev.get("erfuellt"):
        prot.append(f"Event '{ev['id'].replace('_', ' ')}' fulfilled")
        if ev.get("stern"):
            xp_buchen(s, xp_tab(s, "hq_ereignis_stern") or 1, f"HQ event {ev['id']} fulfilled", prot)
    else:
        prot.append(f"Event '{ev['id'].replace('_', ' ')}' not fulfilled: mandatory if the Commands would have sufficed; no penalty for lack of Commands [3.1 p.15, Normandy M1 p.18]")


def bewegung_ereignis(s, e, ziel_k, prot):
    """Trouble on the Flank forbids, Company ahead/Screaming require the step onto a new row."""
    ev = s.get("ereignis_flanke")
    if not ev or ev["zug"] != s["zug"] or e["seite"] != "US" or s["phase"] not in IMPULSE:
        return
    zr = karte(s, ziel_k)["reihe"]
    if ev["id"] == "trouble_flank" and zr > us_front(s):
        raise Verstoss(f"Trouble on the Flank: no movement onto a new row ahead of row {us_front(s)} this turn [Normandy M1 p.18]")
    if ev["id"] in ("company_ahead", "screaming") and zr > ev["reihe"] and not ev.get("erfuellt"):
        if ev["id"] == "company_ahead" or karte(s, ziel_k).get("pc"):
            ev["erfuellt"] = True
            prot.append(f"Event '{ev['id'].replace('_', ' ')}' fulfilled (new row {zr}" + (", PC marker" if ev["id"] == "screaming" else "") + ")")


# ---------------------------------------------------------------- PC reveal/set, package placement Normandy (8.2.3, 8.4)
def cmd_pc_v4(s, args):
    if args[0] == "aufdecken":
        kid, b = args[1], args[2]
        c = karte(s, kid)
        if b not in ("A", "B", "C"):
            raise Verstoss("Letter A|B|C")
        prot = []
        if c.get("pc") == "?":
            c["pc"] = b
        elif c.get("pc2") == "?":
            c["pc2"] = b
        else:
            raise Verstoss(f"{kid} has no face-down PC marker")
        prot.append(f"PC marker on {kid} revealed: {b}")
        if c.get("pc2") and c["pc"] != "?" and c["pc2"] != "?":
            hoch, tief = min(c["pc"], c["pc2"]), max(c["pc"], c["pc2"])
            c["pc"] = hoch
            c.pop("pc2")
            prot.append(f"two PC markers on {kid}: the lower one ({tief}) is removed, {hoch} stays [8.2.3 p.62]")
        speichern(s, "; ".join(prot), "8.2.3 p.62")
        ausgabe(prot, s)
        return True
    if args[0] == "setzen":
        kid, b = args[1], args[2]
        c = karte(s, kid)
        if b not in ("A", "B", "C", "?"):
            raise Verstoss("A|B|C|?")
        if c.get("pc"):
            c["pc2"] = b
        else:
            c["pc"] = b
        prot = [f"PC marker {b} on {kid} (correction/event)"]
        speichern(s, "; ".join(prot), "8.2.3 p.62")
        ausgabe(prot, s)
        return True
    return False


RICHTUNG = {"Front": (1, 0), "Left Front": (1, -1), "Right Front": (1, 1), "Links": (1, -1), "Rechts": (1, 1)}


def platz_in_richtung(s, u, kid, richt, modus, reichweite_max):
    """[RULE 8.4.1-8.4.3 p.63, 8.4.5 p.65] Card along the direction: 'close' adjacent card, 'max' greatest distance with LOS/range,
    'max_los' greatest distance with LOS up to Very Long. Returns (card, None) or (None, missing extension) or (None, reason)."""
    dr, dc = RICHTUNG[richt]
    kt = karte(s, kid)
    dists = [1] if modus == "close" else list(range(1, reichweite_max + 1))
    beste, fehlt = None, None
    for d in dists:
        r, c = kt["reihe"] + dr * d, kt["spalte"] + dc * d
        k = karte_bei(s, r, c)
        if k is None:
            # extension only makes sense if the LOS up to the last existing card is not already blocked
            if fehlt is None and (d == 1 or los(s, karte_bei(s, kt["reihe"] + dr * (d - 1), kt["spalte"] + dc * (d - 1)), kid)[0]):
                fehlt = (r, c)
            break
        if not los(s, k, kid)[0]:
            if modus == "close":
                return None, f"no LOS {k} to {kid}"
            if d > 1 and not los(s, karte_bei(s, kt["reihe"] + dr * (d - 1), kt["spalte"] + dc * (d - 1)), kid)[0]:
                break                                                  # LOS stays blocked beyond (same intervening cards)
            continue
        if karte(s, k).get("staging"):
            continue
        beste = k
    if fehlt and (modus == "close" or opt(s, "U19_erweitern_bis_reichweite") or beste is None):
        return None, ("erweitern", fehlt)
    if beste is None:
        return None, "no card with LOS in this direction"
    return beste, None


def platz_pruefen_v4(s, u, k, kid, pk):
    """Placement restrictions 8.4.3 for a package unit on card k (trigger kid)."""
    if auf(s, k, "Feind") and not u.get("_gleiche_karte_ok"):
        return f"{k}: enemies already there (8.4.3 'Other Enemy Units')"
    ohne_pb = (u.get("cover") in STRUKTUR) or moerser(u)
    if k != kid and auf(s, k, "US") and not ohne_pb:
        return f"{k}: friendly units there (8.4.3)"
    if k != kid and any(auf(s, zw, "US") for zw in (linie(s, k, kid) or [])) and u.get("platz") not in ("max_los",) and not moerser(u):
        return f"{k}: friendly units between {k} and {kid} (8.4.3)"
    if feind_pdf_oder_vof(s, k):
        return f"{k}: {feind_pdf_oder_vof(s, k)} (8.4.3)"
    return None


def reichweite_von(u, pk):
    if u.get("platz") == "max_los":
        return 3                                                       # [RULE 8.4.3 p.63] Spotter/Patrol: Max LOS up to Very Long
    r = u.get("reichweite") or "V"
    return REICHWEITE.get(r.split("-")[-1], 3)


def liste_opt(o, key):
    v = o.get(key)
    return [x.strip() for x in v.split(",")] if v else []


def gebaeude_cover(s, platz, u, r8, wert_opt):
    """[CSR 8 p.15] Package in cover on Village/Farm/Cemetery/Church: R# on the building table; if the building value is equal to or better
    than the package cover, the unit goes inside; a worse result stays behind as a marker (BGG E21)."""
    tab = s.get("gebaeude_tabelle", {}).get(karte(s, platz).get("gebaeude_tabelle"), {})
    typ = next((t for b, t in tab.items() if r_passt(b, int(r8))), None)
    if typ is None:
        raise Verstoss(f"R# {r8} not in the building table (column 8)")
    oben = typ.endswith("*")
    typ = typ.rstrip("*")
    w = s.get("cover_werte", {}).get(typ)
    if w is None:
        if wert_opt is None:
            raise Verstoss(f"{typ}: cover value not recorded (UNVERIFIED); read it from the marker and give --building-value=<n> [CSR 8 p.15]")
        w = int(wert_opt)
    return typ, w, oben


def pc_kontakt_v4(s, kid, paket, pk, o):
    """[RULE 8.3 p.62, 8.4 p.63-65, Normandy M1 p.19] Package with direction (Unit Placement Table), distance, cover, Place PDF/VOF, Spotted."""
    c = karte(s, kid)
    prot = []
    trigger = [n for n in auf(s, kid, "US")]
    # ---- determine the package's units
    if pk.get("wahl"):
        w = o.get("--wahl")
        if w not in pk["wahl"]:
            raise Verstoss(f"Package {paket}: choice by R# ({' or '.join(pk['wahl'])}) and --choice=<{ '|'.join(pk['wahl'])}> [8.3 p.62]")
        einh = copy.deepcopy(pk["wahl"][w])
        prot.append(f"Random package choice: {w} [8.3 p.62]")
    else:
        einh = copy.deepcopy(pk.get("einheiten", []))
    opt_units = [u for u in einh if u.get("optional_r")]
    if opt_units:
        z = o.get("--zusatz")
        if z not in ("ja", "nein"):
            raise Verstoss(f"Package {paket}: extra unit on R# {opt_units[0]['optional_r']} (random number column 2, BGG B4): --extra=yes|no")
        if z == "nein":
            einh = [u for u in einh if not u.get("optional_r")]
    # only if available (leader)
    for u in list(einh):
        if u.get("nur_wenn_verfuegbar") and im_spiel_zahl(s, u["einheit"]) >= cm_zahl(s, u["einheit"]):
            einh.remove(u)
            prot.append(f"{u['einheit']} not available, omitted (p.19 'only if available')")
    # R#-dependent placement
    if any(u.get("platz") == "r" for u in einh):
        rp = pk["r_platz"]
        r = o.get("--r")
        if not r:
            raise Verstoss(f"Package {paket}: placement by R# column {rp.get('spalte', 10)} ({', '.join(f'{b}: {m}' for b, m in rp.items() if b != 'spalte')}); --r=<R#>")
        modus = next(m for b, m in rp.items() if b != "spalte" and r_passt(b, int(r)))
        for u in einh:
            if u.get("platz") == "r":
                u["platz"] = modus
        prot.append(f"R# {r}: placement {modus} [Normandy M1 p.19]")
    # variant (Incoming Artillery/Mortar)
    var = None
    if pk.get("varianten"):
        vn = o.get("--variante")
        if vn not in pk["varianten"]:
            raise Verstoss(f"Package {paket}: draw a card, 1 = {list(pk['varianten'])[0]}, 2 = {list(pk['varianten'])[1]} (BGG B4); --variant=<{'|'.join(pk['varianten'])}>")
        var = pk["varianten"][vn]
        prot.append(f"Variant {vn} (Incoming {var['wert']:+d}) [Normandy M1 p.19]")
        if var.get("ohne_einheiten"):
            einh = []
            prot.append("without Spotter (Normandy M2 p.23: 'Artillery -4 with no Spotter')")
    # ---- counter types (countermix, 8.3)
    bedarf, typen = {}, []
    typ_liste, vof_liste, rw_liste = liste_opt(o, "--typ"), liste_opt(o, "--vof"), liste_opt(o, "--reichweite")
    for u in einh:
        namen = u.get("einheit_wahl") or [u["einheit"]]
        frei = [x for x in namen if im_spiel_zahl(s, x) + bedarf.get(x, 0) < cm_zahl(s, x)]
        if not frei:
            raise Verstoss(f"Package {paket} cannot be placed: no free counter for {'/'.join(namen)}; redraw the package (8.3 p.62, Normandy p.19 'Redraw', E6)")
        if len(frei) > 1:
            if not typ_liste:
                raise Verstoss(f"Choose the counter randomly (R#/{len(frei)}) from {', '.join(frei)}; --type=<name>[,<name> for further squads] [Normandy M1 p.16]")
            w = typ_liste.pop(0)
            if w not in frei:
                raise Verstoss(f"{w} not free; free: {', '.join(frei)}")
            frei = [w]
        bedarf[frei[0]] = bedarf.get(frei[0], 0) + 1
        typen.append(frei[0])
    for u, t in zip(einh, typen):
        u.update(u.get("varianten", {}).get(t, {}))
        u["typname"] = t
        if u.get("vof_rating", "x") is None and u["typ"] not in ("Spotter", "HQ"):
            bekannt = (s.get("counter_vof") or {}).get(t)
            if bekannt:
                u["vof_rating"] = bekannt
                prot.append(f"{t}: VOF {bekannt} per counter (recorded)")
            else:
                if not vof_liste:
                    raise Verstoss(f"{t}: VOF rating not recorded (UNVERIFIED); read it from the counter: --vof=<A|S|H..>[,...] [Normandy p.48]")
                u["vof_rating"] = vof_liste.pop(0)
                s.setdefault("counter_vof", {})[t] = u["vof_rating"]
                prot.append(f"{t}: VOF {u['vof_rating']} per counter (recorded for future contacts)")
        if u.get("vof_rating") == "A" and u.get("munition_wenn_a") and not u.get("munition"):
            u["munition"] = copy.deepcopy(u["munition_wenn_a"])
            u["letzter_step_werte"] = {"vof_rating": "A", "reichweite": "C"}
        if u.get("vof_rating") == "A/S" and u.get("fj_breakdown") and not u.get("letzter_step_werte"):
            u["letzter_step_werte"] = {"vof_rating": "A/S", "reichweite": "C"}     # [Normandy p.48] A/S FJ: last step Fire Team A/S • C
        if u.get("reichweite", "x") is None:
            if not rw_liste:
                raise Verstoss(f"{t}: range not recorded (UNVERIFIED); read it from the counter: --range=<C|L|V>[,...]")
            u["reichweite"] = rw_liste.pop(0)
            prot.append(f"{t}: range {u['reichweite']} per counter")
    # ---- determine cards
    richt_liste = [{"Links": "Left Front", "Rechts": "Right Front"}.get(x, x) for x in liste_opt(o, "--richtung")]
    platz_liste = liste_opt(o, "--platz")
    plaetze = []
    eigene = [u for u in einh if u["platz"] in ("max", "close", "max_los")]
    if len(set(richt_liste)) < len(richt_liste):
        raise Verstoss("Duplicate direction: redraw (FM2 p.10, 8.4.3 'Redraw if an invalid Direction is chosen')")
    rt = s.get("richtung_tabelle", {})
    for idx, u in enumerate(einh):
        m = u["platz"]
        if m in ("pb", "trigger"):
            plaetze.append(kid)
            continue
        if m in ("mit_vorigem", "bei_squad"):
            bezug = 0
            if m == "bei_squad":
                b = o.get("--bei")
                if b not in ("1", "2"):
                    raise Verstoss("HMG in bunker on the card of a squad: --at=1|2 (random) [Normandy M1 p.19]")
                bezug = int(b) - 1
            else:
                bezug = idx - 1
            plaetze.append(plaetze[bezug])
            continue
        j = eigene.index(u)
        if j >= len(richt_liste):
            raise Verstoss(f"Direction per unit on its own card by R# column {rt.get('spalte', 8)} ({', '.join(f'{b} {v}' for b, v in rt.items() if b != 'spalte')}): --direction=Front|Left|Right[,..] [8.4.2 p.63]")
        richt = richt_liste[j]
        if richt not in RICHTUNG:
            raise Verstoss("Direction Front | Left | Right")
        hi = reichweite_von(u, pk)
        if u.get("spotter") or u.get("typ") == "Spotter":
            hi = 3
        if platz_liste and j < len(platz_liste):
            k = platz_liste[j]
            karte(s, k)
            if k == kid and m != "close":
                # [RULE 8.4.3 p.64] Point Blank placement on the trigger card if no card in the direction is valid
                if not (u.get("spotter") or u.get("typ") == "Spotter") and not (u.get("cover") in STRUKTUR or moerser(u)):
                    plaetze.append(k)
                    continue
                raise Verstoss(f"{ziel_name if False else u['einheit']}: Point Blank placement on {kid} not possible (Spotter/structure/mortar) [8.4.3]")
            if richtung(s, kid, k) != RICHTUNG[richt] or abstand(s, kid, k) > hi or (m == "close" and abstand(s, kid, k) != 1) or not los(s, k, kid)[0]:
                raise Verstoss(f"{k} is not in direction {richt} within LOS/range of {kid} [8.4.2/8.4.3 p.63]")
        else:
            kands, fehlt = [], None
            dr, dc = RICHTUNG[richt]
            kt = karte(s, kid)
            los_ok, letzte = True, kid                                 # LOS still open up to the last existing card?
            for d in ([1] if m == "close" else range(1, hi + 1)):
                kk = karte_bei(s, kt["reihe"] + dr * d, kt["spalte"] + dc * d)
                if kk is None:
                    # extension only if a new card there could have LOS: chain so far in LOS and
                    # (reading a: always, Hill possible) or (reading b: the last card lets LOS pass through it) [8.4.5, U19]
                    if los_ok and (d == 1 or opt(s, "U19_erweitern_bis_reichweite") or durchsicht(karte(s, letzte), (-dr, -dc), (dr, dc)) is not False):
                        fehlt = (kt["reihe"] + dr * d, kt["spalte"] + dc * d)
                    break
                letzte = kk
                los_ok = los(s, kk, kid)[0]
                if not los_ok and d > 1:
                    break
                if los_ok and not platz_pruefen_v4(s, u, kk, kid, pk) and not karte(s, kk).get("staging"):
                    kands.append(kk)
            if fehlt and (m == "close" or not kands or opt(s, "U19_erweitern_bis_reichweite")):
                raise Verstoss(f"Direction {richt}: card row {fehlt[0]} column {fehlt[1]} missing; draw a terrain card and fof.py extend {fehlt[0]} {fehlt[1]} <type>, then repeat the contact"
                               + ("" if m == "close" else offen(s, "U19_erweitern_bis_reichweite")) + " [8.4.5 p.65]")
            if not kands:
                raise Verstoss(f"Direction {richt}: no valid card (LOS/range/8.4.3); redraw the direction, if none is possible, redraw the package [8.4.3 p.64]")
            k = kands[-1]
        grund = platz_pruefen_v4(s, u, k, kid, pk) if k not in plaetze else None
        if grund:
            raise Verstoss(grund + "; redraw the direction or the package [8.4.3 p.64]")
        plaetze.append(k)
        prot.append(f"{u['typname']}: direction {richt}, {'Close Range' if m == 'close' else 'Max LOS/Range' if m == 'max' else 'Max LOS'} = card {k} [8.4.1-8.4.3 p.63]")
    # ---- markers (Mines, Incoming) onto the trigger card
    for mk in pk.get("marker", []):
        if mk["typ"] == "Illum":
            # [Normandy M3 p.27, 9.2 p.70] Mortar Illumination on the trigger card
            iv = (s.get("illum_werte") or {}).get(mk.get("quelle", "Mortar Illum"))
            if o.get("--illum"):
                ob, _, un = o["--illum"].partition("/")
                iv = {"oben": int(ob), "unten": int(un) if un else None}
            if not iv:
                raise Verstoss("Read the illumination values (Mortar Illumination) from the marker: --illum=<top>/<bottom> [9.2]")
            c.setdefault("illum", []).append({"oben": iv["oben"], "unten": iv.get("unten"), "quelle": f"Feind {mk.get('quelle', 'Mortar Illum')}"})
            prot.append(f"Illumination marker {iv['oben']:+d}" + (f"/{iv['unten']:+d}" if iv.get("unten") is not None else "") + f" on {kid} (enemy, Mortar Illumination) [9.2]")
            continue
        wert = mk["wert"] if mk["wert"] is not None else (var or {}).get("wert", -3)
        c.setdefault("extern", []).append({"typ": mk["typ"], "wert": wert, "quelle": pk["name"], "seite": "Feind", "aktiv": mk["typ"] != "Mines"})
        if mk["typ"] == "Mines":
            prot.append(f"Mines! marker (Draw 3 side, VOF {wert}) on {kid}; every unit on {kid} checks immediately [8.7.1 p.67]")
        else:
            prot.append(f"Incoming! marker (active, VOF {wert}) on {kid}; first fire mission automatic, blocks LOS out of {kid} [8.10 p.68, 5.4]")
            for n, e in s["einheiten"].items():
                if e["karte"] == kid and feuert(e) and e["ziel"] != kid:
                    e["ziel"] = None
                    prot.append(f"{n} loses LOS out of the card, remove PDF [6.1.2]")
    # ---- place units
    neue, cid_vorig = [], {}
    geb_liste = liste_opt(o, "--gebaeude")
    for idx, (u, platz) in enumerate(zip(einh, plaetze)):
        t = u["typname"]
        cid = None
        if u["platz"] == "mit_vorigem" and cid_vorig.get(idx - 1) and not u.get("eigene_deckung"):
            cid = cid_vorig[idx - 1]
        elif u.get("cover") and not u.get("ohne_deckung") and not u.get("infiltration"):
            ctyp, cwert = u["cover"], u.get("cover_wert", 1)
            if karte(s, platz).get("gebaeude_tabelle") and ctyp not in STRUKTUR:
                if not geb_liste:
                    raise Verstoss(f"{t} in cover on {karte(s, platz)['terrain']}: R# column 8 on the building table, --building=<R#>[,..] [CSR 8 p.15]")
                gt, gw, oben = gebaeude_cover(s, platz, u, geb_liste.pop(0), o.get("--gebaeude_wert"))
                if gw >= cwert:
                    ctyp, cwert = gt, gw
                    prot.append(f"Building cover {gt} (+{gw}) instead of {u['cover']} [CSR 8 p.15]" + (" (Upper Story/Church Tower for Sniper/Spotter)" if oben and u["typ"] in ("Sniper", "Spotter") else ""))
                else:
                    gid = neuer_cover(s, platz, gt, gw)
                    prot.append(f"Building {gt} (+{gw}) worse than {u['cover']}: marker {gid} stays on {platz} (BGG E21)")
            cid = neuer_cover(s, platz, ctyp, cwert)
            cv = [x for x in karte(s, platz)["cover"] if x["id"] == cid][0]
            if u.get("cover_kapazitaet"):
                cv["kapazitaet"] = u["cover_kapazitaet"]
            if ctyp in STRUKTUR and platz != kid:
                cv["richtung"] = list(richtung(s, platz, kid))
            prot.append(f"{ctyp} marker {cid} (+{cwert}) on {platz}")
        cid_vorig[idx] = cid
        spotted = bool(u.get("spotted", pk.get("spotted")))
        e = {"typ": u.get("typ", "Weapons Team"), "typname": t, "seite": "Feind", "erfahrung": u.get("erfahrung", "Line"), "karte": platz,
             "bereich": cid or "offen", "status": [], "steps": u.get("steps", 1), "vof_rating": u.get("vof_rating"), "reichweite": u.get("reichweite") or "L",
             "spotted": spotted, "paket": paket, "pc_herkunft": c.get("pc"), "fire_team_seite": u.get("fire_team_seite", u.get("steps", 1) == 1),
             "ft_vof": u.get("ft_vof") or "S", "letzter_step": u.get("letzter_step"), "ziel": None, "kein_point_blank": u.get("cover") in STRUKTUR}
        for f in ("munition", "letzter_step_werte", "ft_reichweite", "moerser", "grenade_ranged", "tripod", "leader", "unbeweglich", "breakdown_hinweis", "spotter", "fj_breakdown", "breakdown", "rifle_grenades"):
            if u.get(f) is not None:
                e[f] = copy.deepcopy(u[f])
        if e.get("spotter") or u.get("typ") == "Spotter":
            e["spotter"] = True
            e["missionen"] = (var or {}).get("missionen", 2) - 1          # [BGG E19] the automatic first mission counts
            e["karten_folge"] = (var or {}).get("karten_folge", 3)
            e["fm_wert"] = (var or {}).get("wert", -3)
            s.setdefault("feind_target", {})[t] = kid
        if u.get("infiltration"):
            if o.get("--erfolg") not in ("ja", "nein"):
                raise Verstoss(f"Patrol (CSR 6): Infiltrate Attempt, 2 cards (experience {e['erfahrung']}), Infiltrate symbol; --success=yes|no [CSR 6 p.14]")
            if o["--erfolg"] == "ja":
                frei = [x for x in karte(s, platz).get("cover", []) if not any(s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == x["id"] for m in auf(s, platz))]
                if frei:
                    e["bereich"] = max(frei, key=lambda x: x["wert"])["id"]
                prot.append(f"Patrol successful: not Exposed" + (f", under {e['bereich']}" if e["bereich"] != "offen" else "") + " [CSR 6 p.14]")
            else:
                markieren(e, "Exposed")
                prot.append("Patrol failed: without cover and Exposed [CSR 6 p.14]")
        if u.get("exposed"):
            markieren(e, "Exposed")
            prot.append(f"{t}: Exposed, without cover [Normandy M3 p.27 'Squad marked Exposed out of cover']")
        fname = neuer_name(s, t)
        s["einheiten"][fname] = e
        if cid and [x for x in karte(s, platz)["cover"] if x["id"] == cid][0]["typ"] == "Deep Bunker":
            e["deep_bunker"] = cid
            prot.append(f"{fname} in Deep Bunker {cid}: no VOF, no spotting, no Pyro, no grenades; leaves it on Fall Back or Grenade Attack in 3.4.2 (then --area=open) [CSR 5 p.14]")
        if cid and [x for x in karte(s, platz)["cover"] if x["id"] == cid][0]["typ"] in STRUKTUR:
            e["bunker_richtung"] = kid
            prot.append(f"Arrow toward {kid}; fires only in this direction, never Point Blank; redraw Shift results [5.3.2]")
        prot.append(f"Enemy {fname} ({t}, VOF {e['vof_rating']}, {e['steps']} step(s)" + (f", {e['munition']['punkte']} {e['munition']['typ']}" if e.get("munition") else "")
                    + f") on {platz}" + (f" under {e['bereich']}" if e["bereich"] != "offen" else " without cover") + (", Spotted" if spotted else ", place Unspotted marker"))
        # Place PDF/VOF
        if not pk.get("place_vof", True):
            e["kein_feuer_bis_clean_up"] = True
            prot.append(f"{fname}: Place PDF/VOF No, opens fire only in Clean Up [8.3 p.63]")
        elif e.get("vof_rating") == "G":
            g = o.get("--granate")
            if g not in ("ja", "nein"):
                raise Verstoss(f"{fname} (G!) opens with a Grenade Attack on {kid}: 2 cards (experience), Grenade symbol (watch for Jam); --grenade=yes|no [--unit=<target>] [8.4.3 p.63, 7.3.2]")
            e["ziel"], e["nur_pdf"] = kid, True
            muni_verbrauch(s, fname, e, 1, "Grenade Attack at range", prot)
            if g == "ja":
                ze = o.get("--einheit") or (trigger[0] if len(trigger) == 1 else None)
                if not ze:
                    raise Verstoss("--unit=<target of the Grenade Attack> (stack under cover or random unit without cover)")
                einheit(s, ze).setdefault("grenade", []).append(s.get("granate_vof", -4))
                prot.append(f"{fname}: PDF to {kid}, Grenade VOF {s.get('granate_vof', -4)} on {ze} [7.3.2 p.53, 7.10]")
            else:
                c["grenade_miss"] = True
                prot.append(f"{fname}: PDF to {kid}, Grenade Miss (-1) on {kid} [7.10.4]")
        elif e.get("vof_rating"):
            e["ziel"] = kid
            prot.append(f"{fname} opens fire on {kid}" + ("" if platz == kid else f", PDF from {platz} to {kid}" + pdf_hinweis(s, platz, kid, fname)) + (" (Small Arms on the card, Sniper VOF -3 on one target in 3.7.4)" if ist_sniper(e) else "") + " [8.4.3]")
        neue.append(fname)
    # PC markers overshot (8.4.4)
    for fname in neue:
        e = s["einheiten"][fname]
        if feuert(e) and e["ziel"] != e["karte"]:
            for zw in (linie(s, e["karte"], kid) or []):
                if karte(s, zw).get("pc") and karte(s, zw).get("elevation", 1) == karte(s, e["karte"]).get("elevation", 1):
                    karte(s, zw)["pc"] = None
                    prot.append(f"PC marker on {zw} removed (overshot) [8.4.4]")
    # Point Blank fire of friendly units on the placement card, return fire on Spotted
    for fname in neue:
        e = s["einheiten"][fname]
        if e["spotted"]:
            for m, f in s["einheiten"].items():
                if f["seite"] == "US" and f["karte"] == e["karte"] and feuert(f) and f["ziel"] != e["karte"] and not kein_pb(s, f):
                    f["ziel"] = e["karte"]
                    prot.append(f"{m} shifts fire onto its own card (Point Blank) [6.1.2]")
    if any(s["einheiten"][f]["spotted"] for f in neue):
        feuer_eroeffnen(s, prot)
    elif neue:
        prot.append("Enemy Unspotted: no return fire, spot first [8.5, 6.1.1]")
    if any(mk["typ"] == "Mines" for mk in pk.get("marker", [])):
        minencheck_anfordern(s, auf(s, kid), kid, prot, "Mines package")
    c["pc"] = None                                                                   # v4: availability only via the countermix (8.3)
    prot.append(f"Remove PC marker from {kid} [8.2.4]")
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    speichern(s, f"Contact on {kid}: package {paket} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    ausgabe(prot, s)


# ---------------------------------------------------------------- Enemy v4: Sniper, Spotter, Offensive Assault, Leader (8.6-8.10)
def feind_zeile_v4(s, n):
    """Returns a hierarchy row for cases v3 does not know, otherwise None."""
    e = s["einheiten"][n]
    kid = e["karte"]
    if e.get("ooa_fallback") and ft_seite(e) and e.get("spotted"):
        return "O-A Out-of-Ammo team on Fire Team side, Spotted: Fall Back instead of hierarchy [8.11 p.68]", "Auto", {"Auto": "Fall Back"}
    if pinned(e) or ist_lat(e) or ft_seite(e):
        return None
    if ist_sniper(e):
        cv = cover_marker(s, e)
        if cv and cv["typ"] in ("Foxholes", "Trench", "Bunker", "Pillbox", "Deep Bunker", "Cave"):
            return "S3 Sniper in a field fortification stays put even when Spotted [8.8 Exception]", "Auto", {"Auto": "No Action"}
        if e.get("spotted"):
            return "S1 Sniper Spotted: Fall Back until out of LOS, then Unspotted again [8.8 p.67]", "Auto", {"Auto": "Fall Back"}
        return "S2 Sniper Unspotted: fires by target priority or does nothing [8.8 p.67]", "Auto", {"Auto": "No Action"}
    if e.get("spotter"):
        if e.get("missionen", 0) <= 0:
            return "SP0 Spotter without fire missions: remove [8.10 p.68]", "Auto", {"Auto": "Remove (no fire missions left)"}
        z = spotter_ziel(s, n)
        if not z:
            return "SP2 Spotter without target in LOS: nothing [8.10 p.68]", "Auto", {"Auto": "No Action"}
        tk = s.get("feind_target", {}).get(e.get("typname"))
        k = e.get("karten_folge", 3) + (1 if tk == z else 0)
        return (f"SP1 Spotter: Call for Fire on {z} ({k} cards{' incl. +1 Target marker' if tk == z else ''}, burst symbol; experience already included) [8.10 p.68]",
                "Auto", {"Auto": f"Call for Fire --ziel={z}"})
    return None


def spotter_ziel(s, n):
    """[RULE 8.10 p.68] Priority: Target Marker card, vehicle, most steps, nearest card, random."""
    e = s["einheiten"][n]
    kand = [k for k in s["karten"] if auf(s, k, "US") and not karte(s, k).get("staging") and (k == e["karte"] or los(s, e["karte"], k)[0])]
    if not kand:
        return None
    tk = s.get("feind_target", {}).get(e.get("typname"))
    if tk in kand:
        return tk
    st = {k: sum(steps(s["einheiten"][m]) for m in auf(s, k, "US")) for k in kand}
    best = max(st.values())
    kand = [k for k in kand if st[k] == best]
    d = min(abstand(s, e["karte"], k) for k in kand)
    kand = [k for k in kand if abstand(s, e["karte"], k) == d]
    if len(kand) > 1:
        s.setdefault("_hinweise", []).append(f"Spotter targets tied: {', '.join(kand)}; choose by R# [8.10]")
    return kand[0]


def feind_zeile_offensiv(s, n, gegner_da, cover, feuert_):
    """[PLAYER AID Enemy Offensive Activity Check Hierarchy] Columns Assault and Overrun."""
    e = s["einheiten"][n]
    ov = s.get("feind_taktik") == "Overrun"
    if gegner_da and not cover:
        return ("O1 on a card with opposing units, without cover", "6" if ov else "5",
                {"1": "No Action", "2": "Fall Back", "3-4": "Advance Straight Ahead", "5-6": "Grenade Attack"} if ov else
                {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back", "5": "Grenade Attack"})
    if gegner_da:
        return ("O2 on a card with opposing units, under cover", "6" if ov else "5",
                {"1": "No Action", "2": "Fall Back", "3-4": "Advance Straight Ahead", "5-6": "Grenade Attack"} if ov else
                {"1": "No Action", "2": "Fall Back", "3-5": "Grenade Attack"})
    if e.get("out_of_ammo") and e.get("vof_rating") in ("A", "G", "H"):
        return ("O3 A/G!/H with Out of Ammo", "2" if ov else "3", {"1": "No Action", "2": "Advance Straight Ahead"} if ov else {"1-2": "No Action", "3": "Fall Back"})
    if e.get("vof_rating") in ("A", "G", "H") and (feuert_ or (e.get("vof_rating") == "G" and feuerkandidaten_g(s, n))):
        return ("O4 A/G!/H with a valid target along PDF", "4" if ov else "Auto",
                {"1": "No Action", "2-3": "Grenade Attack (or Concentrate Fire)", "4": "Advance Straight Ahead"} if ov else {"Auto": "Grenade Attack (or Concentrate Fire)"})
    return ("O5 all other cases", "3" if ov else "4",
            {"1": "Infiltrate towards closest opposing unit", "2-3": "Advance Straight Ahead"} if ov else
            {"1": "No Action", "2-3": "Infiltrate towards closest opposing unit", "4": "Advance Straight Ahead"})


def feuerkandidaten_g(s, n):
    """G! unit without PDF: target in LOS and range (player aid: 'Also applies to a G! rated unit on a card with no PDF, but with a target in LOS')."""
    e = s["einheiten"][n]
    return [k for k in s["karten"] if k != e["karte"] and gueltiges_ziel(s, k, e["seite"]) and in_reichweite(s, e, k) and los(s, e["karte"], k)[0]]


def leader_da(s, e):
    """[RULE 8.9 p.67] Good Order leader in Visual-Verbal (same card, same area)."""
    return any(x.get("leader") and x["seite"] == e["seite"] and x["karte"] == e["karte"] and x.get("bereich", "offen") == e.get("bereich", "offen")
               and good_order(x) and x is not e for x in s["einheiten"].values())


LAT_MIT_LEADER = {
    "P1": ("4", {"1-2": "Move into or Seek Cover", "3": "Rally", "4": "Fall Back"}),
    "P2": ("3", {"1": "No Action", "2-3": "Rally"}),
    "P3": ("3", {"1": "No Action", "2": "Move into or Seek Cover", "3": "Rally"}),
    "P4": ("Auto", {"Auto": "Rally"}),
    "P6": ("Auto", {"Auto": "Grenade Attack"}),
    "P7": ("3", {"1": "No Action", "2-3": "Infiltrate to nearest opponent"}),
    "P8": ("4", {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back"}),
    "P9": ("3", {"1": "No Action", "2": "Grenade Attack", "3": "Fall Back"}),
    "P10": ("Auto", {"Auto": "Rally"}),
    "P11": ("Auto", {"Auto": "Rally"}),
    "P12": ("Auto", {"Auto": "Fall Back with Casualty"}),
    "P13": ("2", {"1": "No Action", "2": "Move towards closest Casualty"}),
    "P14": ("2", {"1": "No Action", "2": "Rally"}),
    "P15": ("2", {"1": "No Action", "2": "Rally"}),
}


# ---------------------------------------------------------------- Prisoners (3.5.1, 8.15; Normandy: both sides)
def cmd_gefangen(s, args):
    """[RULE 3.5.1 p.16, 8.15 p.69, Normandy p.13 'Both sides take prisoners'] Paralyzed/Litter Team alone with unpinned infantry with VOF:
    one guard step and the prisoners are Removed from Play."""
    if s["phase"] != "3.5.1":
        raise Verstoss("Taking prisoners only in the Capture Segment 3.5.1")
    g, w = args[0], args[1]
    ge, we = einheit(s, g), einheit(s, w)
    if ge["typ"] not in ("Paralyzed Team", "Litter Team"):
        raise Verstoss(f"{g} is not a Paralyzed/Litter Team [3.5.1]")
    if [m for m in auf(s, ge["karte"], ge["seite"]) if m != g]:
        raise Verstoss(f"{g} is not alone on {ge['karte']} [3.5.1]")
    LATS = ("Fire Team", "Assault Team", "Paralyzed Team", "Litter Team")
    faenger = [m for m in auf(s, ge["karte"], gegner(ge["seite"]))
               if (s["einheiten"][m]["typ"] not in LATS) or (s["einheiten"][m]["typ"] in ("Fire Team", "Assault Team") and not pinned(s["einheiten"][m]))]
    if not faenger:
        raise Verstoss(f"On {ge['karte']} there is no Good Order unit and no unpinned Assault/Fire Team of the opposing side [RULE 8.15 p.69]")
    if we["karte"] != ge["karte"] or we["seite"] == ge["seite"] or not we.get("vof_rating"):
        raise Verstoss(f"Guard {w}: one step of an opposing unit with a printed VOF on the same card [RULE 8.15 p.69]")
    if ge["seite"] == "Feind" and not v4(s):
        pass
    prot = []
    st = steps(ge)
    del s["einheiten"][g]
    if steps(we) > 1:
        we["steps"] -= 1
        prot.append(f"{w} details one step as guard (now {we['steps']} steps), guard Removed from Play [8.15]")
        if steps(we) == 1 and we.get("letzter_step"):
            neu = neuer_name(s, we["letzter_step"])
            s["einheiten"][neu] = lat_neu(we, we["letzter_step"], w)
            s["einheiten"][neu]["status"] = []
            entfernen_rfp(s, w, prot, f"last step becomes {we['letzter_step']} ({neu})", nachfolger=neu)
    else:
        entfernen_rfp(s, w, prot, "detached as guard [8.15]")
    if ge["seite"] == "Feind":
        s["gefangene"] = s.get("gefangene", 0) + st
        xp_buchen(s, st * (xp_tab(s, "gefangene_step") or 2), f"{st} prisoners ({g})", prot)
    else:
        s["us_gefangen"] = s.get("us_gefangen", 0) + st
    prot.insert(0, f"{g} ({ge['seite']}) captured, Removed from Play")
    m = aktivitaet_berechnen(s)
    if m:
        prot.append(m)
    speichern(s, "; ".join(prot), "3.5.1 p.16, 8.15 p.69")
    ausgabe(prot, s)


# ---------------------------------------------------------------- Experience, objective, mission end (12.1, 3.9)
def geklaert(s, k):
    """[RULE 12.1 p.81] Cleared: the card started with a PC marker and now has neither enemies (except casualties) nor a PC marker."""
    c = karte(s, k)
    return bool(s.get("pc_start", {}).get(k)) and not c.get("pc") and not auf(s, k, "Feind")


def gesichert(s, k):
    return geklaert(s, k) and bool(auf(s, k, "US"))


def ziel_stand_v4(s):
    z = s.get("ziele", {})
    zr = s["ziel_regeln"]
    teile, ok = [], True
    for key in zr.get("sichern", []):
        k = z.get(key)
        g = bool(k) and gesichert(s, k)
        ok &= g
        teile.append(f"{ {'primaer': 'Primary', 'sekundaer': 'Secondary'}.get(key, key)} {k or '-'} {'secured' if g else 'open'}")
    for r in zr.get("reihen_klaeren", []):
        ks = [k for k, c in s["karten"].items() if c["reihe"] == r and not c.get("ausserhalb") and not c.get("staging")]
        offen_ = [k for k in ks if not geklaert(s, k)]
        ok &= not offen_
        teile.append(f"Row {r} " + ("cleared" if not offen_ else "open (" + ", ".join(offen_) + ")"))
    return ok, "; ".join(teile)


def xp_missionsende(s, prot):
    """Card points at the end of an attempt, no card twice per mission (3.9 step 1 note, 12.1; Errata 4)."""
    tab = s["kampagne"].get("xp_tabelle", {})
    vergeben = s.setdefault("xp_karten", [])
    z = s.get("ziele", {})
    sonder = {z.get("primaer"): ("primaer", "Primary Objective secured"), z.get("sekundaer"): ("sekundaer", "Secondary Objective secured"),
              z.get("ap"): ("ap", "Attack Position secured")}
    for k in sorted(s["karten"]):
        c = s["karten"][k]
        if c.get("staging") or c.get("ausserhalb") or k in vergeben:
            continue
        if k in sonder and k:
            if gesichert(s, k):
                xp_buchen(s, tab.get(sonder[k][0], 0), f"{sonder[k][1]} ({k})", prot)
                vergeben.append(k)
            continue
        if geklaert(s, k):
            pc = s["pc_start"][k]
            xp_buchen(s, tab.get("pc_a_karte", 2) if pc == "A" else tab.get("pc_bc_karte", 1), f"Card {k} with PC {pc} cleared", prot)
            vergeben.append(k)


def missionsende_v4(s, prot):
    if s.get("patrouille_mission"):
        return patrouille_ende(s, prot)
    ok, txt = ziel_stand_v4(s)
    xp_missionsende(s, prot)
    s["missionsende"] = True
    k = s["kampagne"]
    prot.append("Mission objective: " + txt + (" ACHIEVED" if ok else " NOT achieved"))
    if ok:
        vet = s.get("us_casualties_gesamt", 0) // k.get("veteran_je_casualties", 4)
        prot.append(f"Mission successful. Between missions (12.2 p.81): spend {sum(x['punkte'] for x in s.get('xp', []))} Experience points, "
                    f"replacements {k.get('ersatz_green', 6)} Green plus {vet} Veteran ({s.get('us_casualties_gesamt', 0)} casualty steps over the whole mission, 1 per 4) [12.4 p.81, Normandy p.13]; "
                    "replace ammo and assets completely (BGG E14)")
    elif k.get("versuch", 1) < k.get("versuche_max", 1) and opt(s, "U9_reattempt"):
        prot.append(f"Reattempt possible (attempt {k['versuch']} of {k['versuche_max']}): fof.py reattempt [3.9 p.17]")
    else:
        prot.append("No attempts left: mission failed (12.8 standard: the commander is relieved; Survivor mode: continue with the next mission) [12.8 p.82]")


# ---------------------------------------------------------------- Combat Patrol (2.6, Normandy M3 MSR 1-4)
def pat(s):
    return s.get("patrouille") or {}


def patrouille_bewegung(s, n, von, ziel_k, prot):
    """[MSR 2] Route Points in order, pass the Primary, return across the MLR from row 2 to row 1."""
    p = pat(s)
    if not p or p.get("erfolg"):
        return
    if n not in p.get("mitglieder", []):
        # [Normandy M3 p.24 'at least one unit'; BGG 3760839: also LAT, Staff, HQ of the patrol] LATs from patrol units count too
        if s["einheiten"].get(n, {}).get("herkunft") in p.get("mitglieder", []):
            p.setdefault("mitglieder", []).append(n)
        else:
            return
    z = s.get("ziele", {})
    route = [z.get("route", {}).get(str(i)) for i in (1, 2, 3, 4)]
    i = p.get("route_index", 0)
    if i < 4 and route[i] == ziel_k:
        p["route_index"] = i + 1
        prot.append(f"Route Point {i + 1} on {ziel_k} reached: remove marker [MSR 2]")
        xp_buchen(s, xp_tab(s, "cp_route") or 1, f"Route Point {i + 1} ({ziel_k}), patrol Platoon {p['platoon']}", prot)
        # [BGG Shonai_Dweller 3552585, 3520262] if a patrol unit already stands on the next Route Point, it is taken at once as well
        while p["route_index"] < 4:
            j = p["route_index"]
            da = [m for m in p.get("mitglieder", []) if m in s["einheiten"] and s["einheiten"][m].get("karte") == route[j]]
            if not da:
                break
            p["route_index"] = j + 1
            prot.append(f"Route Point {j + 1} on {route[j]}: {', '.join(da)} already there, remove marker [MSR 2, BGG 3552585]")
            xp_buchen(s, xp_tab(s, "cp_route") or 1, f"Route Point {j + 1} ({route[j]}), patrol Platoon {p['platoon']}", prot)
    er = s.get("ereignis_route")
    if er and er.get("zug") == s["zug"] and not er.get("erfuellt") and er.get("ziel") and abstand(s, ziel_k, er["ziel"]) < abstand(s, von, er["ziel"]):
        er["erfuellt"] = True
        prot.append(f"CO HQ is Screaming for Action fulfilled: {n} moves toward {er['ziel']} [Normandy M3 p.26]")
        xp_buchen(s, 1, "HQ event CO HQ is Screaming for Action fulfilled", prot)
    if ziel_k == z.get("primaer") and not p.get("primaer_besucht"):
        p["primaer_besucht"] = True
        prot.append(f"Primary Objective {ziel_k} passed [Normandy M3 p.24]")
    if p.get("route_index", 0) == 4 and p.get("primaer_besucht") and karte(s, von)["reihe"] == 2 and karte(s, ziel_k)["reihe"] == 1:
        p["erfolg"] = True
        prot.append(f"Patrol successful: {n} crosses the MLR from row 2 to row 1 [Normandy M3 p.24]")
        xp_buchen(s, xp_tab(s, "cp_erfolg") or 5, f"Patrol Platoon {p['platoon']} successful", prot)


def patrouille_reserve(s, prot):
    """[MSR 1, MSR 4] Units not set up are missing from this patrol; set aside until the next patrol."""
    res = s.setdefault("patrouille_reserve", {})
    weg = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and not e.get("karte")]
    for n in weg:
        res[n] = {"einheit": s["einheiten"].pop(n), "kommando": s["kommandos"].pop(n, None)}
    if weg:
        prot.append("Not set up, missing from this patrol: " + ", ".join(weg) + " [MSR 1, MSR 4]")


def patrouille_reserve_zurueck(s, prot):
    res = s.pop("patrouille_reserve", {})
    for n, x in res.items():
        s["einheiten"][n] = x["einheit"]
        if x.get("kommando") is not None:
            s["kommandos"][n] = x["kommando"]
    if res:
        prot.append("Back for the next patrol: " + ", ".join(res))


def patrouille_ende(s, prot):
    """End of a patrol (10 turns): Primary cleared (+4), next patrol or mission end [MSR 1, Normandy p.13]."""
    p = pat(s)
    z = s.get("ziele", {})
    pk = z.get("primaer")
    vergeben = s.setdefault("xp_karten", [])
    if pk and pk not in vergeben and geklaert(s, pk):
        xp_buchen(s, xp_tab(s, "cp_primaer") or 4, f"Primary Objective {pk} cleared (patrol Platoon {p.get('platoon')})", prot)
        vergeben.append(pk)
    s["missionsende"] = True
    erl = p.setdefault("erledigt", [])
    if p.get("platoon") and p["platoon"] not in erl:
        erl.append(p["platoon"])
    rest = [x for x in ("1", "2", "3") if x not in erl]
    prot.append(f"Patrol {len(erl)} (Platoon {p.get('platoon')}) ended: " + ("SUCCESSFUL" if p.get("erfolg") else f"not successful (Route Points {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primaer_besucht') else 'not passed'})")
                + "; XP only for the patrol platoon [MSR 1]")
    if rest:
        prot.append(f"Next patrol: fof.py patrol next <{'|'.join(rest)}> (3.9 sequence, new PCs, cover and mines remain) [MSR 1, MSR 3]")
    else:
        prot.append("All three patrols played: Mission 3 ended; Combat Patrols carry no penalty on failure (standard mode) [MSR 1]")


def cmd_patrouille(s, args):
    """patrol | patrol start <platoon> [--with=a,b] | patrol next <platoon> [--with=a,b]"""
    if not s.get("patrouille_mission"):
        raise Verstoss("Not a Combat Patrol mission")
    p = s.setdefault("patrouille", {})
    if not args:
        z = s.get("ziele", {})
        print(f"Patrol {len(p.get('erledigt', [])) + (0 if s.get('missionsende') else 1)}: Platoon {p.get('platoon') or '-'}; members: {', '.join(p.get('mitglieder', [])) or '-'}")
        print(f"Route: " + ", ".join(f"{i} {z.get('route', {}).get(str(i)) or '-'}" for i in (1, 2, 3, 4)) + f"; reached {p.get('route_index', 0)}/4; Primary {z.get('primaer') or '-'} {'passed' if p.get('primaer_besucht') else 'open'}; success {'yes' if p.get('erfolg') else 'no'}")
        print(f"Done: {', '.join(p.get('erledigt', [])) or 'none'}")
        return
    o = opts_parse(args[2:])
    prot = []
    if args[0] == "naechste":
        if not s.get("missionsende"):
            raise Verstoss("First finish the current patrol (10 turns) [MSR 1]")
        if args[1] in p.get("erledigt", []):
            raise Verstoss(f"Platoon {args[1]} has already done its patrol [MSR 1]")
        s["patrouille_wechsel"] = True
        cmd_reattempt(s, [])
        s = laden()
        s.pop("patrouille_wechsel", None)
        patrouille_reserve_zurueck(s, prot)
        s["licht"] = None
        s.pop("konzentration_gesetzt", None)
        prot.append("New visibility for this patrol: draw R#4 (1=+2 ... 4=+5), fof.py visibility <light>; place units with setup on row 1 or in the COP, then fof.py reattempt done [Normandy M3 p.24, MSR 1]")
        p = s.setdefault("patrouille", {})
    elif args[0] != "start":
        raise Verstoss("patrol | patrol start <platoon> [--with=..] | patrol next <platoon> [--with=..]")
    if not in_aufstellung(s):
        raise Verstoss("Set the patrol only before turn 1 [MSR 1]")
    plt = args[1]
    hqs = {x.get("platoon"): m for m, x in s["einheiten"].items() if x.get("ebene") == "PLT" and x["seite"] == "US"}
    if plt not in hqs:
        raise Verstoss(f"Platoon {plt} unknown; available: {', '.join(sorted(k for k in hqs if k))}")
    mit = liste_opt(o, "--mit")
    for m in mit:
        x = einheit(s, m)
        if x.get("ebene") == "PLT" or (x["typ"] == "Squad" and x.get("platoon") != plt):
            raise Verstoss(f"{m}: only Weapons Teams, FOs and Company Staff may join the patrol [2.6.1]")
    mitglieder = [m for m, x in s["einheiten"].items() if x["seite"] == "US" and (x.get("platoon") == plt or m in mit)]
    for m, x in s["einheiten"].items():
        if x["seite"] != "US":
            continue
        if m in mitglieder:
            x.pop("stationaer", None)
        else:
            x["stationaer"] = True
    p.update(platoon=plt, mitglieder=mitglieder, route_index=0, primaer_besucht=False, erfolg=False)
    s["einzelzug"] = True
    prot.append(f"Patrol Platoon {plt}: {', '.join(mitglieder)}; setup on row 1 (setup <unit> <11-15>)")
    ohne = [m for m in mitglieder if s["einheiten"][m]["typ"] not in ("Staff",) and s["einheiten"][m].get("ebene") not in ("CO", "BN")
            and not s["einheiten"][m].get("platoon")]
    if ohne:
        prot.append(f"Unassigned: {', '.join(ohne)}; without assignment only the CO HQ and Staff can order them (2.3.3). Assign for the whole mission: "
                    f"setup <unit> --platoon={plt} [RULE 2.3.3 p.10, K25]")
    prot.append("Other units: into the fortifications of row 1 or into the Combat Outpost (at most one platoon); they fire and accept orders but do not move; units not set up are missing from this patrol [MSR 1, MSR 4]")
    prot.append("Before turn 1: objective primary <row 4>, objective route 1-4 <rows 2-4>, Artillery Concentration (fof.py note), visibility <light> (R4: 1=+2 ... 4=+5); GI draw halved [3.3.2d]")
    speichern(s, "; ".join(prot), "2.6 p.12, MSR 1")
    ausgabe(prot, s)


def cmd_xp(s, args):
    if not v4(s):
        raise Verstoss("Experience only in campaign missions")
    if args and args[0] in ("plus", "ausgeben"):
        n = int(args[1]) * (1 if args[0] == "plus" else -1)
        grund = " ".join(args[2:]) or ("manual" if n > 0 else "spent")
        prot = []
        if n < 0 and sum(x["punkte"] for x in s.get("xp", [])) + n < 0:
            raise Verstoss("Not enough Experience Points")
        xp_buchen(s, n, grund, prot)
        speichern(s, "; ".join(prot), "12.1 p.80, 12.3 p.81")
        ausgabe(prot, s)
        return
    for x in s.get("xp", []):
        print(f"- T{x['zug']} A{x['versuch']}: {x['punkte']:+d} {x['grund']}")
    print(f"Total {sum(x['punkte'] for x in s.get('xp', []))}; cards already scored: {', '.join(s.get('xp_karten', [])) or 'none'}")
    ok, txt = ziel_stand_v4(s)
    print("Status now: " + txt)


def cmd_reattempt(s, args):
    """[RULE 3.9 p.17/18] Reattempt preparation, steps 1-14."""
    k = s.get("kampagne", {})
    if args and args[0] == "fertig":
        if not s.get("reattempt_setup"):
            raise Verstoss("No reattempt preparation pending")
        prot = []
        for n, e in list(s["einheiten"].items()):
            if e["seite"] == "US" and ist_lat(e) and e["typ"] != "Fire Team":
                e["typ"], e["erfahrung"] = "Fire Team", "Green"
                lat_werte_setzen(e, "Fire Team")
                prot.append(f"{n} becomes a Fire Team (step 4)")
            if e["seite"] == "US":
                e["status"] = []
        falsch = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and e.get("karte") and not karte(s, e["karte"]).get("staging") and not gesichert(s, e["karte"])
                  and not (s.get("patrouille_mission") and (karte(s, e["karte"])["reihe"] == 1 or e["karte"] == s.get("ziele", {}).get("cop")))]
        if falsch:
            raise Verstoss("Friendly units only in the Staging Area or on secured cards (step 5): " + ", ".join(falsch))
        if s.get("patrouille_mission"):
            offen_st = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and e.get("stationaer") and e.get("karte")
                        and karte(s, e["karte"]).get("cover") and e.get("bereich", "offen") == "offen"]   # L55
            if offen_st:
                raise Verstoss("Place non-patrol units in the fortifications (setup <unit> <card> --area=C1|C2): "
                               + ", ".join(offen_st) + " [Normandy M3 p.26 MSR 1]")
            fa = [x for x in aufstellung_pruefen_v4(s) if not x.startswith("Terrain")]
            if s.get("assets_start") and not any(e.get("assets") for e in s["einheiten"].values() if e["seite"] == "US") \
                    and not s.get("assets_bewusst_leer"):   # L57: step 12 puts all assets into the pool
                fa.append("Distribute assets: setup <unit> --asset=<type> (pool: " + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b) + ") [3.9 step 12, 2.3.4 p.10]")
            if s.get("fm_werte") and not s.get("konzentration_gesetzt"):   # L56
                fa.append("Artillery Concentration: objective concentration <card> <firing agency> [Normandy M3 p.24, 7.16.5]")
            if fa:
                raise Verstoss("Still open before turn 1 of the patrol: " + "; ".join(fa))
            patrouille_reserve(s, prot)
        s["reattempt_setup"] = False
        s["aufstellung_fertig"] = True
        feuer_eroeffnen(s, prot)
        ak = aktivitaet_berechnen(s)
        if ak:
            prot.append(ak)
        prot.append(f"Attempt {k.get('versuch')} starts with turn 1 (steps 13/14); no new PC markers, Spotted status remains [3.9 p.18]")
        speichern(s, "Reattempt: " + "; ".join(prot), "3.9 p.18")
        ausgabe(prot, s)
        return
    if not s.get("missionsende"):
        raise Verstoss("Reattempt only after the last turn (Clean Up of turn {}) [3.9 p.17]".format(s.get("max_zuege")))
    if not s.get("patrouille_mission"):
        ok, txt = ziel_stand_v4(s)
        if ok:
            raise Verstoss("Mission objective achieved, no reattempt needed")
        if k.get("versuch", 1) >= k.get("versuche_max", 1) or not opt(s, "U9_reattempt"):
            raise Verstoss("No more reattempts allowed [3.9 p.17]")
    elif not s.get("patrouille_wechsel"):
        raise Verstoss("Combat Patrol: next patrol with fof.py patrol next <platoon> [MSR 1]")
    prot = [f"Experience so far {sum(x['punkte'] for x in s.get('xp', []))} (step 1; cards not counted twice)"]
    for n, e in s["einheiten"].items():
        if e["seite"] == "US" and ft_seite(e):
            e["status"] = [x for x in e["status"] if x != "Fire Team side"]
            prot.append(f"{n} to the Good Order side (step 2)")
    for kid, c in s["karten"].items():
        if c.get("casualties") or c.get("casualties_feind"):
            prot.append(f"{kid}: casualties removed (step 6)")
            c["casualties"] = c["casualties_feind"] = 0
        c["extern"] = [x for x in c.get("extern", []) if x["typ"] == "Mines"]
        for x in c["extern"]:
            x["aktiv"] = False
        c.pop("grenade_miss", None)
        c["assets"] = []
        c["munition"] = {}
    for n, e in list(s["einheiten"].items()):
        if e["seite"] == "Feind" and e["typ"] in ("Paralyzed Team", "Litter Team"):
            del s["einheiten"][n]
            prot.append(f"{n} removed (step 6)")
        if e.get("ebene") == "BN" and e["seite"] == "US":
            del s["einheiten"][n]
            s["kommandos"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; events end with the attempt (turn counter restarts)")
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and e.get("bereich", "offen") == "offen":
            frei = [cv for cv in karte(s, e["karte"]).get("cover", []) if not any(s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == cv["id"] for m in auf(s, e["karte"]))]
            if frei:
                e["bereich"] = max(frei, key=lambda x: x["wert"])["id"]
                prot.append(f"{n} under {e['bereich']} (step 8; if there is too little cover, distribute randomly)")
        e["status"] = [x for x in e["status"] if x not in ("Pinned", "Exposed")]
        e["ziel"] = None
        for f in ("ziel_offen", "konzentriert", "cf", "grenade", "mine_hit", "nur_pdf", "indirekt", "munition_leer", "kein_feuer_bis_clean_up"):
            e.pop(f, None)
        m = e.get("munition")
        if m and m.get("start") is not None:
            m["punkte"] = m["start"]
            e.pop("out_of_ammo", None)
        if e.get("spotter"):
            e["missionen"] = 2
        if e["seite"] == "US" and e.get("attachment") is None:
            orig = s.get("aufbau_einheiten", {}).get(n, {})
            if orig.get("funk") is not None:
                e["funk"] = copy.deepcopy(orig["funk"])
                if s.get("co_tac_mittel") == "telefon":
                    for g in e["funk"]:
                        if g["netz"] == "CO TAC":
                            g["typ"] = "EE8"
        e.pop("assets", None)
    prot.append("Pinned, PDF and VOF removed, ammo and assets replenished, dropped assets off the board (steps 10-12); cover markers and mines remain (step 7)")
    for kk in s["kommandos"].values():
        kk.update(verfuegbar=0, gespart=0, aktiviert=False, fertig=False)
    s["feuermissionen"] = copy.deepcopy(s.get("fm_start", s.get("feuermissionen")))
    s["target_marker"] = {}
    s["assets_pool"] = copy.deepcopy(s.get("assets_start", s.get("assets_pool", {})))
    # L58: turn-based event flags apply only in the attempt in which they were drawn (turn counter restarts, 3.9 step 13)
    for _f in ("hold_up", "ereignis_pflicht", "ereignis_flanke", "ereignis_route", "fm_gesperrt", "ereignis_erledigt"):
        s.pop(_f, None)
    if s.get("gegenangriff"):
        s["feind_taktik"] = s["gegenangriff"].get("taktik_vorher", s.get("feind_taktik"))
        s.pop("gegenangriff")
        prot.append("Counterattack ends with the last turn (BGG E16)")
    if s.get("patrouille_mission"):
        neu_pc = []
        for kid, letter in s.get("pc_start", {}).items():
            c = karte(s, kid)
            if not c.get("pc") and kid != s.get("ziele", {}).get("cop"):
                c["pc"] = letter
                neu_pc.append(kid)
        z = s.setdefault("ziele", {})
        z["primaer"], z["route"] = None, {}
        s["target_marker"] = {}
        prot.append(("New PC markers on " + ", ".join(sorted(neu_pc)) if neu_pc else "No PC markers to replace")
                    + "; place Primary, Route Points and Artillery Concentration again (objective primary/route) [2.6.3, MSR 1, Normandy M3 p.24]")
    k["versuch"] = k.get("versuch", 1) + 1
    s["zug"], s["phase"] = 1, sop(s)[0][0]
    s["reattempt_setup"] = True
    s.pop("missionsende", None)
    s["aktiver_hq"] = None
    ak = aktivitaet_berechnen(s)
    if ak:
        prot.append(ak)
    lats = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and ist_lat(e)]
    prot.append(f"Attempt {k['versuch']}: reconstitute now (reconstitute <unit> --from=<LAT,..>; LATs: {', '.join(lats) or 'none'}; 1 Green step per LAT, new HQs Green), "
                "spend Experience (xp spend <n> <reason>, set <unit> erfahrung=..), distribute assets (setup --asset), "
                "place units on secured cards or in Staging (setup <unit> <card> [--area=<cover>]), then fof.py reattempt done [3.9 p.17/18]")
    speichern(s, "Reattempt preparation: " + "; ".join(prot), "3.9 p.17")
    ausgabe(prot, s)


def cmd_rekon(s, args):
    """[RULE 3.9 step 3 p.17] Squads, HQs and company weapons teams (no attachments) from LATs; each LAT = 1 Green step."""
    if not s.get("reattempt_setup"):
        raise Verstoss("reconstitute only during reattempt preparation (3.9); during the turn use 4.2.3i/4.2.1d")
    n = args[0]
    o = opts_parse(args[1:])
    lats = liste_opt(o, "--aus")
    if not lats:
        raise Verstoss("Specify --from=<LAT>[,<LAT>..]")
    for t in lats:
        te = einheit(s, t)
        if te["seite"] != "US" or not ist_lat(te):
            raise Verstoss(f"{t} is not a friendly LAT")
    orig = s.get("aufbau_einheiten", {}).get(n)
    if not orig:
        raise Verstoss(f"{n} is not part of the company according to the setup")
    if orig.get("attachment"):
        raise Verstoss(f"{n} is an attachment, no reconstitution (3.9 step 3)")
    prot = []
    maxst = orig.get("steps", 1)
    if n in s["einheiten"]:
        e = s["einheiten"][n]
        if steps(e) + len(lats) > maxst:
            raise Verstoss(f"{n} has at most {maxst} steps")
        e["steps"] = steps(e) + len(lats)
        prot.append(f"{n} at {e['steps']} steps")
    else:
        if len(lats) > maxst:
            raise Verstoss(f"{n} has at most {maxst} steps")
        e = copy.deepcopy(orig)
        e.update(karte=s["einheiten"][lats[0]]["karte"], bereich="offen", status=[], steps=len(lats), ziel=None)
        if ist_hq(e):
            e["erfahrung"] = "Green"
        if n in s.get("removed_from_play", []):
            s["removed_from_play"].remove(n)
        s["einheiten"][n] = e
        if ist_hq(e):
            s["kommandos"].setdefault(n, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
        prot.append(f"{n} with {len(lats)} step(s) on {e['karte']}" + (", Green (new HQs are always Green)" if ist_hq(e) else ""))
    if o.get("--erfahrung") and not ist_hq(e):
        e["erfahrung"] = o["--erfahrung"]
        prot.append(f"Experience {o['--erfahrung']} (12.6 table, promotions via xp spend)")
    elif not ist_hq(e):
        s.setdefault("_hinweise", []).append(f"{n}: determine experience per 12.6 p.82 (LAT = Green step) and set it with --experience= or set")
    for t in lats:
        del s["einheiten"][t]
    prot.append(f"used up: {', '.join(lats)}")
    speichern(s, "Reconstitution: " + "; ".join(prot), "3.9 p.17, 12.6 p.82")
    ausgabe(prot, s)


def cmd_kampagne(s, args):
    k = s.get("kampagne")
    if not k:
        print("No campaign mission.")
        return
    print(f"# Mission Log {k.get('name')} Mission {k.get('mission_nr')}, attempt {k.get('versuch')} of {k.get('versuche_max')}, turn {s['zug']}")
    for a, b in k.get("log", {}).items():
        print(f"- {a}: {b}")
    print(f"- CO TAC: {s.get('co_tac_mittel') or 'not chosen yet (CSR 1)'}; Mortar: {s.get('moerser_wahl') or 'not chosen yet (CSR 2)'}")
    print("- Objectives: " + ", ".join(f"{a} {b}" for a, b in s.get("ziele", {}).items() if a != "phaselines") + (f", Phase Lines {s['ziele'].get('phaselines')}" if s.get("ziele", {}).get("phaselines") else ""))
    print("- Pyro (Mission Log): " + (", ".join(f"{a}={b}" for a, b in s.get("pyro_belegung", {}).items()) or "no assignment"))
    print("- Asset-Pool: " + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b))
    print(f"- Fire Missions: {s.get('feuermissionen')}")
    print(f"- Experience {sum(x['punkte'] for x in s.get('xp', []))}; US casualty steps {s.get('us_casualties_gesamt', 0)}; prisoners {s.get('gefangene', 0)}; evacuated {s.get('evakuiert', 0)}")
    print("## Units")
    for n, e in s["einheiten"].items():
        if e["seite"] == "US":
            print(f"- {n}: {steps(e)} step(s) {erfahrung(e)}" + (f", {e['munition']['typ']} {e['munition']['punkte']}" if e.get("munition") else "")
                  + (f", Radio {'/'.join(g['typ'] + ' ' + g['netz'] for g in geraete(e))}" if geraete(e) else "") + (f", Assets {', '.join(e['assets'])}" if e.get("assets") else ""))
    if s.get("removed_from_play"):
        print("- Removed from Play: " + ", ".join(s["removed_from_play"]))


# ---------------------------------------------------------------- Pyrotechnics (4.4, 4.2.1c)
def pyro_ausfuehren(s, z, name, o, prot):
    typ = o.get("--asset")
    if not typ or typ not in z.get("assets", []):
        raise Verstoss(f"{name}: specify --asset=<type>; carries {', '.join(z.get('assets', [])) or 'no pyro asset'} [4.2.1c p.22]")
    if not (good_order(z) or (z["typ"] in ("Assault Team", "Fire Team") and not pinned(z))):
        raise Verstoss("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1c p.22]")
    zk = o.get("--ziel", z["karte"])
    karte(s, zk)
    if typ in PYRO_LUFT:
        if zk != z["karte"] and not benachbart(s, z["karte"], zk):
            raise Verstoss("Aerial pyrotechnics on the own card or an adjacent card [4.4 p.30]")
    elif zk != z["karte"]:
        raise Verstoss("Non-aerial (smoke) only on the own card [4.4 p.30]")
    z["assets"].remove(typ)
    if typ == "Handheld Illumination":
        iv = (s.get("illum_werte") or {}).get(typ) or {"oben": -1, "unten": None}
        karte(s, zk).setdefault("illum", []).append({"oben": iv["oben"], "unten": iv.get("unten"), "quelle": typ})
        prot.append(f"Hand Held Illumination {iv['oben']:+d} on {zk} (this card only), immediately; removed in Clean Up [4.4, 9.2 p.70, Marker E34]")
        feuer_eroeffnen(s, prot)
        return
    if typ in ("HC Smoke", "WP Smoke"):
        w = o.get("--wert")
        if w is None:
            raise Verstoss(f"{typ}: read the cover value from the marker (UNVERIFIED) and specify --value=<n> [4.4.3 p.31]")
        karte(s, zk).setdefault("extern", []).append({"typ": "Smoke", "wert": int(w), "quelle": typ, "seite": "US"})
        prot.append(f"{typ} on {zk} (cover +{w} against everything except Incoming/Air Strike/Mines/Grenade; blocks LOS out of and through {zk}; removed in Clean Up) [4.4.3 p.31, 5.4 p.38]")
        for n, e in s["einheiten"].items():
            if e["karte"] == zk and feuert(e) and e["ziel"] != zk:
                e["ziel"] = None
                prot.append(f"{n} loses LOS out of the card, remove PDF [5.4]")
        return
    code = s.get("pyro_belegung", {}).get(typ)
    prot.append(f"{typ} on {zk} fired" + (f", Mission Log: {code}" if code else ", no assignment (no effect)") + " [4.4.1 p.30]")
    if not code:
        return
    karte(s, zk).setdefault("pyro", []).append(typ)                      # display only; removed in Clean Up (3.8), no VOF
    # [RULE 4.4.1 p.30] Colored flares visible everywhere; colored smoke only with normal LOS to the card
    folgen = []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US":
            continue
        if typ in PYRO_FARBE and not (e["karte"] == zk or los(s, e["karte"], zk)[0]):
            continue
        if not opt(s, "U21_pyro_alle_einheiten") and ist_hq(e) and n != name and hq_rang(e) < hq_rang(einheit(s, name)):
            continue
        folgen.append(n)
    zi = s.get("ziele", {})
    if code == "CF":
        for n in folgen:
            e = s["einheiten"][n]
            if feuert(e):
                e["ziel"] = None
                e.pop("konzentriert", None)
                prot.append(f"{n} ceases fire [4.2.4k]")
        feuer_eroeffnen(s, prot)
        prot.append("Cease Fire by signal: units with a Spotted enemy in LOS open fire again immediately per 6.1.1 [4.4.1 footnote]")
        return
    ziel_von = {}
    for n in folgen:
        e = s["einheiten"][n]
        if code == "M2S" and benachbart(s, e["karte"], zk):
            ziel_von[n] = zk
        elif code in ("M2PO", "M2SO"):
            obj = zi.get("primaer" if code == "M2PO" else "sekundaer")
            if obj and benachbart(s, e["karte"], obj):
                ziel_von[n] = obj
        elif code.startswith("M2RP"):
            rp = zi.get("route", {}).get(code[4:])
            if rp and benachbart(s, e["karte"], rp):
                ziel_von[n] = rp
        elif code.startswith("XPL"):
            r = zi.get("phaselines", {}).get(code[3:])
            if r is not None and karte(s, e["karte"])["reihe"] == r:
                k2 = karte_bei(s, r + 1, karte(s, e["karte"])["spalte"])
                if k2:
                    ziel_von[n] = k2
        elif code in ("InfAP2PO", "InfAP2SO"):
            obj = zi.get("primaer" if code == "InfAP2PO" else "sekundaer")
            if obj and e["karte"] == zi.get("ap"):
                ziel_von[n] = obj
    erg = {}
    for t in (o.get("--erfolg") or "").split(","):
        if ":" in t:
            a, b = t.split(":")
            erg[a] = b
    for n, zk2 in ziel_von.items():
        e = s["einheiten"][n]
        akt = "4.2.2c" if code.startswith("Inf") else "4.2.2a"
        try:
            pruefe_bewegung(s, e, n, zk2, akt)
        except Verstoss as v:
            prot.append(f"{n} cannot follow the signal: {v}")
            continue
        if akt == "4.2.2c" and erg.get(n) not in ("ja", "nein"):
            raise Verstoss(f"Infiltration by signal: each unit draws 2 cards (own experience): --success=" + ",".join(f"{m}:yes|no" for m in ziel_von) + " [4.4.1 p.30]")
        bewegen(s, n, zk2, None, exposed=(akt == "4.2.2a" or erg.get(n) == "nein"), prot=prot)
    if not ziel_von:
        prot.append("no unit meets the requirement of the signal")


def hq_rang(e):
    return {"BN": 0, "CO": 1}.get(e.get("ebene"), e.get("rang", 9) if e["typ"] == "Staff" else 5)


# ---------------------------------------------------------------- Orders 4.2.1f-k
def befehl_v4(s, hq_name, ziel_name, akt, o, orig, prot):
    """Runner, net change, phone line repair. Returns True if the action was handled here."""
    if akt == "4.2.1f":
        z = einheit(s, ziel_name)
        if runner_zahl(s) >= 2:
            raise Verstoss("At most two Runners in play [4.3.2 p.27, 4.2.1f p.22]")
        if not (good_order(z) or (z["typ"] in ("Assault Team", "Fire Team") and not pinned(z))) or ist_hq(z):
            raise Verstoss("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1f p.22]")
        rn = neuer_name(s, "Runner")
        while rn in runner_box(s):
            rn = rn[:-1] + str(int(rn[-1]) + 1)
        schritt_abgeben(s, ziel_name, prot, "Fire")
        runner_box(s).append(rn)
        prot.append(f"{rn} (Line) into the CO HQ Assets Box; moves with the CO HQ [4.2.1f p.22, 4.3.2 p.27]")
        return True
    if akt in ("4.2.1g", "4.2.1h"):
        raise Verstoss(f"{ziel_name} is not in the CO HQ Assets Box (en route or not a Runner); Runner orders only to Runners in the box [4.3.2 p.27]")
    if akt == "4.2.1k":
        z = einheit(s, ziel_name)
        c = karte(s, z["karte"])
        if orig["karte"] != z["karte"]:
            raise Verstoss("Originator must be on the same card as the cut phone line [4.2.1k p.22]")
        cut = [l for l in c.get("leitungen", []) if l.get("cut")]
        if not cut or not good_order(z):
            raise Verstoss(f"No cut phone line on {z['karte']} or {ziel_name} not in Good Order [4.2.1k p.22]")
        for l in cut:
            l["cut"] = False
        prot.append(f"Phone Line on {z['karte']} repaired (flip the marker back) [4.2.1k p.22]")
        return True
    if akt == "4.2.1j":
        z = einheit(s, ziel_name)
        von, nach = o.get("--von"), o.get("--nach")
        g = [x for x in geraete(z) if x["netz"] == von]
        if not g:
            raise Verstoss(f"{ziel_name} has no device in net {von}; --source=<net> --to=<net> [4.2.1j p.22]")
        weg = f"{g[0]['typ']} {nach}"
        if weg not in s.get("funk_zerstoert", []):
            raise Verstoss(f"No {g[0]['typ']} of net {nach} is Removed from Play; only the same device type can replace it [4.2.1j p.22, BGG D2]")
        s["funk_zerstoert"].remove(weg)
        s["funk_zerstoert"].append(f"{g[0]['typ']} {von}")
        g[0]["netz"] = nach
        prot.append(f"{ziel_name}: {g[0]['typ']} now in net {nach} (net {von} drops out instead) [4.2.1j p.22]")
        return True
    return False


def befehl_runner_box(s, hq_name, ziel_name, akt, o):
    """4.2.1g/h to a Runner in the CO HQ Assets Box (not a unit on the board)."""
    co = s.get("co_hq")
    if hq_name != co and not (hq_name == "GI" and o.get("--originator") == co):
        raise Verstoss("Only the CO HQ gives Runner orders [4.2.1g/h p.22]")
    if s["phase"] not in IMPULSE or s.get("aktiver_hq") != hq_name:
        raise Verstoss(f"Active HQ is {s.get('aktiver_hq')}, not {hq_name}")
    name, kosten, _, _, regel = AKTIONEN[akt]
    k = s["kommandos"][hq_name]
    if k["verfuegbar"] + (0 if hq_name == "GI" else k["gespart"]) < kosten:
        raise Verstoss(f"{hq_name} has too few Commands [RULE {regel}]")
    ce = einheit(s, co)
    prot = []
    if akt == "4.2.1g":
        hq = o.get("--ziel")
        h = s["einheiten"].get(hq)
        if not h or not (h.get("ebene") == "PLT" or h["typ"] == "Staff"):
            raise Verstoss("--target=<PLT HQ or CO Staff on the board> to be activated next turn [4.2.1g p.22]")
        runner_box(s).remove(ziel_name)
        s["einheiten"][ziel_name] = {"typ": "Runner", "seite": "US", "erfahrung": "Line", "karte": h["karte"], "bereich": h.get("bereich", "offen"),
                                     "status": ["Exposed"], "steps": 1, "vof_rating": None, "reichweite": "C", "ziel": None, "runner_ziel": hq,
                                     "unterwegs_seit": s["zug"], "fire_team_seite": False,
                                     "hinweis": "Runner, Line (4.2.1f); counter VOF UNVERIFIED"}
        prot.append(f"{ziel_name} to {hq} on {h['karte']}, Exposed; activates {hq} in the CO HQ Impulse of the next turn unless hit/pinned [4.2.1g p.22, 4.3.2 p.27]")
    else:
        e = o.get("--einheit")
        x = s["einheiten"].get(e)
        if not x or x["karte"] != ce["karte"] or x.get("bereich", "offen") != ce.get("bereich", "offen") or not good_order(x):
            raise Verstoss("--unit=<Good Order unit in the same card area as the CO HQ that can absorb a step> [4.2.1h p.22]")
        maxst = s.get("aufbau_einheiten", {}).get(e, {}).get("steps", steps(x))
        if steps(x) >= maxst:
            raise Verstoss(f"{e} cannot absorb a step (has {steps(x)} of {maxst})")
        runner_box(s).remove(ziel_name)
        x["steps"] = steps(x) + 1
        prot.append(f"{ziel_name} released, {e} at {x['steps']} steps [4.2.1h p.22]")
    bezahlen(s, hq_name, kosten, regel)
    txt = f"{hq_name} orders {ziel_name}: {name}; remaining {k['verfuegbar']}+{k['gespart']}"
    speichern(s, txt + "; " + "; ".join(prot), regel)
    print("ALLOWED [RULE " + regel + "]")
    print(txt)
    ausgabe(prot, s)


# ---------------------------------------------------------------- Rule lookup
def cmd_regel(args):
    if not (DATA / "regelindex.json").exists():
        sys.exit("No rule index yet: run tool/build_rules_index.py --rules <your rulebook PDF> first (no rule text ships with this kit).")
    idx = json.loads((DATA / "regelindex.json").read_text(encoding="utf-8"))
    komp = (DATA / "regelbuch_kompakt.txt").read_text(encoding="utf-8").split("\n")
    nr = args[0]
    if nr not in idx:
        sys.exit(f"Rule {nr} not in the index. Example: 4.2.2a is part of 4.2.2.")
    start = idx[nr]["zeile_kompakt"]
    folgende = sorted((v["zeile_kompakt"], k) for k, v in idx.items() if v["zeile_kompakt"] and v["zeile_kompakt"] > start)
    ende = folgende[0][0] if folgende else start + 40
    print(f"[RULE {nr} p.{idx[nr]['seite']}] {idx[nr]['titel']}")
    print("\n".join(komp[start - 1:min(ende - 1, start + 80)]))
    clf = DATA / "clarifications_2025_05_kompakt.txt"
    cl = clf.read_text(encoding="utf-8") if clf.exists() else ""
    haupt = ".".join(nr.split(".")[:2])
    if re.search(r"\b" + re.escape(nr) + r"\b", cl) or re.search(r"\b" + re.escape(haupt) + r"\b", cl):
        print(f"\nNOTE: Clarifications May 2025 mention {haupt}/{nr}; see data/clarifications_2025_05_kompakt.txt")


def cmd_suche(args):
    rx = re.compile(re.escape(" ".join(args)), re.I)
    for f in sorted(DATA.glob("*_kompakt.txt")):
        for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if rx.search(l):
                print(f"{f.name}:{i}: {l.strip()[:140]}")


# ---------------------------------------------------------------- English command-line aliases
# The engine was written in German. Every command, sub-word, option and value below has an English alias;
# the German originals keep working. Internal identifiers and JSON keys stay German (see GLOSSARY.md).
CMD_ALIASES = {
    "new": "neu", "rule": "regel", "search": "suche", "status": "stand", "check": "pruefung",
    "phase": "phase", "activate": "aktivieren", "hq": "hq", "card": "karte", "gi": "gi", "order": "befehl",
    "done": "fertig", "fire": "feuer", "enemycheck": "feindcheck", "enemyaction": "feindaktion", "pc": "pc",
    "external": "extern", "enemy": "feind", "ncm": "ncm", "note": "notiz", "hit": "treffer", "endturn": "rundenende",
    "setup": "aufstellen", "radio": "funk", "drop": "ablegen", "options": "optionen", "terrain": "terrain",
    "extend": "erweitern", "objective": "ziel", "set": "werte", "event": "ereignis", "mine": "mine", "sniper": "sniper",
    "line": "leitung", "runner": "runner", "ammo": "munition", "capture": "gefangen", "xp": "xp",
    "reattempt": "reattempt", "reconstitute": "rekon", "campaign": "kampagne", "visibility": "sicht", "illum": "illum",
    "patrol": "patrouille",
}
SUBWORD_ALIASES = {   # per (German) command: English positional word -> German word
    "phase": {"next": "weiter"},
    "patrouille": {"next": "naechste"},
    "reattempt": {"done": "fertig"},
    "xp": {"add": "plus", "spend": "ausgeben"},
    "pc": {"reveal": "aufdecken", "set": "setzen", "clear": "frei", "contact": "kontakt"},
    "ziel": {"primary": "primaer", "secondary": "sekundaer", "concentration": "konzentration"},
    "leitung": {"lay": "legen"},
    "funk": {"check": "pruefen", "damage": "schaden", "intact": "heil", "destroyed": "zerstoert"},
    "feuer": {"off": "aus"},
    "extern": {"remove": "weg"}, "feind": {"remove": "weg"}, "illum": {"remove": "weg"},
    "munition": {"depot": "lager"},
    "ereignis": {"yes": "ja", "no": "nein"},
    "mine": {"yes": "ja", "no": "nein"},
}
OPT_ALIASES = {
    "--target": "--ziel", "--success": "--erfolg", "--unit": "--einheit", "--net": "--netz", "--area": "--bereich",
    "--value": "--wert", "--mortar": "--moerser", "--place": "--platz", "--free": "--gratis", "--agency": "--agentur",
    "--edges": "--raender", "--building": "--gebaeude", "--building-value": "--gebaeude_wert", "--experience": "--erfahrung",
    "--who": "--wer", "--type": "--typ", "--move-target-marker": "--target", "--skill-from": "--skill-von", "--no": "--nr",
    "--to": "--nach", "--with": "--mit", "--lines": "--leitungen", "--device": "--geraet", "--from": "--aus",
    "--extra": "--zusatz", "--what": "--was", "--choice": "--wahl", "--source": "--von", "--variant": "--variante",
    "--raw": "--roh", "--direction": "--richtung", "--range": "--reichweite", "--origin": "--quelle",
    "--this-turn-only": "--nur_zug", "--line": "--leitung", "--grenade": "--granate", "--at": "--bei",
    "--battalion": "--bataillon",
}
VALUE_ALIASES = {"yes": "ja", "no": "nein", "open": "offen", "Left": "Links", "Right": "Rechts", "none": "keiner",
                 "radio": "funk", "phone": "telefon", "section": "sektion"}


def argv_deutsch(argv):
    """Translate an English command line into the engine's German command line (German input passes unchanged)."""
    if not argv:
        return argv
    cmd = CMD_ALIASES.get(argv[0], argv[0])
    sub = SUBWORD_ALIASES.get(cmd, {})
    out = [cmd]
    for a in argv[1:]:
        if a.startswith("--"):
            k, eq, v = a.partition("=")
            k = OPT_ALIASES.get(k, k)
            if eq and k == "--raender":
                for en_, de_ in (("top", "oben"), ("bottom", "unten"), ("left", "links"), ("right", "rechts"),
                                 ("white", "weiss"), ("green", "gruen"), ("dark", "gruen"), ("corner", "diagonal")):
                    v = v.replace(en_, de_)
            elif eq:
                v = ",".join(VALUE_ALIASES.get(x, x) for x in v.split(",")) if k in ("--richtung",) else VALUE_ALIASES.get(v, v)
            out.append(k + eq + v)
        else:
            out.append(sub.get(a, a))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, *args = argv_deutsch(sys.argv[1:])
    try:
        if cmd == "neu":
            return cmd_neu(args)
        if cmd == "regel":
            return cmd_regel(args)
        if cmd == "suche":
            return cmd_suche(args)
        s = laden()
        tabelle = {"phase": cmd_phase, "aktivieren": cmd_aktivieren, "hq": cmd_hq, "karte": cmd_karte, "gi": cmd_gi,
                   "befehl": cmd_befehl, "fertig": cmd_fertig, "feuer": cmd_feuer, "feindcheck": cmd_feindcheck,
                   "feindaktion": cmd_feindaktion, "pc": cmd_pc, "extern": cmd_extern, "feind": cmd_feind, "ncm": cmd_ncm, "notiz": cmd_notiz,
                   "treffer": cmd_treffer, "rundenende": cmd_rundenende, "aufstellen": cmd_aufstellen, "funk": cmd_funk,
                   "ablegen": cmd_ablegen, "optionen": cmd_optionen,
                   # v4
                   "terrain": cmd_terrain, "erweitern": cmd_erweitern, "ziel": cmd_ziel, "werte": cmd_werte, "ereignis": cmd_ereignis,
                   "mine": cmd_mine, "sniper": cmd_sniper, "leitung": cmd_leitung, "runner": cmd_runner, "munition": cmd_munition,
                   "gefangen": cmd_gefangen, "xp": cmd_xp, "reattempt": cmd_reattempt, "rekon": cmd_rekon, "kampagne": cmd_kampagne,
                   "sicht": cmd_sicht, "illum": cmd_illum, "patrouille": cmd_patrouille}
        if cmd == "stand":
            print(briefing(s))
        elif cmd == "pruefung":
            print(stempel(s))
        elif cmd in tabelle:
            tabelle[cmd](s, args)
        else:
            print(__doc__)
    except Verstoss as v:
        print("VIOLATION: " + str(v))
        sys.exit(2)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
