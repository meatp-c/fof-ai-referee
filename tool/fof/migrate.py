"""German to English: the vocabulary of older game states, setup files and command lines.

Until the engine stored its game state with German keys and values (spielstand.json, setup files, snapshots) and
used German command words internally. Since everything inside the engine is English. This module is the one
place that still knows the German words:

    WORDS          German key, value, command or sub-command word -> English word
    OPTION_WORDS   German option name -> English option name
    COMMANDS_DE    German command name -> English command name
    FILES, DATA_FILES, ENV  file, folder and environment variable names of earlier releases

state(obj) translates an old game state or setup file on load (keys and exact string values); the command line
(cli.normalize_argv, options.parse_opts) uses the same tables, so German commands, sub-commands, options and option
values keep working as aliases. A file that is already English passes unchanged (no German word is an English target).
"""

from __future__ import annotations

import re
from typing import Any

WORDS = {
    # ---------------------------------------------------------------- game state keys
    "_befehl_opts": "_order_opts",
    "_gleiche_karte_ok": "_same_card_ok",
    "_herkunft": "_origin",
    "_hinweis": "_note",
    "_hinweise": "_hints",
    "_neu_exposed": "_new_exposed",
    "_phase_alt": "_phase_before",
    "_pionier_check": "_engineer_check",
    "_quelle": "_source",
    "_rauch_ziel": "_smoke_target",
    "_reichweite_vof": "_range_vof",
    "_sicht_values": "_sight_values",
    "_typ_values": "_type_values",
    "_unverifiziert": "_unverified",
    "_vof_sperre": "_vof_blocked",
    "agentur": "agency",
    "aktion": "action",
    "aktiv": "active",
    "aktiver_hq": "active_hq",
    "aktiviert": "activated",
    "aktivitaet": "activity",
    "an_bord": "on_board",
    "angegriffen": "attacked",
    "angreifer": "attacker",
    "ap_neben": "ap_neighbours",
    "art": "kind",
    "arty_jeep_moeglich": "arty_jeep_possible",
    "arty_jeep_wahl": "arty_jeep_choice",
    "assets_bewusst_leer": "assets_empty_on_purpose",
    "assets_boden": "assets_ground",
    "assets_hinweis": "assets_note",
    "at_waffe": "at_weapon",
    "attached_an": "attached_to",
    "aufbau_einheiten": "setup_units",
    "aufdecken_staging": "reveal_staging",
    "aufstellung_feld": "setup_field",
    "aufstellung_fertig": "setup_done",
    "ausserhalb": "outside",
    "bataillon_fm": "battalion_fm",
    "befestigung": "fortify",
    "befestigung_gesetzt": "fortifications_placed",
    "befestigung_zwischen_versuchen": "fortify_between_attempts",
    "befoerdert": "promoted",
    "beobachter": "observer",
    "bereich": "area",
    "bericht": "report",
    "bewegt": "moved",
    "bezahlt": "paid",
    "bis_zug": "until_turn",
    "bn_nicht_verfuegbar": "bn_unavailable",
    "breakdown_hinweis": "breakdown_note",
    "bunker_richtung": "bunker_direction",
    "capture_offen": "capture_open",
    "casualties_feind": "casualties_enemy",
    "cff_beobachter": "cff_observers",
    "cff_karten": "cff_cards",
    "cff_tabelle": "cff_table",
    "check_offen": "check_open",
    "co_immer_in_kommunikation": "co_always_in_comm",
    "co_immer_in_kommunikation_mit": "co_always_in_comm_with",
    "co_tac_mittel": "co_tac_medium",
    "crew_hit_offen": "crew_hit_open",
    "countermix_hinweis": "countermix_note",
    "cover_hinweis": "cover_note",
    "cover_kapazitaet": "cover_capacity",
    "cover_wert": "cover_value",
    "cover_werte": "cover_values",
    "datum": "date",
    "dreifuss": "tripod_legacy",
    "ebene": "level",
    "eigene_deckung": "own_cover",
    "eingebaut": "mounted",
    "einheit": "unit",
    "einheit_wahl": "unit_choice",
    "einheiten": "units",
    "einzelzug": "single_platoon",
    "ende": "end",
    "ereignis_einheiten": "event_units",
    "ereignis_erledigt": "events_done",
    "ereignis_flanke": "event_flank",
    "ereignis_munition": "event_ammo",
    "ereignis_pflicht": "event_task",
    "ereignis_route": "event_route",
    "ereignis_vorrat": "event_supply",
    "ereignistabellen": "event_tables",
    "erfahrung": "experience",
    "erfolg": "success",
    "erfuellt": "fulfilled",
    "erledigt": "completed",
    "ersatz_green": "replacement_green",
    "evakuiert": "evacuated",
    "exhort_frei": "exhort_free",
    "fahrzeug_reihenfolge": "vehicle_order",
    "fahrzeug_werte": "vehicle_values",
    "fahrzeuge": "vehicles",
    "fd_netz": "fd_net",
    "feind_erfahrung": "enemy_experience",
    "feind_erfahrung_versuch": "enemy_experience_attempt",
    "feind_gruppe": "enemy_group",
    "feind_taktik": "enemy_tactic",
    "feind_target": "enemy_target",
    "feinde_eliminieren": "eliminate_enemies",
    "feld": "field",
    "feuermissionen": "fire_missions",
    "fm_gesperrt": "fm_blocked",
    "fm_gruppe": "fm_group",
    "fm_hinweis": "fm_note",
    "fire_team_seite": "fire_team_side",
    "fm_wert": "fm_value",
    "fm_werte": "fm_values",
    "freund": "friendly",
    "ft_reichweite": "ft_range",
    "funk_aktiv": "radio_active",
    "funk_frei": "radio_free",
    "funk_zerstoert": "radio_destroyed",
    "g_karten": "g_cards",
    "gebaeude_tabelle": "building_table",
    "gefangene": "prisoners",
    "gefangene_nehmen": "take_prisoners",
    "gefeuert": "fired",
    "gegenangriff": "counterattack",
    "geplanter_gegenangriff": "planned_counterattack",
    "geprueft": "checked",
    "gespart": "saved",
    "gezogen": "drawn",
    "granate_antworten": "grenade_responses",
    "granate_vof": "grenade_vof",
    "grund": "reason",
    "gruppe": "group",
    "hat_gehandelt": "has_acted",
    "herkunft": "origin",
    "hinweis": "note",
    "hitze_offen": "heat_open",
    "hmg_ersatzmunition": "hmg_spare_ammo",
    "hoehe_plus": "elevation_plus",
    "illum_werte": "illum_values",
    "im_spiel": "in_play",
    "impuls_aktionen": "impulse_actions",
    "impuls_ausgegeben": "impulse_spent",
    "in_bewegung": "in_motion",
    "indirekt": "indirect",
    "infiltration_regel": "infiltration_rule",
    "kampf_ncm": "combat_ncm",
    "kampf_offen": "combat_open",
    "kapazitaet": "capacity",
    "karte": "card",
    "karten": "cards",
    "karten_folge": "card_sequence",
    "kartennummer": "card_number",
    "kartennummern": "card_numbers",
    "kartenschema": "card_layout",
    "kein_feuer_bis_clean_up": "no_fire_until_clean_up",
    "kein_point_blank": "no_point_blank",
    "keine_ereignisse": "no_events",
    "kommando": "command",
    "kommandos": "commands",
    "kompanie_jeep": "company_jeep",
    "kompanie_waffe": "company_weapon",
    "konzentration_gesetzt": "concentrations_placed",
    "konzentriert": "concentrated",
    "kritisch": "critical",
    "leitung_assets": "line_assets",
    "leitung_checks": "line_checks",
    "leitungen": "lines",
    "leitungen_pool": "lines_pool",
    "letzter_step": "last_step",
    "letzter_step_werte": "last_step_values",
    "letzter_versuch": "last_attempt",
    "licht": "light",
    "max_zuege": "max_turns",
    "min_reichweite": "min_range",
    "minen_check_info": "mine_check_info",
    "minen_checks": "mine_checks",
    "minen_redraw": "mine_redraw",
    "mission_nr": "mission_no",
    "missionen": "missions",
    "missionsende": "mission_end",
    "mitglieder": "members",
    "mlr_reihe": "mlr_row",
    "modus": "mode",
    "moerser": "mortar",
    "moerser_verbot": "mortar_banned",
    "moerser_wahl": "mortar_choice",
    "mtr_sec_funk_frei": "mtr_sec_radio_free",
    "munition_leer": "ammo_empty",
    "munition_traeger_abstrakt": "ammo_carriers_abstract",
    "munition_wenn_a": "ammo_if_a",
    "netz": "net",
    "nr": "number",
    "nur_pdf": "pdf_only",
    "nur_versuch": "attempt_only",
    "nur_wenn_verfuegbar": "only_if_available",
    "ohne_deckung": "no_cover",
    "ohne_einheiten": "no_units",
    "paket": "package",
    "paket_munition": "package_ammo",
    "paket_tabelle": "package_table",
    "paket_tabelle_gegenangriff": "package_table_counterattack",
    "pakete": "packages",
    "panzer_prioritaeten": "tank_priorities",
    "patrouille_mission": "patrol_mission",
    "patrouille_reserve": "patrol_reserve",
    "patrouille_wechsel": "patrol_change",
    "pc_a_karte": "pc_a_card",
    "pc_bc_karte": "pc_bc_card",
    "pc_herkunft": "pc_origin",
    "pc_marker_gesamt": "pc_markers_total",
    "pc_vorrat": "pc_supply",
    "pc_zufall": "pc_random",
    "pfad": "path",
    "platz": "place",
    "primaer_besucht": "primary_visited",
    "protokoll": "protocol",
    "punkte": "points",
    "pyro_belegung": "pyro_codes",
    "pyro_hinweis": "pyro_note",
    "quelle": "source",
    "r_platz": "r_place",
    "raender": "edges",
    "rally_offen": "rally_open",
    "rang": "rank",
    "reaktion_offen": "reaction_open",
    "reattempt_gesichert": "reattempt_secured",
    "reichweite": "range",
    "reihe": "row",
    "reihen": "rows",
    "reserve_einheiten": "reserve_units",
    "rfp_daten": "rfp_data",
    "richtung": "direction",
    "richtung_tabelle": "direction_table",
    "rifle_grenade_hinweis": "rifle_grenade_note",
    "rifle_grenade_je_platoon": "rifle_grenades_per_platoon",
    "rifle_grenade_reichweite": "rifle_grenade_range",
    "rkt_leer": "rkt_empty",
    "runner_hinweis": "runner_note",
    "runner_ziel": "runner_target",
    "schaden_offen": "damage_open",
    "schuetze": "shooter",
    "schuetzen": "shooters",
    "seite": "side",
    "sicht": "sight",
    "skills_hinweis": "skills_note",
    "sniper_offen": "sniper_open",
    "sniper_ziele": "sniper_targets",
    "sonderregeln": "special_rules",
    "spalte": "column",
    "stationaer": "stationary",
    "stern": "star",
    "sternchen": "asterisks",
    "stornos": "cancellations",
    "symbole": "symbols",
    "taktik": "tactic",
    "taktik_vorher": "tactic_before",
    "teilgenommen": "took_part",
    "telefon_hinweis": "phone_note",
    "telefon_leitungen": "phone_lines",
    "terrain_katalog": "terrain_catalog",
    "titel": "title",
    "traegt_casualties": "carries_casualties",
    "traegt_munition": "carries_ammo",
    "typ": "type",
    "typ_nach": "type_after",
    "typname": "type_name",
    "unbeweglich": "immobile",
    "unterwegs_seit": "en_route_since",
    "us_casualties_gesamt": "us_casualties_total",
    "us_gefangen": "us_captured",
    "varianten": "variants",
    "verdeckt": "face_down",
    "verfuegbar": "available",
    "verifiziert": "verified",
    "versuch": "attempt",
    "versuch_plan": "attempt_plan",
    "versuche_max": "attempts_max",
    "veteran_je_casualties": "veteran_per_casualties",
    "vorrat": "supply",
    "wachen": "guards",
    "wahl": "choice",
    "werfer": "launcher",
    "wert": "value",
    "wetter": "weather",
    "wetter_nur_zug": "weather_this_turn_only",
    "wrack": "wreck",
    "xp_hinweis": "xp_note",
    "xp_karten": "xp_cards",
    "xp_tabelle": "xp_table",
    "zeile_kompakt": "line_compact",
    "zeilen": "modifiers",
    "zeit": "time",
    "ziel": "target",
    "ziel_offen": "target_open",
    "ziel_regeln": "objective_rules",
    "ziele": "objectives",
    "ziele_hinweis": "objectives_note",
    "ziele_quelle": "objectives_source",
    "ziele_reihen": "objective_rows",
    "zuege": "turns",
    "zufall": "random",
    "zug": "turn",
    "zusatzkarte": "extra_card",
    # ---------------------------------------------------------------- open rules questions (option ids)
    "U2_fo_fd_funk": "U2_fo_fd_radio",
    "U3_incoming_blockiert_funk": "U3_incoming_blocks_radio",
    "U4_as_zaehlt_als_a": "U4_as_counts_as_a",
    "U6_aktivieren_im_initiative_impuls": "U6_activate_in_initiative_impulse",
    "U7_lat_behaelt_funk": "U7_lat_keeps_radio",
    "U9_ziel_lesart": "U9_objective_reading",
    "U10_staging_funk_ueber_hill": "U10_staging_radio_over_hill",
    "U11_plt_mtr_ueber_hub": "U11_plt_mtr_via_hub",
    "U12_indirekt_unter_gi": "U12_indirect_under_gi",
    "U12_moerser_reichweite": "U12_mortar_range",
    "U13_target_marker_bei_short": "U13_target_marker_on_short",
    "U14_telefon_diagonal": "U14_phone_diagonal",
    "U15_leitung_automatisch": "U15_line_automatic",
    "U16_erste_commands_mit_gespart": "U16_first_commands_with_saved",
    "U17_gegenangriff_staging": "U17_counterattack_staging",
    "U18_fall_back_rand_offmap": "U18_fall_back_edge_offmap",
    "U19_erweitern_bis_reichweite": "U19_extend_to_range",
    "U20_mine_bei_seek_cover": "U20_mine_on_seek_cover",
    "U21_pyro_alle_einheiten": "U21_pyro_all_units",
    "U22_munition_leer_im_clean_up": "U22_ammo_empty_in_clean_up",
    "U27_mtr_sec_nicht_fa": "U27_mtr_sec_not_fa",
    "U28_gegenangriff_alle_pc_a": "U28_counterattack_all_pc_a",
    "U29_ein_target_marker_he_wp": "U29_one_target_marker_he_wp",
    # ---------------------------------------------------------------- values
    "Feind": "Enemy",
    "Links": "Left",
    "Rechts": "Right",
    "bei_squad": "with_squad",
    "cp_erfolg": "cp_success",
    "cp_primaer": "cp_primary",
    "defensiv": "defensive",
    "eingeschraenkt": "limited",
    "feind_casualty_step": "enemy_casualty_step",
    "feind_panzer": "enemy_tank",
    "feind_truck": "enemy_truck",
    "gefangene_step": "prisoner_step",
    "geplant": "planned",
    "gruen": "green",
    "hq_ereignis_stern": "hq_event_star",
    "ja": "yes",
    "keine": "none",
    "keiner": "none",
    "links": "left",
    "mit_vorigem": "with_previous",
    "mit_zufaelligem": "with_random",
    "nein": "no",
    "oben": "top",
    "offen": "open",
    "offensiv": "offensive",
    "pb_granate": "pb_grenade",
    "pc_klaeren": "clear_pcs",
    "primaer": "primary",
    "rechts": "right",
    "reihen_klaeren": "clear_rows",
    "sekundaer": "secondary",
    "sektion": "section",
    "sichern": "secure",
    "tag": "day",
    "telefon": "phone",
    "unbegrenzt": "unlimited",
    "unten": "bottom",
    "verzicht": "pass",
    "weiss": "white",
    # ---------------------------------------------------------------- commands (English name in cli.COMMANDS)
    "ablegen": "drop",
    "aktivieren": "activate",
    "aufstellen": "setup",
    "befehl": "order",
    "ereignis": "event",
    "erweitern": "extend",
    "extern": "external",
    "fahrzeug": "vehicle",
    "feind": "enemy",
    "feindaktion": "enemyaction",
    "feindcheck": "enemycheck",
    "fertig": "done",
    "feuer": "fire",
    "funk": "radio",
    "gefangen": "capture",
    "granate": "grenade",
    "hilfe": "help",
    "hitze": "heat",
    "kampagne": "campaign",
    "korrektur": "correct",
    "leitung": "line",
    "mehrstoeckig": "multistory",
    "munition": "ammo",
    "nachtrag": "lateorder",
    "neu": "new",
    "notiz": "note",
    "optionen": "options",
    "patrouille": "patrol",
    "pruefung": "check",
    "regel": "rule",
    "rekon": "reconstitute",
    "rueckzug": "retreat",
    "rundenende": "endturn",
    "stand": "status",
    "suche": "search",
    "treffer": "hit",
    "werte": "set",
    "zurueck": "undo",
    # ---------------------------------------------------------------- sub-command words
    "antwort": "response",
    "aufdecken": "reveal",
    "aus": "off",
    "ausgeben": "spend",
    "befoerdern": "promote",
    "bewegen": "move",
    "dazu": "add",
    "frei": "clear",
    "heil": "intact",
    "kontakt": "contact",
    "konzentration": "concentration",
    "lager": "depot",
    "legen": "lay",
    "naechste": "next",
    "nochmal": "again",
    "plus": "add",
    "pruefen": "check",
    "reaktion": "react",
    "schaden": "damage",
    "setzen": "set",
    "spotten": "spot",
    "verfallen": "expired",
    "verkehr": "traffic",
    "weg": "remove",
    "weiter": "next",
    "zerstoert": "destroyed",
}

