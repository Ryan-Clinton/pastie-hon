**What this changes, and why**


**How you know it works**

- [ ] `pytest` passes
- [ ] `ruff check .` and `mypy` are clean
- [ ] If it touches behaviour, there is a test that fails without the change

**The rules this has to keep** (delete what doesn't apply)

- [ ] Haier's field names stay inside `pastie.connector` — `machMode` in the
      interface code is a rejected pull request
- [ ] Nothing bypasses or weakens a safety interlock the appliance exposes
- [ ] A command is not reported as done until the machine says so
- [ ] Nothing guesses what a number means on hardware nobody here owns
- [ ] An unverified appliance type still gets no interpreted state, no fault
      alerts and no commands
- [ ] No new unauthenticated network listener
- [ ] No password, key or token can reach a log
- [ ] Any recorded test data was stripped with the allow-list in
      `connector/scrub.py`, not by removing fields one at a time
