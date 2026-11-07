# Changelog

## 2026-11-07 (eighth release)
This release comes mostly from a full review of the engine code rather than from play at the table. The fixes come
with tests. It also adds the company jeep for Naktong River Mission 1.
- Company jeep (Naktong Mission 1, 10.8.1): a jeep without crew that carries up to two steps of infantry
  (`order <HQ> <unit> 4.2.2h --what=jeep`, the same order again to dismount). It is activated by an HQ or Staff on
  board, or by an HQ in visual or verbal contact with command over a passenger. Its experience is the highest on board
  (10.8.8) and is recalculated whenever the game is loaded or saved; vehicle and passengers move as one. L528, L548
- Step runner: `zug.py` decides by the exit code of `fof.py` (0 legal, 2 VIOLATION, anything else an error). Help
  texts or notes that contain the word VIOLATION no longer stop a step, a crash books nothing, and an error in the
  real run names the commands that were already booked but not committed. `new` creates missing parent folders and
  does not leave the game pointer on a game that failed to save; an invalid setup file is a violation. Arguments that
  used to crash the engine (`steps=null`, a doubled `--from` or `--with`, an invalid `--experience`, a bare
  `--success`) are refused, and `--plain=no` now means no. L529, L547
- Vehicle phase (3.6): sides alternate after every enemy tank action (before, all enemy tanks acted in a row before
  the first US vehicle). Reaction Fire is an open window in the plan: when an enemy vehicle moves or fires in LOS and
  range of a US AT unit, the tool stops until each firing unit is booked with `vehicle react <unit> <vehicle>` or the
  window is closed with `vehicle react pass`. Enemy tank Concentrate Fire takes `--target=<unit>`. Move & Fire with
  several targets is a plan step after VOF and Reaction Fire, and a tank whose chart has no Move & Fire value
  (SU-76M) does not fire after moving. Crew losses of a brewed up vehicle are handled as normal casualties, and an
  enemy route over a card with unknown trafficability is refused instead of taking a silent detour. L531, L543, L551
- Enemy: point blank and bunker facing are cleared when a unit leaves its bunker or pillbox; a unit in a Deep Bunker
  gets no target at placement and ceases fire before it opens fire after leaving; cover choice respects the capacity
  of the marker (5.3.2), so a Fall Back under full foxholes can be booked; Fall Back with Casualty takes the casualty
  along; Paralyzed and Litter Teams moving towards a casualty do not enter a card under VOF; with option U20 a
  successful enemy Seek Cover on a mined card asks for a mine check; enemy Rally keeps a flip caused by running out of
  ammo (only resupply removes it); Advance from row 1 avoids diagonals across a PDF; enemy Infiltrate goes only onto
  a step card towards the nearest opponent; a Litter Team at its own map edge leaves the map with its casualty.
  L532-L534, L539-L541, L550, L551
- Contacts: a G! grenade attack at contact uses the full grenade resolution (whole stack, Critical Hit, Jam);
  `pc set` with a second open letter applies 8.2.3 at once. L542, L550
- Orders and fire: Move and Infiltrate share one test for VOF or Grenade Miss on the start or destination card
  (before, a unit under its own point blank VOF could do neither); removing an Incoming or Air Strike marker in 3.7.1
  also checks for lost LOS; a Staff that gives up its step in 4.2.1d ends the HQ's impulse, and 4.2.1d is limited to
  PLT HQs; removing a counter clears its open mine check, rally, heat, capture and sniper prompts; Retreat uses the
  normal move path (Grenade VOF, mine check, wire); refusals that depend on the state of the game come before the
  draw prompt; Move within a Card refuses jeep passengers; the free answer roll (always point blank) has no Jam
  branch; Indirect Lay ceases the previous fire; a change of target clears the fields of the old target; usage texts
  match the words the command line accepts. L535-L538, L544-L546, L549, L550
- Housekeeping: Hold Up is removed in Clean Up; snapshots and BRIEFING.md are written atomically, and undo checks
  the snapshot before using it; `visibility --this-turn-only` needs a weather value; `extend` from row or column 10
  is refused. L551, L554
- Structure, without effect on play: a register of every key in the game state with its meaning and lifetime
  (`tool/fof/keys.py`; with `FOF_KEY_CHECK=1`, as in the tests, a state with an unregistered key is not saved);
  `commands.py` split into `fire_support`, `grenades`, `pickup` and `pyro`; the five longest functions split up;
  type annotations at the module boundaries, with a mypy test where mypy is installed; a new `ARCHITECTURE.md` that
  explains how the engine is built. L530, L554-L558