# German command names (the dispatch keys until) -> English command name (cli.COMMANDS)
COMMANDS_DE = {
    "ablegen": "drop",
    "aktivieren": "activate",
    "aufstellen": "setup",
    "befehl": "order",
    "ereignis": "event",
    "erweitern": "extend",
    "extern": "external",
    "fahrzeug": "vehicle",
    "feind": "enemy",
    "feindaktion": "enemyaction",
    "feindcheck": "enemycheck",
    "fertig": "done",
    "feuer": "fire",
    "funk": "radio",
    "gefangen": "capture",
    "granate": "grenade",
    "hilfe": "help",
    "hitze": "heat",
    "kampagne": "campaign",
    "karte": "card",
    "korrektur": "correct",
    "leitung": "line",
    "mehrstoeckig": "multistory",
    "munition": "ammo",
    "nachtrag": "lateorder",
    "neu": "new",
    "notiz": "note",
    "optionen": "options",
    "patrouille": "patrol",
    "pruefung": "check",
    "regel": "rule",
    "rekon": "reconstitute",
    "rueckzug": "retreat",
    "rundenende": "endturn",
    "sicht": "visibility",
    "stand": "status",
    "suche": "search",
    "treffer": "hit",
    "werte": "set",
    "ziel": "objective",
    "zurueck": "undo",
}

