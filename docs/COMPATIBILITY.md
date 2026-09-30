# Will my appliance work?

Pastie calls an appliance **supported** only when somebody has watched that
machine do what the mapping says. It doesn't count an appliance as supported
because the hOn API returns fields for it.

## The levels

| Level | Meaning | What you get |
|---|---|---|
| 🔎 **Detected** | On your hOn account, so Pastie sees it | Its name and model, and its raw values labelled as raw. No state, no alerts, no commands |
| 🧪 **Testing** | A profile is written from community sources, waiting on real cycles | The same as Detected, plus phase names marked "(unconfirmed)" |
| ✅ **Verified** | Confirmed on hardware by this project | State, time remaining, alerts, and the commands listed |
| 🤝 **Community verified** | Confirmed on hardware by an owner who reported it in an issue | The same as Verified, with credit to them |

Anything in the Haier, Candy or Hoover ranges that works with the hOn app is at
least **Detected**.

## The list

| Brand | Appliance | Model | Level | Alerts | Remote start |
|---|---|---|---|---|---|
| Haier | Tumble dryer | HD90-A2959R-UK | ✅ Verified | Finished (also while Pastie was off), fault, full water tank, filter and drum cleaning | ✅ Once armed at the machine's dial. It disarms after every cycle |
| Haier | Washing machine | HW100-BP14357 (X5) | 🧪 Testing | None yet | None yet |
| Haier | Other tumble dryers | HD80, HD90 and HD100 variants | 🔎 Detected: likely close to the HD90, [not yet checked](https://github.com/Ryan-Clinton/pastie-hon/issues/2) | None | None |
| Haier | Other washing machines | any | 🔎 Detected: [help wanted](https://github.com/Ryan-Clinton/pastie-hon/issues/1) | None | None |
| Candy, Hoover | Any hOn appliance | any | 🔎 Detected: [help wanted](https://github.com/Ryan-Clinton/pastie-hon/issues/3) | None | None |
| Haier, Candy, Hoover | Dishwashers, ovens, hobs, fridges, air conditioners and the rest | any | 🔎 Detected | None | None |

## Why "Detected" gets so little

The same number means different things on different machines. On the verified
dryer, machine mode 6 is a fault. On an oven nobody here has watched, it could be
anything. Announcing a fault on somebody's oven because of what 6 means on a
dryer would be worse than saying nothing. So an appliance nobody has verified
gets its raw numbers, labelled as raw, and nothing interpreted from them.
([More on this](safely-reverse-engineering-hon.md).)

## Moving an appliance up the list

**Own one? That's all it takes.** No programming is needed:

1. Install Pastie with the appliance on your hOn account.
2. Run one normal cycle.
3. Open an
   [appliance report](https://github.com/Ryan-Clinton/pastie-hon/issues/new?template=appliance.md)
   and quote the log lines Pastie wrote as the values changed, with what you
   were doing at the time. `pastie where` (or `pastie-cli where` in the
   download's folder) shows where the log is.

Just want to say what you own before testing anything? Post it in
[Discussions](https://github.com/Ryan-Clinton/pastie-hon/discussions).

Please quote individual fields. Never paste a raw dump: it contains the
appliance's GPS coordinates, MAC address and serial number.