- Tests: 549 tests in the full project (the kit skips those that need mission data).

## 2026-11-05 (seventh release)
Engine updates from the first game of the Korea campaign at the table (Naktong River Mission 1, attempt 1 and most of
attempt 2, counter attack included) and from a BGG research pass on open rules questions:
- Setup: rifle grenades as one 2-shot counter per platoon where the mission says so; free radios from the TO&E
  (`setup <unit> --device=<type>`); packages with a random number of units or a leader that joins a randomly drawn
  squad (`--leader-squad=<n>`); package variants with R# bands from the mission table (Naktong package 1:
  Artillery or Mortar). L491, L492, L521, L522
- Face-down cards: a card seen only across another face-down card is announced as WAIT until the nearer card is
  revealed (5.2.2). L493
- Contacts: building table column and source taken from the campaign; G! first fire names the number of cards;
  enemy package infiltration draws 2 cards adjusted for experience; Max LOS of a package without PDF counts the
  trigger's view into a card with Incoming or Smoke (5.4, 8.4.3). L494, L497, L519, L525
- Fire: the Sniper VOF marker (-3) is announced like every other marker; LOS and range are checked again after the
  visibility change at the end of a turn; the fire follows the last unit under a VOF that moves one card further along
  the same PDF (6.3.4); a failed ranged enemy Grenade Attack places a Grenade Miss marker (7.10.4). L495, L498, L513,
  L518
- Orders: a Move is refused while Infiltrate is possible (book it on purpose with `--plain=yes`); a Platoon Move or
  Infiltrate counts as the single action of every member (4.2); a detached team is placed without an Exposed marker
  (2nd printing; replaces L496); a Pinned or Paralyzed unit must drop radios, assets and casualties before it moves
  (4.2.5); Flip to Front of a unit that flipped only because it ran out of ammo needs `--ooa-flip=yes` (open U45);
  Call for Fire by PLT HQs where the fire support table has a PLT HQ column (7.16.1, CO TAC relay); a jeep-mounted
  radio also works for the dismounted observer on the jeep's card. L496, L509, L509a, L511, L512, L514, L523, L524,
  L526
- Enemy: Grenade VOF on a unit counts as Under Fire; row Z5 needs a visible target on the PDF card; Fall Back of a
  Pinned unit or LAT without a legal card asks for a redraw (Stead: "Redraw if a move isn't possible"). L510, L515,
  L517
- Events and campaign: heat casualties read R#/4 = 1 only, end with the attempt, and convert the last step like a
  hit (the new Fire Team is not pinned); the reattempt removes saved Commands, puts enemies into freed cover, uses
  the secured cards at the end of the attempt, and keeps free radios; the capture note names the campaign's prisoner
  rule; the 3.7.2 list is sorted by PC letter. L499-L508, L516, L520
- `fof.py` refuses options that belong to `zug.py` (`--probe`, `--all`, `--msg`). L501
- Tests: 459 tests in the full project (the kit skips those that need mission data).

## 2026-10-31 (sixth release)
Engine updates from Normandy Mission 7 (campaign complete) and first building blocks for the Korea campaign:
- Game step runner: new `tool/zug.py`, one call per game step (commands on stdin), probe in a scratch copy, booking
  only without VIOLATION, then git commit; undo works in the probe; new result `OPEN:` (exit 0) for steps that are
  saved and wait for a draw (first case: VOF against vehicles at the end of 3.6). L470, L474, L475
- History: snapshots in `verlauf/` are a ring of 41 files, also where the file system does not allow deletes. L471
- Setup: packages with an optional extra on a die roll (`--extra=yes|no`), single-variant packages need no
  `--variant`, objective rows per mission (`ziele_reihen`, `ap_neben`), `terrain --cc2=none`, Normandy CSR 1 Arty
  Jeep (`setup "Arty FO" --jeep=yes|no`). L452-L456, L467, L469
- Fire: Concentrate Fire takes the only spotted enemy without `--unit`; Shift Fire names the PDF marker correctly;
  moving with Cease Fire names the PDF left behind; HC/WP smoke on a firing card keeps the VOF on the own card
  (6.1.2); opening fire takes the own card first when both sides are on it (6.2.1b); after a capture the shooters
  whose only target were the prisoners open fire anew (6.3.3); `WATCH friendly fire` when a unit moves onto a card
  under friendly VOF. L457, L458, L461, L462, L466, L468, L472