OPTION_WORDS = {
    "--agentur": "--agency",
    "--aus": "--from",
    "--bataillon": "--battalion",
    "--bei": "--at",
    "--bereich": "--area",
    "--einheit": "--unit",
    "--erfahrung": "--experience",
    "--erfolg": "--success",
    "--ergebnis": "--result",
    "--fahrzeuge": "--vehicles",
    "--gebaeude": "--building",
    "--gebaeude_wert": "--building-value",
    "--geraet": "--device",
    "--granate": "--grenade",
    "--gratis": "--free",
    "--grund": "--reason",
    "--hoehe_plus": "--elevation",
    "--kosten": "--cost",
    "--kritisch": "--critical",
    "--leitung": "--line",
    "--leitungen": "--lines",
    "--mit": "--with",
    "--moerser": "--mortar",
    "--nach": "--to",
    "--netz": "--net",
    "--normal": "--plain",
    "--nr": "--no",
    "--nur_zug": "--this-turn-only",
    "--partie": "--game",  # step.py
    "--platz": "--place",
    "--quelle": "--origin",
    "--raender": "--edges",
    "--reichweite": "--range",
    "--richtung": "--direction",
    "--roh": "--raw",
    "--seite": "--side",
    "--skill-von": "--skill-from",
    "--target_marker": "--move-target-marker",
    "--typ": "--type",
    "--typ-neu": "--new-type",
    "--variante": "--variant",
    "--von": "--source",
    "--waffe": "--weapon",
    "--wahl": "--choice",
    "--was": "--what",
    "--wer": "--who",
    "--wert": "--value",
    "--ziel": "--target",
    "--zusatz": "--extra",
}

