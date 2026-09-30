# Code signing policy

**Status: application submitted to the [SignPath Foundation](https://signpath.org/)
on 30 September 2026.** Until it's reviewed, Pastie's Windows downloads stay
unsigned, and Windows SmartScreen warns about them. This page is written to the
Foundation's requirements. Once the project is
accepted, this line will read: *Free code signing provided by
[SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org).*

## What gets signed

Only what `.github/workflows/release.yml` builds from this repository's source,
on GitHub's own runners, from a `v*` tag:

- `Pastie.exe` and `pastie-cli.exe` in the PyInstaller folder
- `PastieSetup-<version>.exe`, the Inno Setup installer that wraps them

Nothing built on a developer's machine is ever signed. Every GitHub Action the
workflow uses is pinned to a full commit, not a movable tag, and Dependabot
proposes updates as reviewable pull requests. Each binary carries the
product name *Pastie* and the version from `pastie.__version__`, set by
`packaging/pastie.spec` and `packaging/pastie.iss`. The release workflow refuses
to build a tag that doesn't match that version.

Pastie ships third-party open-source components (listed with their licences in
`THIRD_PARTY_NOTICES.txt`, which is generated from the pinned dependencies and
checked by CI). Their own binaries are shipped as their authors built them and
are not re-signed as Pastie's.

## Team roles

| Role | Who | What they may do |
|---|---|---|
| Committer and reviewer | [@Ryan-Clinton](https://github.com/Ryan-Clinton) | Push to this repository; review and merge pull requests |
| Approver | [@Ryan-Clinton](https://github.com/Ryan-Clinton) | Approve each release for signing, by hand, every time |

Pull requests from anyone else are reviewed before merging. CI (tests, lint,
type checks, the licence-notices check) must pass first. Every release is
approved for signing manually. Nothing is signed automatically.

## Privacy

This program will not transfer any information to other networked systems
unless specifically requested by the user or the person installing or operating
it.

Specifically, what Pastie talks to, and when:

- **Haier's hOn service**, with the account you sign in with, to read your
  appliances and send the commands you ask for. That's the program's purpose,
  and it happens only once you've entered an hOn account.
- **Only if you turn them on in Settings:**
  - a **Philips Hue bridge** on your own network
  - a **Google Home, Nest or Chromecast speaker** on your own network. Spoken
    announcements are rendered by Google's text-to-speech service (the gTTS
    library), which receives the sentence being spoken.
  - the **webhook URL** you enter
- **Your web browser**, only when you click a link in the window (the project's
  GitHub page, or Microsoft's WebView2 download if it's missing).

Pastie has no telemetry, no analytics and no update check. Your hOn password is
encrypted with Windows DPAPI and never leaves your PC except to sign in to hOn.

## Reporting a problem

Security issues: see [SECURITY.md](../SECURITY.md). Please use private reporting,
not a public issue.