- Orders: Rally on an unpinned generic LAT names the upgrade action (4.2.3b-d); a second failed Grenade Attack keeps
  one Miss marker (7.10.4); `vehicle spot` checks LOS like infantry Spot (5.4); vehicle fire hint only with an enemy
  vehicle in LOS and range; Arty Jeep riders are not marked Exposed inside the Staging Area. L459, L460, L463-L465
- Enemy: Fall Back avoids diagonals that cross a PDF (5.1.2). L473
- Skill name unified: "Auto Concentrate" (the old "Auto Concentrate Fire" is accepted as alias). L476
- Korea building blocks (Naktong River Mission 1, preliminary, not yet played at the table): attempt plan with
  turns, visibility per turn, enemy experience and package ammo per attempt; fortifying secured objectives between
  attempts (`objective fortify`); no prisoners (8.15); Korea chart rows and recoilless rifles (75mm RCL cannot fire
  while Exposed, no RCL fire from building/bunker cover); face-down cards with reveal prompts and a lock until
  revealed; new terrain types during setup (`terrain ... --new-type=yes`); Heat Casualties (`heat <unit> yes|no`);
  Naktong counter attack (CSR 5) incl. the planned counter attack; event units with a pool (.50 cal HMG); Human Wave
  (8.14: PIN becomes MISS, every hit a casualty, never pinned); enemy tank priorities 1 to 4 and enemy vehicles
  activated every turn (MSR 3, CSR 9), tanks out of ammo leave the board. L477-L488
- Tests: 16 new test files, 421 tests in the full project (the kit skips those that need mission data).

## 2026-10-24 (fifth release)
Engine updates from Normandy Missions 5 and 6 (the first mission with tanks and AT guns) and from a full code review
of the engine:
- Vehicles and AT combat (chapter 10): new module `vehicles.py` with the Vehicle and AT Weapons chart (WWII rows, AT
  modifiers, result V), vehicles as units (crew = steps, Tank HQ as HQ), action 4.2.1i Activate for AT Combat, the
  AT Combat & Vehicle Movement Phase 3.6 with alternating actions (10.5.1), activation groups (tanks, jeeps, AT guns
  and AT-capable infantry), trafficability per terrain, move, fire, Concentrate Fire and Spot as plan steps, Reaction
  Fire, enemy vehicle and AT actions, AT draws (`at <number>`), wrecks with cover, Grenade VOF and friendly fire on
  vehicles (10.5.3), stacking counts infantry steps only (5.1.5). Commands `vehicle ...` and `at ...`. L187-L196,
  L200, L201, L205, L214, L290-L305
- Fire: VOF markers per 6.2.1 (top marker from outside, best friendly and best enemy Point Blank VOF as corner
  markers); units waiting for a target choice on one card join the first PDF instead of laying a second one (6.3.5);
  PDF markers that disappear are named for removal; Battalion Fire Mission hint after 3 bursts (7.16.2B); mortars
  never fire from building cover (7.3.1); Cease Fire is passed to every unit on the card (4.2.4k). L179, L198, L203,
  L206, L207, L217, L218
- Grenades and ammo: the grenade marker expires as Grenade Miss when the target seeks cover within its card (7.10.4);
  rockets are used for grenade attacks only (7.18.1D); jam-prone detection for rocket teams and Out of Ammo units
  (7.12); new Fire Teams after a jam open fire at once; weapon choice `--weapon=rifle|own` for a unit with its own
  ranged grenade and a picked-up rifle grenade; Pick Up needs `--what`. L171-L178, L211, L216
- Enemy: Fall Back of pinned enemies and enemy Paralyzed/Litter Teams avoids cards with a VOF; enemy Seek Cover on
  village/farm/church cards can find buildings (Normandy CSR 8); removed enemy counters go back to the counter mix and
  their numbers are reused; one movement path for every enemy move (ammo surplus, grenade expiry, Exposed, cover,
  fire after move, mine check); the Enemy Activity Check hierarchy is data instead of code; defensive missions use
  the right enemy segments (3.2.1/3.2.2). L213, L215, L219, L260-L282, L320
- Capture and retreat: vehicles and pinned units are no captors (3.5.1), `phase next` waits for an open capture,
  the guard must meet the captor conditions, prisoners leave the board through one removal path. L199, L208, L209,
  L370-L374
- Campaign: `reconstitute` only during the reattempt preparation (3.9); mission number in the patrol end text;
  `patrol next` checks platoon and `--with` before it books anything. L185, L186, L336