# containers whose keys are names (units, cards, HQs, terrain types), never translated themselves
NAME_KEYED = {
    "einheiten",
    "units",
    "reserve_einheiten",
    "reserve_units",
    "aufbau_einheiten",
    "setup_units",
    "karten",
    "cards",
    "kommandos",
    "commands",
    "impuls_aktionen",
    "impulse_actions",
    "impuls_ausgegeben",
    "impulse_spent",
    "rfp_daten",
    "rfp_data",
    "terrain_katalog",
    "terrain_catalog",
}

assert not set(WORDS) & set(WORDS.values()), "a German word must not also be an English target (idempotence)"
assert not set(OPTION_WORDS) & set(OPTION_WORDS.values()), "a German option must not also be an English option"


def german(english: str) -> tuple[str, ...]:
    """The German words that mean `english` (input aliases a handler accepts besides the English word)."""
    return tuple(g for g, e in WORDS.items() if e == english)


def word(w: Any) -> Any:
    """English form of one stored word; anything else unchanged."""
    return WORDS.get(w, w) if isinstance(w, str) else w


HILL = re.compile(r"^(.+) auf (\d+) Hill$")  # terrain of a card on a hill, as written before ('Woods auf 1 Hill')


def _value(v: Any) -> Any:
    if isinstance(v, str):
        v = HILL.sub(r"\1 on \2 Hill", WORDS.get(v, v))
        for de, en in MARKERS.items():
            v = v.replace(de, en)
        return v
    if isinstance(v, (dict, list)):
        return _walk(v, False)
    return v


