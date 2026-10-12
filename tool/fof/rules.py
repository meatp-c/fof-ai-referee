"""Rule tables: sequence of play, action menu, LAT limits, VOF values, default options (3.0, 4.2, 6.2)."""

from . import messages

SOP_OFFENSIVE = [
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


SOP_DEFENSIVE = (
    [
        SOP_OFFENSIVE[0],
        ("3.2.1", "Enemy Higher HQ Event Segment (from turn 2)"),
        ("3.2.2", "Enemy Activity Check Segment"),
    ]
    + SOP_OFFENSIVE[1:8]
    + SOP_OFFENSIVE[10:]
)


IMPULSES = {"3.3.1a", "3.3.1b", "3.3.1c", "3.3.2a", "3.3.2b", "3.3.2c", "3.3.2d"}


PLT_IMPULSES = {"3.3.1c", "3.3.2b"}


FROM_TURN_2 = {"3.1", "3.2.1", "3.4.1"}


# id: (name, cost, draw type, originator, rule reference)   draw type: auto | attempt | attempt_vof (Rally: auto without VOF) | cover | cff
ACTIONS = {
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
HQ_REQUIRED_UNDER_GI = {"4.2.1b", "4.2.1d", "4.2.1e", "4.2.1f", "4.2.1g", "4.2.1h", "4.2.1l", "4.2.3i", "4.2.4m"}


# 4.2.5 p.26 LAT restrictions (allow lists)
LAT_ALLOWED = {
    "Assault Team": {
        "4.2.2a",
        "4.2.2c",
        "4.2.2e",
        "4.2.2f",
        "4.2.2g",
        "4.2.2h",
        "4.2.3e",
        "4.2.3h",
        "4.2.3i",
        "4.2.4a",
        "4.2.4b",
        "4.2.4d",
        "4.2.4k",
        "4.2.4l",
    },
    "Fire Team": {
        "4.2.2a",
        "4.2.2c",
        "4.2.2e",
        "4.2.2f",
        "4.2.2g",
        "4.2.2h",
        "4.2.3d",
        "4.2.3h",
        "4.2.3i",
        "4.2.4a",
        "4.2.4b",
        "4.2.4d",
        "4.2.4k",
        "4.2.4l",
    },
    "Litter Team": {"4.2.2a", "4.2.2c", "4.2.2e", "4.2.2f", "4.2.2g", "4.2.2h", "4.2.3c"},
    "Paralyzed Team": {"4.2.2a", "4.2.3b"},
}


# 4.2.5 p.26 Pinned: takes precedence over LAT; allows a (restricted), e, f, Rally a, Exhort
PINNED_ALLOWED = {"4.2.2a", "4.2.2e", "4.2.2f", "4.2.3a", "4.2.1b"}


LAT_TYPES = {"C": "Casualty", "P": "Paralyzed Team", "L": "Litter Team", "F": "Fire Team", "A": "Assault Team"}


LAT_EXPERIENCE = {"Assault Team": "Line", "Fire Team": "Green", "Litter Team": "Green", "Paralyzed Team": "Green"}


SAVE_LIMIT = {"Green": (3, 2), "Line": (6, 4), "Veteran": (9, 6)}  # 4.1.3 p.20


MAX_PER_IMPULSE = {"tag": 6, "eingeschraenkt": 4}  # 4.1.3 p.20


VOF_VALUE = {"Pinned": 2, "S": 0, "A": -1, "H": -3}  # 6.2.2 p.42 (A/S: A at Point Blank, otherwise S)


VOF_NAME = {
    "S": "Small Arms",
    "A": "Automatic Weapons",
    "H": "Heavy Weapons",
    "Pinned": "All Pinned",
    "Incoming": "Incoming!",
    "Mines": "Mines",
    "AirStrike": "Air Strike!",
    "G": "Grenade",
    "Sniper": "Sniper",
    "Pending": "Pending",
    "Indirect": "Heavy Weapons (Indirect Lay)",
}


CMD_VOF_MODIFIERS = {
    "S": -1,
    "A": -2,
    "H": -3,
    "Sniper": -3,
    "G": -3,
    "Incoming": -3,
    "AirStrike": -3,
    "Pinned": 0,
    "Mines": 0,
    "Indirect": -3,
}  # 4.1.2B; Indirect Lay is a Heavy Weapons VOF (7.3.2 p.53)


# [RULE 5.2.3 p.36] lower C&C value and burst for Incoming and indirect mortar fire
TERRAIN_LIKE_INCOMING = ("Incoming", "AirStrike", "Indirect")


FIXED_COVER = ("Trench", "Bunker", "Pillbox")  # [RULE 5.1.1 p.31, 5.1.2 p.32] movement without Exposed


STRUCTURES = ("Bunker", "Pillbox")  # [RULE 5.3.2 p.37] fire arc, no Point Blank


SIDE_NAME = {(1, 0): "oben", (-1, 0): "unten", (0, -1): "links", (0, 1): "rechts"}


# Open rules questions from cac/regeln_cac_run3.md (appendix). Default = the reading marked as more likely in the research;
# where none is marked, the reasoning is in cac/aenderungen_fof_v3.md. Effective only if the setup contains "optionen".
DEFAULT_OPTIONS = {
    "U1_remove_pc_no_action": (
        True,
        "Special rule 'Remove unit, place PC' = No Action also applies in Run 2/3 (reading a)",
    ),
    "U2_fo_fd_funk": (True, "FOs implicitly have their FD radio (reading a)"),
    "U3_incoming_blockiert_funk": (True, "Incoming! also blocks SCR536 LOS (reading a, only smoke excepted)"),
    "U4_as_zaehlt_als_a": (
        False,
        "A/S does not count as A in the hierarchy row 'A or H VOF unit that has opened fire' (reading a)",
    ),
    "U6_aktivieren_im_initiative_impuls": (
        False,
        "CO HQ does not activate PLT HQs in the CO HQ Initiative Impulse (reading b)",
    ),
    "U7_lat_behaelt_funk": (True, "HQ becomes Paralyzed/Litter Team: the team keeps the radio (reading a)"),
    "U9_ziel_lesart": ("a", "a: no enemy non-Casualty unit left on the board; b: prisoners/withdrawn units also count"),
    "U9_reattempt": (False, "no Reattempt after the last turn (FM1 names none)"),
    "U10_staging_funk_ueber_hill": (False, "Staging Area radios only to the adjacent cards of row 1 (wording of 2.5)"),
    "U11_plt_mtr_ueber_hub": (
        True,
        "two SCR536 other than the CO HQ talk to each other if both have a connection to the CO HQ (reading a)",
    ),
    "U12_moerser_reichweite": ("C-L", "Range 'C-L' = Close to Long"),
    "U12_indirekt_unter_gi": (False, "Indirect Lay not allowed under General Initiative (reading a)"),
    "U13_target_marker_bei_short": (False, "no automatic Target marker after Short (7.16.5 does not cover the case)"),
    # v4: open rules questions Normandy Mission 1 (normandy/regeln_normandy_m1.md, section U)
    "U14_telefon_diagonal": (
        True,
        "Phone lines also connect diagonally adjacent cards (cards count as adjacent diagonally, 5.1.2)",
    ),
    "U15_leitung_automatisch": (
        True,
        "A unit with lines automatically lays one when leaving a card without a line (4.3.4 'occurs automatically'); --line=no suppresses it",
    ),
    "U16_erste_commands_mit_gespart": (
        True,
        "'first N Commands' (Situation Report, Comm Trouble) include saved Commands",
    ),
    "U17_gegenangriff_staging": (False, "Counterattack: no PC markers on staging cards (map area only)"),
    "U18_fall_back_rand_offmap": (
        True,
        "Enemy Event Fall Back at the top map edge: unit leaves the board (8.6.3, no map extension)",
    ),
    "U19_erweitern_bis_reichweite": (
        True,
        "Max LOS/Range: extend the map up to maximum range, because Hills could give visibility (wording of 8.4.5)",
    ),
    "U20_mine_bei_seek_cover": (
        True,
        "successful Seek Cover on a mine card triggers a mine check (movement within the card)",
    ),
    "U21_pyro_alle_einheiten": (
        True,
        "Signal applies to all units with LOS, including higher-ranking HQs (wording of 4.4.1; Stead says otherwise)",
    ),
    "U22_munition_leer_im_clean_up": (
        True,
        "Out of Ammo consequences (flip/marker) only in Clean Up, after simultaneous combat",
    ),
    "U24_assault_in_staging": (
        True,
        "Advance Straight Ahead (Assault) from the first card row also into the Staging Area toward US units",
    ),
    "U27_mtr_sec_nicht_fa": (
        True,
        "Mtr Sec: C/L/P results as normal (Casualty/LAT), last remaining step becomes a 1-step Mortar Team (CSR 2)",
    ),
    "U28_gegenangriff_alle_pc_a": (
        True,
        "during the counterattack all PC A markers use the Counter-Attack list (MSR 1 'any PC A Markers')",
    ),
    "U29_ein_target_marker_he_wp": (
        True,
        "HE and WP of the same firing agency (15th FA) share one Target marker (7.16.5)",
    ),
}


AMMO_CAPACITY = {"MG": 6, "MTR": 2, "RKT": 3, "RCL": 3}  # [RULE 5.1.6A p.33] per step


PYRO_AERIAL = ("RSP", "RSC", "GSP", "GSC", "Handheld Illumination")  # [RULE 4.4 p.30] Aerial: same or adjacent card


PYRO_COLOR = ("Red Smoke", "Green Smoke", "Yellow Smoke", "Purple Smoke")


PYRO_CODES_OFF = ("CF", "M2PO", "InfAP2PO", "M2SO", "InfAP2SO", "M2S")  # [RULE 4.4.1 p.30] plus XPL#


PYRO_CODES_PAT = ("CF", "M2PO", "M2S")  # [RULE 4.4.1 p.30] Patrol Mission, plus M2RP#


PC_DRAWS = {
    "A": {"No Contact": 0, "Contact": 7, "Engaged": 5, "Heavily Engaged": 3},
    "B": {"No Contact": 0, "Contact": 5, "Engaged": 3, "Heavily Engaged": 2},
    "C": {"No Contact": 4, "Contact": 3, "Engaged": 2, "Heavily Engaged": 1},
}  # 8.2.4 Chart


RANGE_CARDS = {"P": 0, "C": 1, "L": 2, "V": 3}  # 1.2.6 Range


class Violation(Exception):
    """A step the rules do not allow; nothing is saved when it is raised. Optional citation: Violation(msg, rule="6.1.2 p.44")."""

    def __init__(self, message, rule=None):
        super().__init__(message + (" " + messages.rule(rule) if rule else ""))