- Input checks everywhere: missing or non-numeric arguments are a VIOLATION with the usage instead of a traceback;
  options come from an explicit registry (unknown, empty and repeated options are refused); English value aliases
  (yes/no/open ...) are translated only for enumerations, free text stays untouched; `--move-target-marker` no longer
  overwrites the Call for Fire target. L192, L212, L220-L223, L230-L257, L330-L338, L373
- Safety: `new` refuses a folder that already holds a game (`--force` to overwrite) and checks the setup before it
  switches the current game; the game state is written atomically; a damaged `spielstand.json` names the latest
  snapshot to restore. L223, L335, L348
- Initiative and General Initiative prompts name the small number in the star, not the helmet number. L210, L212
- Speed: one fire map per read-only pass (marker summary, activity level, NCM rows), the state is read once per
  command, a Platoon Move runs the board-wide fire check once after the last member. L344, L349, L382, L450
- Code structure (no change in play): `cmd_order`, `cmd_vehicle`, `cmd_at`, `cmd_setup`, `cmd_end_turn` and the
  briefing split into small functions; segment tables in `phase.py`; dataclasses for the order context; status
  markers as constants; `undo` lives in `history.py`. L255, L256, L304, L342, L343, L383-L385, L420-L448
- Tests: 332 pass in a clean copy of the kit; 45 skip because they need the Normandy mission setups or game
  states, which are not part of the kit (they run in the author's project: 376 pass). Regression games
  (Normandy M1 357 commands, M4 98 commands) unchanged except one intended correction: a Fire Team that becomes a
  casualty is now listed as Removed from Play. L350

## 2026-10-18 (fourth release)
Engine updates from a rules audit against the rulebook examples and from Normandy Mission 5 play (night combat
patrols, three platoons one after the other):
- Fire: Grazing Fire for tripod MGs along the whole PDF up to maximum range, same elevation or a steady slope only
  (7.2.2); Overhead Fire also for tripod MGs with an A VOF (7.2.3 examples); out of range keeps the PDF and puts the
  VOF on the last card in range (6.3.2 example); Smoke or Incoming! on the firing card turns the fire into a
  Point Blank VOF on that card (6.1.2 example 1); when the last Point Blank target moves to an adjacent card the
  fire follows it (6.3.4). L128, L147, L148, L149
- NCM: every fire effect on a unit (direct VOF, Incoming-type VOF, Mines!, Sniper, Grenade, Grenade Miss) is
  worked out with its own modifiers and the strongest total counts (6.4, Clarification 3). L129
- New actions 4.2.4c Platoon Concentrate Fire and 4.2.4h Platoon Grenade Attack: each eligible unit of the
  platoon on the HQ card makes its own attempt (`--success=<unit>:yes|no,..`). L136
- Concentrate Fire: one extra card for a tripod MG (7.11.2); the target must be a spotted enemy the shooter can
  see itself (7.11.1, 5.2.2 Fig 3), for enemy CF too; Critical Hit with `--critical=yes` (7.11.4). L137, L140, L150, L154
- New command `grenade response <unit> --success=yes|no [--critical=yes] [--jam=yes]` for the free response of
  7.10.5, offered with the card count after a Point Blank grenade attack, for both sides, no Command. L144
- Every card draw request with a success symbol adds a WATCH line: Jam symbol for jam-prone units (7.12),
  Critical Hit on 2 or more symbols (7.10.3, 7.11.4), Short on Call for Fire (7.16.4). L153
- Combat Effects: new command `ncm next` shows the next group of 3.7.4 as a numbered list (card, NCM and column,
  number of cards to draw, units in order, NCM rows one per line); printed again after every `hit`. L155, L156
- Enemy AI: Fall Back priorities 2 (out of LOS) and 3 (best cover) are computed and enforced (8.6.3); enemy moves
  check diagonals through a PDF (5.1.2); Deep Bunker handling (Normandy CSR 5); enemy Seek Cover respects the
  card's Cover Potential (5.3); leader extra card for every enemy attempt (8.9); target on the same card is the
  largest stack (8.6.1B); ammo surplus on every enemy movement (8.11); enemy Infiltrate names the closest
  opponent cards and is a normal move with Exposed when neither card has a VOF (5.1.4); enemy Advance and
  Infiltrate take the best free or own Cover marker on the new card (8.6.1E). L130, L131, L133, L141, L142, L143,
  L145, L168, L169
- LATs: a HIT that turns one LAT type into another takes that type's VOF and range (Assault Team A, Point Blank;
  Fire Team S, Close); enemy Rally of an unpinned Assault Team is reported as already the highest LAT. L163, L165