def _walk(o: Any, names: bool) -> Any:
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            nk = k if names else WORDS.get(k, k)
            if nk in out:
                raise ValueError(f"German and English key {nk!r} in the same structure")
            out[nk] = _walk(v, k in NAME_KEYED) if isinstance(v, dict) else _value(v)
        return out
    if isinstance(o, list):
        return [_value(v) for v in o]
    return _value(o)


# phrases in free text an older note may contain (enemy action text)
PHRASES = {"keine feuerauftraege": "no fire missions"}
# markers inside stored notes, replaced wherever they occur in a string
MARKERS = {
    "UNVERIFIZIERT": "UNVERIFIED",
    # source of a terrain type recorded from the board (setup.set_terrain) before
    "beim Aufdecken vom Brett abgelesen": "read from the card on the board when revealed",
}

# ---------------------------------------------------------------- file names
# game folder: state file and snapshot folder; project root: pointer to the current game; environment variable
FILES = {
    "game_state.json": "spielstand.json",
    "history": "verlauf",
    ".current_game": ".aktuelle_partie",
}
ENV = {"FOF_GAME": "FOF_PARTIE"}
# data folder: rule texts and the action card archive written by earlier releases of build_rules_index.py
DATA_FILES = {
    "rulebook.txt": "regelbuch.txt",
    "rulebook_compact.txt": "regelbuch_kompakt.txt",
    "rule_index.json": "regelindex.json",
    "clarifications_2025_05_compact.txt": "clarifications_2025_05_kompakt.txt",
    "action_cards.json": "karten.json",
}
COMPACT_SUFFIX = ("_compact.txt", "_kompakt.txt")  # searched rule texts: new suffix, suffix of earlier releases


