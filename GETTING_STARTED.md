# Getting started (no programming needed)

This page is for players who have never used GitHub, Python or an AI with file access. You do not write code.
You download a folder, give an AI assistant access to it, and from then on you only talk to the AI about the game.
Plan about one hour for the setup. The first mission then plays like a normal solo game, only with a referee.

## What you need

- Your own copy of Fields of Fire Deluxe with the PDFs (Series Rules, the Field Manuals and the Mission Book of the
  campaign you want to play). The kit contains no rule texts and no card data; everything comes from your files.
- An AI assistant that can work with a folder on your computer and run commands in it. Known to work: Claude in the
  Claude desktop app (Cowork mode with a connected folder) and Claude Code. Other agents work as long as they can run
  `python3` in your folder and read files there.
- Python 3.9 or newer on your computer. Windows: install it from python.org and tick "Add python to PATH".
  macOS and most Linux systems already have it. You never start Python yourself, the AI does.

## Step 1: download the kit

1. On the GitHub page of this repository click the green **Code** button, then **Download ZIP**.
2. Unpack the ZIP. You get a folder `fof-ai-referee-main`. Rename it if you like, for example `Fields of Fire AI`.
3. Put your game PDFs into a subfolder, for example `Fields of Fire AI/pdf/`. The AI builds the rule index from them
   (step 3); the PDFs themselves stay on your computer and are listed in `.gitignore`, so they never end up on GitHub
   if you ever publish your folder.

Your folder now looks like this:

```
Fields of Fire AI/
  AI_BRIEFING.md          <- the working contract for the AI
  README.md, GETTING_STARTED.md, GLOSSARY.md, CHANGELOG.md
  tool/fof.py, tool/fof/  <- the referee engine (the AI runs it, you do not)
  templates/              <- skeletons for a mission setup and your action card archive
  data/                   <- empty; the AI fills it with the rule index built from your PDFs
  pdf/                    <- your own PDFs (you add this folder)
```

## Step 2: give the AI access to the folder

- **Claude desktop app (Cowork):** start a new task, choose "Link to this computer" and connect the folder
  `Fields of Fire AI`. Claude can then read the files and run the tool inside that folder.
- **Claude Code:** open a terminal in the folder `Fields of Fire AI` and start `claude` there.
- **Other agents:** open the folder as the working directory of the agent.

The AI only needs this one folder. It does not need internet access for the game.

## Step 3: the first prompt

Paste this as your first message (adjust the campaign and mission to what you want to play):

```
Read AI_BRIEFING.md and README.md in this folder completely and follow them for the whole session.
You are the rules referee for my solo game of Fields of Fire Deluxe. I play on the physical table, I draw
all cards and tell you the results; you check every step with the tool tool/fof.py and never announce
anything from memory.

Setup, in this order, one step at a time, and wait for my answer after each step:
1. Build the rule index from my PDFs in the folder pdf/ with tool/build_rules_index.py and show me that
   "python3 tool/fof.py rule 4.2.2" works.
2. Create the mission setup for <campaign>, Mission <number> from templates/mission_template.json. Ask me
   for every value you cannot read from the PDFs (counter values, terrain card values, package tables,
   fire support). Keep the German JSON keys as they are, see GLOSSARY.md.
3. Create the game with "python3 tool/fof.py new <setup file> game1" and tell me what the tool says is
   still missing before turn 1.
Then we play: I describe my move, you check it, answer ALLOWED or VIOLATION with the rule, and tell me
the board changes in bold. One rule step per message. End every answer with the tool's CHECKSTAMP line.
```

That is the whole setup. From here the AI leads: it asks for the values it needs (you read them off your counters,
cards and the Mission Book), builds the mission file, and starts turn 1.

## Step 4: playing

- Describe moves the way you would say them at the table: "Move 2/2 to 44 under cover", "Spot 35 with the CO HQ",
  "Call for fire 105mm on 42".
- Answer card draws with `E` (the symbol or word was drawn) or `M` (not drawn), numbers as the bare number you read
  ("4"), random number draws with the value in the column the AI names ("R10: 7").
- Tell the AI when you move a marker yourself or when the table and the AI disagree. The physical board is the
  master; the AI corrects its data, never the other way round.
- `status` (just type it) makes the AI print the full board briefing. Useful after a break.

## Step 5: a new session or a new day

The game state lives in `game1/spielstand.json` in your folder, so you can stop at any time. In a new session paste:

```
Read AI_BRIEFING.md, then run "python3 tool/fof.py status" in this folder and continue the game from there.
Tool first, one rule step per message, CHECKSTAMP at the end of every answer.
```

## Common questions

- **Do I need to understand the tool?** No. If you are curious: `python3 tool/fof.py help` lists the commands.
- **Can I play in another language?** Yes. The tool's output is English, the AI can talk to you in any language.
- **The AI books something wrong.** Tell it. The briefing instructs it to fix the tool or its data, not to argue with
  the board. Every booked step is in `game1/spielstand.json` under `protokoll`, so nothing is lost.
- **Something does not work.** Open an issue on GitHub with the AI's last answers and, if possible, your
  `spielstand.json`. Do not attach your PDFs or rule texts.