- Contact: equal PC letters name the cards and the R# column for the random order (8.2.4); missing package cover
  values are a VIOLATION instead of a silent +1; package placement is blocked by units between the placement card
  and the trigger unless Grazing or Overhead Fire applies (8.4.3 examples). L134, L135, L151
- Campaign: US guard steps from a capture return between missions with their experience level (8.15); new
  commands `xp promote <unit> --from=Green|Line --steps=n` and `xp skill <HQ> <skill>` (12.3, 12.3.1, 12.7, skill
  marker countermix); in combat patrols only units of finished patrols can be promoted, counted per step;
  `reconstitute` derives the level from table 12.6 and counts every LAT as a Green step (3.9, 12.2). L126, L146,
  L152, L158, L166, L167
- Small rules checks: coloured smoke cannot signal at night (4.4.1); Infiltrate within a card refused for tripods,
  H VOF, mortars and Exposed units (5.1.4); dark Hill borders replace light ones (5.2.2A); Move or Infiltrate onto
  a card with a free Cover marker reminds you of 5.1.2; Initiative impulses of PLT HQs and staff are listed "in
  any order you choose" (3.3.2b/c); Out of Ammo without LOS no longer reports a VOF shift. L138, L139, L157, L161,
  L162, L164
- Small fixes: `patrol start` reads the row 1 cards from the map; `objective` without arguments prints its usage.
  L159, L160
- Tests: 40 worked examples from the Series Rules as unit tests (`tests/test_examples_a/b/c.py`, one skipped:
  enemy reconstitution 6.5.2 is not built), coverage tests for Mission 5 rules; 84 tests pass. Regression games
  (Normandy M1 357 commands, M4 98 commands) unchanged except two intended corrections (Fall Back priority 3,
  Smoke on the firing card).