def path(folder: Any, name: str, table: dict[str, str] | None = None) -> Any:
    """folder/name, or the file of the same meaning under its name of an earlier release when only that one exists."""
    new = folder / name
    old = (table if table is not None else {**FILES, **DATA_FILES}).get(name)
    return folder / old if old and not new.exists() and (folder / old).exists() else new


def adopt(folder: Any) -> None:
    """Rename the state file and the snapshot folder of a game folder from an earlier release to the English names
    (a rename, no delete: works where the shell may not delete files)."""
    for new, old in (("game_state.json", "spielstand.json"), ("history", "verlauf")):
        if (folder / old).exists() and not (folder / new).exists():
            (folder / old).rename(folder / new)


def env(name: str, environ: Any) -> str | None:
    """Environment variable `name`, or its name of an earlier release."""
    return environ.get(name) or environ.get(ENV.get(name, ""))


RULE_INDEX = {"titel": "title", "seite": "page", "zeile_txt": "line_txt", "zeile_kompakt": "line_compact"}


def rule_index(idx: dict[str, Any]) -> dict[str, Any]:
    """English keys of a rule index (regelindex.json) built before ('seite' is the page here, not a side)."""
    return {k: {RULE_INDEX.get(a, a): b for a, b in v.items()} if isinstance(v, dict) else v for k, v in idx.items()}


def state(obj: Any) -> Any:
    """English form of a game state, setup file or snapshot written before (keys and exact string values);
    an English file passes unchanged."""
    if not isinstance(obj, dict):
        return obj
    if not ({"einheiten", "karten", "protokoll"} & set(obj)):
        # an English game of - may still carry the German source text of a terrain type read from the board
        for entry in (obj.get("terrain_catalog") or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get("source"), str):
                entry["source"] = _value(entry["source"])
        return obj
    return _walk(obj, False)


def data(obj: Any) -> Any:
    """English form of any other JSON file of the engine (data tables, rule index), without the format check."""
    return _walk(obj, False)
