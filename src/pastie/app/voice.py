"""Every line Pastie ships with. Authored, never generated.

The rules these obey live in docs/SPEC.md section 17 and docs/UI-SPEC.md
section 7, and tests/test_voice.py enforces the mechanical ones: pool sizes,
length, no line in two pools, and no borrowed catchphrases.

Three things to know before adding a line:

* **Pastie is the only narrator.** Appliances and people appear as reported
  speech or reported positions ("{Name} currently believes..."), never as
  voices of their own.
* **Nothing here is a fact.** Facts are phrased by the presenter and are plain
  at every personality level. A line may be deleted without the screen losing
  anything.
* **Nothing here is shown for a fault, a full tank, a login problem or anything
  else somebody has to act on.** Those are plain. There is deliberately no pool
  for them.

`{name}` and `{Name}` are the appliance's name as the owner has configured it
("the dryer", "Big Dave"), lower and sentence case. `{household}` and
`{household_s}` are what Pastie calls the humans ("the Household", "the
Household's"), also configurable (UI-SPEC 7.9).
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------- narration
#
# Departmental only: what the pastie is going through when nothing notable has
# happened. Keyed by stage. Minimum sizes are in UI-SPEC 7.4.

NARRATION: dict[str, tuple[str, ...]] = {
    "idle": (
        "Pastie has nothing to report. This is generally considered a successful outcome.",
        "{Name} is at rest. Pastie has checked twice, for thoroughness, and once more for luck.",
        "All machinery is accounted for. None of it is doing anything, which is how Pastie prefers it.",
        "No proceedings are open. Pastie is using the time to tidy the filing.",
        "{Name} has not been asked to do anything, and has agreed not to.",
        "The household is quiet. Pastie has noted the quiet, in case it is needed later.",
        "Nothing is running. Pastie regards this as the machinery's finest hour.",
        "Pastie has reviewed the caseload and found it empty. It has signed the review anyway.",
        "{Name} is idle. Pastie has resisted the urge to ask whether it is sure.",
        "There is no laundry in progress. There may be laundry elsewhere. That is outside Pastie's remit.",
        "A calm day in the Division. Pastie has written 'calm' in the log and underlined it.",
        "{Name} is off duty. Pastie remains on duty, which is the arrangement.",
    ),
    "armed": (
        "{Name} has made itself available. Pastie awaits {household_s} instructions.",
        "Remote mode is on. {Name} is ready to take instructions, having first insisted on a visit.",
        "{Name} is standing by. Pastie has its pen ready, in case anything happens.",
        "Everything is in order for a start. Pastie merely needs to be told which one.",
        "{Name} has been dialled to Remote and is now, in principle, co-operative.",
        "The paperwork for a start is prepared. Only the programme is left blank.",
        "{Name} is armed and attentive. Pastie is attentive too, but was already.",
        "A start can be arranged at {household_s} convenience. Pastie has cleared its afternoon.",
        "{Name} awaits a programme. It has not expressed a preference, which Pastie respects.",
        "Remote control is available, following the customary personal visit to {name}.",
        "Pastie and {name} are both ready. This is the most they have agreed on all week.",
        "Instructions may now be given from the comfort of elsewhere. Pastie will pass them on.",
    ),
    "running_early": (
        "{Name} has begun. It is currently establishing how wet everything is, at some length.",
        "The cycle is under way. {Name} is still forming an opinion about how long it will take.",
        "{Name} is warming up. Pastie has opened a file and written today's date at the top.",
        "Proceedings have commenced. Pastie will report developments as {name} discloses them.",
        "{Name} is turning the laundry over and over, which is also how Pastie approaches problems.",
        "The drum is in motion. Pastie is watching with the concentration of a junior clerk.",
        "{Name} is sensing the load. Its findings will be shared when it feels ready.",
        "Early days. {Name} has not yet committed to a finishing time, and Pastie has not pressed it.",
        "The cycle is young. Pastie has found that this is when {name} is at its most changeable.",
        "{Name} has started working. Pastie has started taking notes. Both are going well.",
        "Warm air is being applied to the laundry with great seriousness and no apparent hurry.",
        "The operation is under way. Pastie has told nobody, because nobody needed telling.",
    ),
    "running_middle": (
        "{Name} is halfway through its duties and shows no sign of wanting to discuss them.",
        "Somewhere in the drum a sock is quietly preparing to leave. Pastie will not be told which one.",
        "The laundry is now roughly as dry as a committee meeting, and a good deal warmer.",
        "The cycle continues. Pastie has begun to wonder whether everything is round, or merely this.",
        "{Name} is making steady progress. Pastie has recorded the progress, steadily.",
        "Midway. {Name} is concentrating, and Pastie has asked the rest of the house to keep it down.",
        "The middle of a cycle is the least dramatic part. Pastie has nothing to add, and adds nothing.",
        "{Name} is doing exactly what it said it would, for once. Pastie has made a note of the occasion.",
        "Progress is being made in a circular fashion, which Pastie understands is the method.",
        "Lint is forming, as lint does. Pastie considers it a kind of weather.",
        "{Name} has reached the part of the cycle it does best, which is continuing.",
        "Half done. Pastie has resisted the temptation to round up.",
    ),
    "running_late": (
        "Nearly there. {Name} has entered the part of the cycle where hope and lint look much the same.",
        "The end is in sight. Pastie has begun drafting the completion notice, in pencil.",
        "{Name} is winding down. Pastie is winding up the paperwork.",
        "The heat is easing off. The laundry is cooling down, and so is {name}'s sense of urgency.",
        "Final stages. Pastie has placed the completion stamp within reach, but not yet in hand.",
        "{Name} is finishing up. Pastie has alerted nobody, as nothing has yet happened.",
        "Almost done. The socks, if they are going, will go now.",
        "{Name} is in its closing remarks. They are long, warm and mostly rotation.",
        "The cycle is concluding. Pastie is ready to inform {household} the moment it is true.",
        "Very nearly finished. Pastie would say 'finished', but it is not yet in a position to know.",
        "{Name} has slowed to a thoughtful tumble. Pastie is giving it the time it needs.",
        "The last few minutes. Pastie is watching the counter the way others watch a kettle.",
    ),
    "estimating": (
        "{Name} is running, and has not yet decided how long for. Pastie is giving it room.",
        "No reliable estimate yet. {Name} is still measuring, and Pastie is still waiting.",
        "The finishing time is under review by {name}. Pastie has not been consulted.",
        "{Name} is thinking about it. Pastie has been told this can take a while.",
        "An estimate is expected shortly. Pastie has cleared a space in the log for it.",
        "{Name} is gathering evidence about the load. Pastie approves of evidence in general.",
    ),
    "paused": (
        "Everything has stopped. The laundry hangs in the drum like a thought nobody has finished.",
        "{Name} is paused. Pastie has paused too, out of solidarity.",
        "Proceedings are suspended. Pastie has marked the page and is waiting to resume.",
        "{Name} is holding still. It will continue when asked, and not before.",
        "A pause. Pastie has used it to straighten the file, which did not need straightening.",
        "The cycle is on hold. Pastie is holding with it, patiently and in good order.",
    ),
    "scheduled": (
        "A cycle has been booked. Pastie is waiting for it the way one waits for a bus that was promised in writing.",
        "{Name} has an appointment. Pastie has written it in the diary and underlined the time.",
        "A delayed start is arranged. {Name} will begin when the hour arrives, and not a minute earlier.",
        "Proceedings are scheduled. Pastie has set an internal reminder, which it will not need.",
        "{Name} is waiting for its start time. It is very good at waiting.",
        "A start is pencilled in. Pastie will ink it once {name} actually begins.",
    ),
    "finished": (
        "It's over. {Name} has done its part, and the laundry has emerged, changed in ways it won't discuss.",
        "{Name} has finished. The rest of the arrangement concerns a basket.",
        "The last tumble has been tumbled. Pastie has recorded it with appropriate ceremony.",
        "{Name} has finished and gone quiet, which in its line of work counts as satisfaction.",
        "Done. Pastie has closed the file and filed the closed file.",
        "The cycle is complete. Laundry-related responsibilities have returned to their usual owner.",
        "Finished. The laundry is dry, noticeably warmer, and would like to be folded.",
        "{Name} reports completion, and Pastie has checked the evidence. It holds up.",
        "All done. Pastie has nothing further to add, and is adding nothing further.",
        "{Name} has concluded its business. The drum is still. The socks are counted, or were.",
        "The job is done. Pastie has permitted itself a small, dignified moment of approval.",
        "Complete. {Name} would like it noted that it finished roughly when it eventually said it would.",
    ),
}

# ----------------------------------------------------------- reactive asides
#
# Dry and Departmental: one line, only because something genuinely happened.
# Keyed by aside key (UI-SPEC 7.8). Three variants minimum. Some take extra
# placeholders, supplied by the presenter from real values.

ASIDES: dict[str, tuple[str, ...]] = {
    "estimate_unsettled": (
        "{Name} currently believes {minutes} minutes remain. Pastie has elected not to contradict it.",
        "{Name} estimates {minutes} minutes. Pastie is recording this as an estimate.",
        "According to {name}, {minutes} minutes. Pastie will believe it once the figure stops moving.",
    ),
    "estimate_rose": (
        "It said {before} min earlier. It now says {after}. Pastie has elected not to contradict it.",
        "The estimate has gone from {before} to {after} minutes. {Name} is reconsidering, in public.",
        "The estimate went from {before} to {after}. Pastie has noted the revision, and its direction.",
    ),
    "start_confirmed": (
        "Three separate parties have now agreed that {name} is on.",
        "Haier said yes, and then {name} said yes. Pastie is satisfied on both counts.",
        "Confirmation received from the machine itself, which is the only kind Pastie counts.",
    ),
    "remote_not_armed": (
        "The remote-control procedure currently contains a mandatory visit to {name}.",
        "{Name} accepts remote instructions only from people who have first come to see it in person.",
        "Remote control is available after a short walk. Pastie did not design this.",
    ),
    "gap_recovered": (
        "Pastie wasn't present, but {name} kept minutes.",
        "Pastie was away. {Name}'s counter was not. The counter has been believed.",
        "Reconstructed from the evidence. {Name}'s records were complete, and Pastie is grateful.",
    ),
    "unknown_state": (
        "Inventing an answer would be quicker. It would also be an answer Pastie made up.",
        "Pastie could guess. Pastie has a policy about guessing, and this is it.",
        "The value is noted exactly as received. What it means has not yet been established.",
    ),
    "maintenance_due": (
        "{Name} has begun keeping records. This seems only fair, given what Pastie does for a living.",
        "{Name} is asking for its filter to be seen to. It asks politely, by counting.",
        "Maintenance is recommended by {name}, who has kept an exact tally.",
    ),
    "finished_aside": (
        "Its part of the arrangement is complete.",
        "The machine is finished. The clothes have been transferred to your department.",
        "{Name} has concluded its business and would like the laundry collected at your convenience.",
    ),
    "dryer_offline": (
        "{Name} has not reported for a while. Pastie is keeping the chair warm.",
        "Nothing has been heard from {name} since the last reading. Pastie is listening.",
        "{Name} has gone quiet. Pastie has noted the silence without drawing conclusions.",
    ),
    "reconnect_quiet": (
        "Nothing happened. This has simplified the paperwork considerably.",
        "Nothing happened in Pastie's absence. The file for it is very thin.",
        "Everything is exactly as Pastie left it. Pastie is quietly pleased.",
    ),
    "where_dryer_silent": (
        "The internet is present. Haier is present. {Name}, presently, is not.",
        "Everybody is present except {name}. Pastie has marked it absent, not missing.",
        "The line to Haier is open. {Name} has not picked up.",
    ),
    "messenger_ok": (
        "It reports no objections.",
        "The message was delivered and, as far as Pastie can tell, understood.",
        "Delivered. The messenger has returned to its desk.",
    ),
}

# Clicking the pastie three times (Departmental, UI-SPEC 7.7). Twelve minimum.
POKED: tuple[str, ...] = (
    "Pastie is working. It will be free shortly, and by shortly it means eventually.",
    "Pastie acknowledges the contact and has logged it under 'miscellaneous'.",
    "Yes? Pastie is listening. Pastie is always listening, in the most reassuring sense.",
    "Pastie would like to point out that it is battered, not fragile.",
    "Pastie has been poked. It has chosen to regard this as a vote of confidence.",
    "This is not a button. Pastie is flattered that you thought it might be.",
    "Pastie is on duty. Social calls are welcome, briefly.",
    "Pastie has checked, and nothing needs doing. You are free to go.",
    "Pastie is still here. It is always still here. That is rather the point of it.",
    "Pastie appreciates the attention and will note it in the minutes.",
    "The Division is open. Pastie is the Division. Please take a number.",
    "Pastie is fine, thank you for asking, if that is what this was.",
)

# ------------------------------------------------------- temperaments
#
# UI-SPEC 7.9: an appliance's temperament chooses which shipped lines it draws
# on. The narration above was written from the dryer's observed behaviour,
# which is Indecisive; every other temperament adds its own lines to it, by
# stage group. Custom draws only on the owner's own lines.

TEMPERAMENTS = ("Diligent", "Indecisive", "Dramatic", "Aloof", "Weary", "Cheerful", "Custom")

TEMPERAMENT_LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "Diligent": {
        "running": (
            "{Name} is working steadily and to schedule. Pastie has nothing to correct, and finds this unsettling.",
            "{Name} is doing precisely what was asked, in the order it was asked. Pastie approves.",
            "Diligence is being shown by {name}. Pastie has recorded it in the good column.",
            "{Name} has not deviated from the plan once. Pastie is keeping an eye on it anyway, out of habit.",
        ),
        "finished": (
            "{Name} has finished exactly as undertaken. Pastie has filed the result under 'as expected'.",
            "Completed, on time and without fuss. {Name} would like no fuss made about it, and Pastie obliges.",
            "{Name} reports the task complete, and has already tidied up after itself.",
            "The work is done. {Name} has asked for no recognition. Pastie is recording some anyway.",
        ),
        "idle": (
            "{Name} is idle, but ready, in the manner of something that has read the manual.",
            "{Name} is resting between duties. It would describe this as maintenance.",
            "No work is scheduled. {Name} has used the time to be prepared.",
            "{Name} awaits instructions with its usual quiet competence.",
        ),
    },
    "Dramatic": {
        "running": (
            "{Name} has thrown itself into the cycle as if the fate of the house depended on it.",
            "{Name} is tumbling with enormous feeling. Pastie is reporting only the facts.",
            "Every rotation is an event, according to {name}. Pastie has counted them as rotations.",
            "{Name} has declared this cycle the most important of its career. It said so about the last one.",
        ),
        "finished": (
            "{Name} has finished, and would like a moment to recover before anyone opens the door.",
            "It is over. {Name} describes the experience as transformative. Pastie describes it as dry.",
            "{Name} has taken a bow. Pastie has noted the bow, and the laundry, which is ready.",
            "Completion has been achieved, as {name} would have it, against all odds. There were no odds.",
        ),
        "idle": (
            "{Name} is idle, and would like everyone to know how much it misses the work.",
            "{Name} rests, in a pose that suggests it has been wronged.",
            "Nothing is happening. {Name} regards this as a tragedy in several acts.",
            "{Name} has been left alone with its thoughts, and has a great many of them.",
        ),
    },
    "Aloof": {
        "running": (
            "{Name} is running and has not seen fit to discuss it with Pastie.",
            "{Name} is getting on with things and prefers not to be watched. Pastie watches discreetly.",
            "Progress is being made. {Name} regards the details as its own business.",
            "{Name} has acknowledged Pastie with the barest of status updates. Pastie is used to it.",
        ),
        "finished": (
            "{Name} has finished and would rather not make a thing of it.",
            "Done. {Name} has withdrawn to a dignified silence.",
            "{Name} reports completion in the fewest possible words, which is to say one.",
            "The cycle is complete. {Name} does not require thanks, or indeed conversation.",
        ),
        "idle": (
            "{Name} is idle and has made itself unavailable for comment.",
            "{Name} is keeping to itself. Pastie respects its privacy, and its schedule.",
            "Nothing to report. {Name} would like that to remain the case.",
            "{Name} rests, aloof, above the concerns of the laundry basket.",
        ),
    },
    "Weary": {
        "running": (
            "{Name} is working, again. It has asked Pastie to note that it has done this before.",
            "{Name} is tumbling with the air of something that has seen a great many socks.",
            "Another cycle. {Name} is getting through it the way it gets through all of them.",
            "{Name} is carrying on. Pastie admires the carrying on, if not the sighing.",
        ),
        "finished": (
            "{Name} has finished, and would like to sit down, figuratively.",
            "Done, at last. {Name} does not expect this to be the end of it.",
            "{Name} has completed another cycle and added it to a very long list.",
            "Finished. {Name} is already bracing itself for the next basket.",
        ),
        "idle": (
            "{Name} is resting. It has earned it, and would like that acknowledged.",
            "{Name} is idle, for now. It knows better than to call it a holiday.",
            "Nothing is running. {Name} is enjoying it while it lasts.",
            "{Name} is having a quiet moment. It has had very few of them.",
        ),
    },
    "Cheerful": {
        "running": (
            "{Name} is tumbling away with great enthusiasm. Pastie reports the enthusiasm at face value.",
            "{Name} is having a lovely time. Pastie has checked, and it is also drying.",
            "{Name} is delighted to be working. Pastie is delighted that somebody is.",
            "Round and round goes {name}, cheerfully. Pastie counts the cheer as a secondary output.",
        ),
        "finished": (
            "{Name} has finished and is very pleased with how it went.",
            "All done. {Name} would like to thank everyone involved, which is mostly the laundry.",
            "{Name} reports completion with evident satisfaction. It will happily do it again.",
            "Finished, and {name} is beaming, in so far as a drum can beam.",
        ),
        "idle": (
            "{Name} is idle and in excellent spirits about it.",
            "{Name} is resting, and looking forward to the next load with unusual optimism.",
            "Nothing is happening, and {name} is making the best of it.",
            "{Name} is ready whenever {household} is, and very much hopes it is soon.",
        ),
    },
}

# ------------------------------------------------------------- stances
#
# How Pastie reports and negotiates with a cast member (UI-SPEC 7.9), drawn on
# in Departmental narration alongside the stage lines.

STANCES = ("Professional", "Deferential", "Firm", "Weary", "Fond")

STANCE_LINES: dict[str, tuple[str, ...]] = {
    "Professional": (
        "Pastie has recorded {name}'s position and will report any change.",
        "Pastie and {name} maintain a correct working relationship, and a tidy file.",
        "{Name}'s status has been noted, cross-referenced and filed.",
        "Pastie is monitoring {name} to the usual standard.",
    ),
    "Deferential": (
        "Pastie would not dream of hurrying {name}.",
        "Pastie defers entirely to {name}'s judgement on the matter of time.",
        "{Name} knows best. Pastie merely takes the minutes.",
        "Pastie is at {name}'s disposal, as ever, and at a respectful distance.",
    ),
    "Firm": (
        "Pastie has reminded {name} of its obligations, politely but clearly.",
        "Pastie is holding {name} to its estimate. Firmly.",
        "{Name} has been told that Pastie is watching. It is.",
        "Pastie expects {name} to finish as undertaken, and has written that down.",
    ),
    "Weary": (
        "Pastie has seen {name} do this before. Pastie will see it again.",
        "Pastie is monitoring {name} with the patience of long acquaintance.",
        "{Name} is behaving exactly as Pastie feared it would, which is to say normally.",
        "Pastie has stopped being surprised by {name}, and finds this restful.",
    ),
    "Fond": (
        "Pastie is, if it is honest, rather proud of {name}.",
        "Pastie is keeping a fond eye on {name}, and a fonder file.",
        "{Name} is doing its best, and Pastie thinks that is quite enough.",
        "Pastie would like it recorded that {name} is a credit to the household.",
    ),
}

# ------------------------------------------------------------ fixed phrases

#: Under an idle appliance (UI-SPEC 6.9), by level. Plain has nothing.
IDLE_LINE = {
    "dry": "No active proceedings.",
    "departmental": "No domestic machinery currently requires intervention.",
}

#: The caseload heading (Departmental only).
CASELOAD_HEADING = "CURRENT CASELOAD"

#: Connecting, by observable stage (UI-SPEC 6.8). Plain uses CONNECTING_PLAIN.
CONNECTING = {
    "service": "Contacting the background watcher…",
    "haier": "Contacting Haier…",
    "appliances": "Requesting appliance records…",
    "reading": "Comparing their account with ours…",
    "ready": "Everything appears to be in order.",
}
CONNECTING_PLAIN = "Connecting…"
RECONNECTED = (
    "Connection restored. Pastie is requesting a complete account of what happened during its "
    "absence."
)
RECONNECTED_PLAIN = "Reconnected."

#: The two closing lines of a case file (Dry and Departmental).
CASE_CLOSING = (
    "No further action is required by Pastie.",
    "Laundry-related responsibilities have now returned to their usual owner.",
)

#: An extra closing line on the 50th and 100th cycle's case file.
CASE_MILESTONE = (
    "Pastie notes, for the record, that this was cycle {count}. It has kept every file."
)

HISTORY_EMPTY = {
    "plain": "Nothing yet.",
    "dry": "No proceedings on record yet.",
    "departmental": "The case file is empty. Pastie finds this suspicious, but cannot prove anything.",
}

#: The subtitle of History in Departmental mode.
HISTORY_SUBTITLE = "Case file"

#: Release notes heading in Departmental mode.
MINUTES_HEADING = "Minutes of recent proceedings"

INSTITUTION = "Practical Appliance Supervision, Telemetry & Interoperability Executive"
INSTITUTION_NOTE = "(The acronym was developed considerably later than the name.)"
DIVISION = "Domestic Appliance Liaison Division"

ORG_CHART = (
    ("Connector", "translates what Haier said"),
    ("Brain", "decides what actually happened"),
    ("Messengers", "bother something else about it"),
    ("App", "tells you what everybody is doing"),
)

#: One example per personality level, shown in Settings -> Appearance: the same
#: event in each level's voice (UI-SCREENS 7.4).
LEVEL_EXAMPLES = (
    ("plain", "Plain", "Tumble dryer finished."),
    ("dry", "Dry", "Tumble dryer finished. Its part of the arrangement is complete."),
    (
        "departmental",
        "Departmental",
        "Tumble dryer finished. The clothes have been transferred to your department.",
    ),
)

EMPTY_NO_APPLIANCE = {
    "plain": "No appliance yet.",
    "dry": "No appliance yet. Pastie is ready to administer one.",
    "departmental": "No appliance yet. Pastie is ready to administer one.",
}

ONBOARDING_ASIDES = {
    "appliances": "Pastie is introducing itself to the household machinery.",
    "messengers": "Pastie will need someone to carry messages.",
    "tested": "The chain from appliance to household is complete.",
}

# ----------------------------------------------------------------- the Guide


@dataclass(frozen=True)
class GuideEntry:
    key: str
    title: str
    #: Plain words, shown whatever the level, so Plain mode still makes sense.
    condition: str
    body: str


GUIDE: tuple[GuideEntry, ...] = (
    GuideEntry(
        "pasties",
        "On Pasties, and Why One Is in Charge",
        "Always available.",
        "A pastie is minced meat and potato, pressed into a disc, battered and deep-fried, and "
        "usually served with chips. It has no processor, no network stack and no opinions. For "
        "the liaison of people and domestic machinery this makes it the most qualified "
        "candidate ever found. It was placed in the post by a process nobody remembers agreeing "
        "to, and has regarded the work as serious administration ever since.",
    ),
    GuideEntry(
        "round",
        "On Being Round",
        "Unlocks with the first cycle Pastie watches.",
        "The drum is round. The pastie is round. It has been suggested that the universe is "
        "round as well. Pastie has never confirmed this, but has never been seen to disagree, "
        "and has noted that most of its working life takes place in circles.",
    ),
    GuideEntry(
        "estimates",
        "On Estimates, Which Change Their Minds",
        "Unlocks the first time an estimate goes up.",
        "Early in a cycle the dryer is still measuring the load, and its estimate wanders, "
        "sometimes upwards. This is not a fault. Pastie reports the figure as the dryer's "
        "belief, marks it 'still estimating', and waits until it falls inside the programme's "
        "own length, which is when the dryer begins counting down honestly.",
    ),
    GuideEntry(
        "coming_back",
        "On Coming Back",
        "Unlocks the first time Pastie reconstructs a cycle it missed.",
        "When Pastie is not running, the dryer carries on without it. On its return Pastie "
        "compares the dryer's completed-cycle counter with the one it last saw. If the counter "
        "moved, a cycle finished in its absence, and Pastie says so, with the evidence, and "
        "without pretending to know when.",
    ),
    GuideEntry(
        "water",
        "On Water, and Where It Goes",
        "Unlocks with the first full-tank alert.",
        "A heat-pump dryer does not vent. It condenses the water out of the laundry and keeps "
        "it in a tank, and when the tank is full it stops and waits for a person. Pastie tells "
        "the Household at once, in plain words, because this is the one part of the process "
        "that nobody else can do.",
    ),
    GuideEntry(
        "lint",
        "On Lint",
        "Unlocks with the first filter-clean reminder.",
        "Lint accumulates, as lint does. The dryer keeps its own count of cycles since the "
        "filter was last cleaned, and asks for attention when the count runs out. Pastie "
        "passes the request on, and regards lint as a kind of weather: not personal, and not "
        "going away.",
    ),
    GuideEntry(
        "duvets",
        "On Duvets, Which Are Not Quilts",
        "Unlocks with the first Duvet cycle.",
        "For a time, asking for Duvet from afar did nothing at all. The app's recipe pointed at "
        "a programme called quilt, which this dryer does not have, and the dryer, reasonably, "
        "ignored it. Pastie now asks for the dryer's own Duvet, which it recognises at once. "
        "The episode is remembered as a lesson in asking for things by their proper names.",
    ),
    GuideEntry(
        "faults",
        "On Faults",
        "Unlocks after the first fault has cleared.",
        "When a machine reports a fault, Pastie says so plainly and says nothing else. Faults "
        "are the one subject on which Pastie has no sense of humour, by design. Once it is "
        "over, it is permitted to observe that the machinery, too, is only doing its best.",
    ),
    GuideEntry(
        "milestones",
        "The Fiftieth and the Hundredth",
        "Unlocks when the dryer's cycle counter reaches 50, and again at 100.",
        "Some numbers deserve recognition. Not a reward, not a streak, and nothing to lose: "
        "only a note, in the file, that Pastie and the dryer have been through this many "
        "cycles together, most of them in circles.",
    ),
)

# ----------------------------------------------------------------- meters


@dataclass(frozen=True)
class MeterSpec:
    label: str
    #: rising (up fast, then level), peaking (worst mid-cycle), late (all at the end)
    curve: str


_DEFAULT_METERS = (
    MeterSpec("Crispiness", "rising"),
    MeterSpec("Existential dread", "peaking"),
    MeterSpec("Sock escape probability", "late"),
)

#: Joke meters by programme label (UI-SPEC 7.5). Departmental only.
METERS: dict[str, tuple[MeterSpec, ...]] = {
    "default": _DEFAULT_METERS,
    "Duvet": (
        MeterSpec("Loft", "rising"),
        MeterSpec("Feather anxiety", "peaking"),
        MeterSpec("Likelihood it is secretly a cloud", "late"),
    ),
    "Wool": (
        MeterSpec("Shrinkage fear", "peaking"),
        MeterSpec("Sheep-related guilt", "peaking"),
        MeterSpec("Cosiness", "rising"),
    ),
    "Towels": (
        MeterSpec("Fluffiness", "rising"),
        MeterSpec("Absorbency regained", "rising"),
        MeterSpec("Beach-readiness", "late"),
    ),
    "Delicates": (
        MeterSpec("Nervousness", "peaking"),
        MeterSpec("Frills intact", "rising"),
        MeterSpec("Tact", "late"),
    ),
    "Refresh": (
        MeterSpec("Freshness", "rising"),
        MeterSpec("Smell of adventure removed", "rising"),
        MeterSpec("Plausible deniability", "late"),
    ),
}

#: Terms borrowed from somebody else's books (SPEC 17, rule 6). Shipped copy
#: may not contain them; the owner's own lines only get a warning (UI-SPEC 7.9).
BORROWED = (
    "42",
    "forty-two",
    "towel",
    "panic",
    "improbab",
    "vogon",
    "hitchhik",
    "sirius cybernetics",
    "genuine people personalit",
    "babel fish",
    "marvin",
)