## 2026-10-13 (third release)
Engine updates found during Normandy Mission 4 play (counter attack, grenade fights, retreats and captures), plus
the fall-back and grenade rulings collected from the BGG rules forum after the mission:
- New command `retreat <unit> [<card>]` (German `rueckzug`) for 3.5.2: checks whether a retreat is mandatory
  (unpinned, not Exposed, under a VOF; Litter Teams only with a casualty), picks the card one row towards the
  friendly edge without a VOF, then the highest C&C (ties by R#), the Litter Team takes the casualty along, the
  unit becomes Exposed. `phase next` out of 3.5.2 is refused while a mandatory retreat is still open. L110, L123
- Capture (3.5.1, 8.15): Paralyzed/Litter Teams that are alone on their card are taken as one group with a single
  guard step; enemy casualties on that card are captured right after. L117
- Enemy fall back (8.6.3): priority 1 (off-map) is enforced when the unit stands on or behind the top mission row
  and one of the three places towards the enemy edge has no card, or when it stands beyond a side boundary;
  `--target=off-map` is rejected in every other position. L125
- Grenade attacks hit the whole stack under a cover marker (7.10.1), for enemy attacks too; Critical Hit (7.10.3)
  with `--critical=yes`; no Grenade Miss marker while part of the hit stack remains (7.10.4); the free grenade
  response (7.10.5) is offered only against a point-blank attack from the same card, never from a bunker or
  pillbox, never while Pinned, and is listed per unit of the hit stack. L112, L115, L116, L124
- Opening fire: a unit on a card that already has a friendly PDF joins that fire (6.1.1); no target behind a
  nearer card with visible enemies (6.1.2); a PDF that already lies on the same card to the same target is
  reported instead of a second marker. L121, L122
- Cease Fire and Shift Fire reach every firing unit of the card, not only those with the same target (4.3.1
  note). L114
- Every save now reports changed VOF markers (strongest VOF per card), Crossfire markers, and new or ended mutual
  PDFs (6.3.1) as Board lines before the CHECKSTAMP; during 3.7.4 these reports are held back and compared once
  against the state at the start of the segment. L111, L113, L119
- Every movement lists the markers that travel with the unit (Pinned, ammo, Out of Ammo, assets, radios). L109
- Infiltrate (4.2.2c) checks 5.1.4 (a VOF on the start or target card) before asking for the card draw;
  Engineers infiltrating within a mine card need no `--area` (Normandy CSR 10). L107, L120
- An enemy moving onto a card where spotted and unspotted enemies would mix makes the whole card spotted
  (8.5). L108
- Small fixes: English area names in the move-within-a-card message, `hit` without arguments prints its usage. L105, L118

## 2026-10-12 (restructuring, same behaviour)
- New command `undo <entry> --reason=..` (German `zurueck`): every save keeps a snapshot of the state in
  `<game>/verlauf/<entry>.json` (last 40 entries); undo restores one and lists the discarded entries.
- Fix after the rename: 35 keyword arguments that write game-state keys (`update(karte=...)`, `dict(punkte=...)`)
  had been renamed to English; restored, guarded by `tests/test_state_keys.py`.
Verified with two state-based regression games (454 commands): identical exit codes and identical final game
states before and after every step.
- One engine package `tool/fof/` (16 modules) instead of a 9000-line file; `tool/fof.py` is the entry point.
- English identifiers for functions, constants, parameters and locals (4560 renames); JSON keys and stored values
  stay German (GLOSSARY.md), so existing game states keep working.
- `ruff format` (line length 120) and `ruff check` clean; `pyproject.toml`.
- The 550-line order function is one handler per action class (`ORDER_HANDLERS`), enemy actions one handler per
  result (`ENEMY_ACTION_HANDLERS`), phase changes and enemy placement split into smaller functions.
- `lateorder` counts the Commands an HQ already spent from the game state instead of parsing protocol text; no more
  monkeypatching of the save function.
- One `COMMANDS` table drives dispatch, English aliases and the new `help` command; a missing file is a
  VIOLATION line instead of a traceback.
- `messages.py` holds the output vocabulary (ALLOWED, VIOLATION, Board, Note, CHECKSTAMP) and the rule citation
  format; `Violation(msg, rule=...)`.
- `tests/`: unit tests on a synthetic board (geometry, LOS, VOF, Commands, CLI), no game data needed.

Internal change numbers (L..) refer to the gap list kept during play. Rule references are Series Rules 3rd Edition
(page numbers) and the Normandy Campaign Book (CSR/MSR).

## 2026-10-12 (second release)
Engine updates found during Normandy Mission 3 and 4 play:
- Enemy leaders with Rifle Grenades act as G! units along their card's PDF (8.9); offensive table rows fixed
  (Assault 1/4 No Action, 2-3/4 Grenade Attack, 4/4 Advance; Overrun Auto). L67, L86, L89
- Upper Story / Church Tower count as +1 elevation for LOS and spotting (5.2.2); Multi-Story symbol recorded with
  `multistory <card>`; Rifle Grenades and rocket launchers (Bazooka, Panzerschreck, RCL) cannot fire from
  building/bunker/cave/pillbox cover (7.4, 7.6). L73, L79, L84, L85, L97
- Smoke/Incoming/Air Strike on an intervening card moves the VOF back along the PDF to the blocking card instead of
  ceasing fire (6.1.2 p.44); fire ceases only when LOS or range is really lost, with the real reason. L94-L96
- Counter attack (Normandy M4 MSR 4): PC A placement, two face-up PC markers (8.2.3), enemy tactic switch. L74, L88
- Engineers clear mine paths (CSR 10) and draw 1 card for mine checks; mines package redraw. L82
- Spotter counters per firing agency (Arty/Mortar), one concentration marker per type (7.16.5); AT guns with a Small
  Arms VOF use no ammo (CSR 7); FJ squad breakdown keeps the MG ammo with the A fire team (Normandy p.48). L87, L91, L93
- Setup rules for missions with a setup row and one extra card (M4), 16-step stacking at setup, setup hints
  (assets in the pool, signals without an order, CCP). L75-L77
- New commands: `lateorder` (order for an HQ whose impulse already ended, cost from its saved Commands),
  `correct casualty|status|grenade|ammo|target` (fix a wrong booking with a reason), `drop <unit> <asset>`,
  `radio check <HQ>` (every unit the HQ can reach), command track display above 10. L78, L80, L83, L92, L98, L99
- Unknown options are rejected instead of silently ignored (`--agency` and friends are accepted as aliases). L72
- Grenade markers expire on movement/fall back (7.10.4); removed counters report their markers; grenade-back rule
  messages (7.10.5). L69, L70, L92
- Dead code removed, f-string and unused-variable cleanups (pyflakes clean). L81

## 2026-10-09 (first release)
Engine as used for Field Manual 1 and Normandy Missions 1 to 3, with English output and English command aliases.
