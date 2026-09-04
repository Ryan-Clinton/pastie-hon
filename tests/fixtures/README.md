# Recorded sequences

Each file is a list of readings, in the shape `pastie.connector.RawReading`
records them: the raw field names Haier uses, already reduced to the allow-list
in `pastie.connector.scrub`.

## Where these came from

The field names, the values they take, and the order they move in were all
observed on a **Haier HD90-A2959R-UK tumble dryer**:

- the `machMode` sequence `1 -> 2 -> 7`, and `remainingTimeMM` showing the
  programme's nominal length while idle and counting down while running, are
  from the prototype's own notifier log over real cycles;
- the `statistics` block - `programsCounter`, `filterCleaning`, `drumCleaning`
  and their `tot`/`count` shape - is from a real appliance dump;
- `dryLevel`, `tempLevel` and the programme identifiers are the values the
  machine reports for the programmes on its own dial.

Timestamps are made up, because timing is what the tests vary.

## Adding one

**Strip by keeping only fields known to be safe.** Do not remove the bad ones
one at a time. Haier's responses carry the appliance's registered **GPS
coordinates**, its MAC address, its serial number and an account identifier, and
Haier can add new fields whenever they like - a fixture built by removal is one
upstream change away from publishing somebody's address.

`pastie.connector.scrub` is that allow-list, and it is what the connector runs
every reading through before anything else sees it. If a field you need is
missing from a fixture, add it to `SAFE_PARAMETERS` first, having looked at what
it actually contains.

The same applies to anything attached to a bug report.
