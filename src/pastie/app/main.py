"""The window.

It does not talk to Haier. It asks the service, over the private channel, and
draws whatever comes back - which is why there is only ever one connection to
Haier's servers, and why the window and the service can never disagree about
what the appliance is doing.

Two things here are worth knowing before changing them:

* **The settings screens are generated.** Every messenger describes its settings
  and this file draws them. Adding a light or a speaker means writing one file
  in `pastie.messengers` and touching nothing here.
* **Nothing blocks the window.** Every request runs on a worker thread and comes
  back through a queue, because a Hue bridge that has gone away takes ten
  seconds to say so, and a frozen window is how that gets reported as a crash.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from tkinter import messagebox, ttk
from typing import Any

from pastie.app.client import ServiceClient, ServiceUnavailableError
from pastie.service.channel import PipeClient

log = logging.getLogger(__name__)

# The prototype's palette, kept: warm, crusty, pastie.
BG = "#13161b"
CARD = "#1d2129"
CARD_HI = "#272c36"
CRUST = "#e0a03c"
TEXT = "#eef1f6"
MUTED = "#8994a5"
GREEN = "#7fc96b"
BLUE = "#6fb4d8"
AMBER = "#e0a03c"
RED = "#e2664f"
FIELD = "#eef1f6"
INK = "#171a20"

STATE_COLOURS = {
    "running": GREEN,
    "finished": BLUE,
    "fault": RED,
    "paused": AMBER,
    "scheduled": AMBER,
    "unknown": MUTED,
}

REFRESH_MS = 3000


@dataclass
class Answer:
    """Something a worker thread finished, on its way back to the window."""

    kind: str
    payload: Any = None
    error: str = ""


class Work:
    """Runs requests off the window's thread and hands the answers back.

    A queue rather than callbacks into tkinter from another thread: tkinter is
    not thread-safe, and the failure mode when you get that wrong is a window
    that dies silently three minutes later.
    """

    def __init__(self) -> None:
        self.answers: queue.Queue[Answer] = queue.Queue()

    def run(self, kind: str, action: Callable[[], Any]) -> None:
        def worker() -> None:
            try:
                self.answers.put(Answer(kind, action()))
            except ServiceUnavailableError as error:
                self.answers.put(Answer(kind, error=str(error)))
            except Exception as error:
                log.exception("%s failed", kind)
                self.answers.put(Answer(kind, error=f"{type(error).__name__}: {error}"))

        threading.Thread(target=worker, name=f"pastie-{kind}", daemon=True).start()


class App(tk.Tk):
    def __init__(self, client: ServiceClient) -> None:
        super().__init__()
        self._client = client
        self._work = Work()
        self._appliance: str | None = None
        self._fields: dict[str, dict[str, tk.Variable]] = {}

        self.title("Pastie")
        self.configure(bg=BG)
        self.geometry("620x760")
        self.minsize(560, 640)
        self._style()

        self._header()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._appliance_tab(notebook)
        self._settings_tab(notebook)

        self.after(200, self._drain)
        self._refresh()

    # ------------------------------------------------------------ chrome

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=TEXT, padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", CARD_HI)])
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TProgressbar", background=CRUST, troughcolor=CARD_HI, borderwidth=0)
        style.configure("TCombobox", fieldbackground=FIELD, foreground=INK)

    def _card(self, parent: tk.Misc) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 12))
        return card

    def _header(self) -> None:
        bar = tk.Frame(self, bg=BG, padx=14, pady=12)
        bar.pack(fill="x")
        tk.Label(bar, text="PASTIE", bg=BG, fg=CRUST, font=("Segoe UI", 20, "bold")).pack(
            side="left"
        )
        self.health_label = tk.Label(
            bar, text="connecting...", bg=BG, fg=MUTED, font=("Segoe UI", 10)
        )
        self.health_label.pack(side="right")

    # --------------------------------------------------------- appliance

    def _appliance_tab(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=14)
        notebook.add(page, text="  Appliance  ")

        card = self._card(page)
        self.name_label = tk.Label(
            card, text="Looking...", bg=CARD, fg=TEXT, font=("Segoe UI", 15, "bold")
        )
        self.name_label.pack(anchor="w")
        self.model_label = tk.Label(card, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.model_label.pack(anchor="w")

        self.state_label = tk.Label(card, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 13, "bold"))
        self.state_label.pack(anchor="w", pady=(10, 2))
        self.detail_label = tk.Label(
            card, text="", bg=CARD, fg=TEXT, font=("Segoe UI", 10), justify="left"
        )
        self.detail_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(12, 0))

        controls = self._card(page)
        tk.Label(
            controls, text="START A CYCLE", bg=CARD, fg=CRUST, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 8))
        self.armed_label = tk.Label(
            controls,
            text="",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=520,
            justify="left",
        )
        self.armed_label.pack(anchor="w", pady=(0, 8))

        self.programme_box = self._dropdown(controls, "Programme")
        self.dryness_box = self._dropdown(controls, "Dryness")
        self.temperature_box = self._dropdown(controls, "Temperature")

        buttons = tk.Frame(controls, bg=CARD)
        buttons.pack(fill="x", pady=(10, 0))
        self.start_button = tk.Button(
            buttons,
            text="START",
            command=self._start,
            bg=CRUST,
            fg=INK,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=6,
            state="disabled",
        )
        self.start_button.pack(side="left")
        tk.Button(
            buttons,
            text="STOP",
            command=self._stop,
            bg=CARD_HI,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=6,
        ).pack(side="left", padx=(8, 0))

        self.command_label = tk.Label(
            controls, text="", bg=CARD, fg=MUTED, font=("Consolas", 9), justify="left"
        )
        self.command_label.pack(anchor="w", pady=(10, 0))

        activity = self._card(page)
        tk.Label(activity, text="RECENTLY", bg=CARD, fg=CRUST, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        self.recent_label = tk.Label(
            activity, text="Nothing yet.", bg=CARD, fg=TEXT, font=("Segoe UI", 9), justify="left"
        )
        self.recent_label.pack(anchor="w")

    def _dropdown(self, parent: tk.Misc, label: str) -> ttk.Combobox:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9), width=14, anchor="w"
        ).pack(side="left")
        box = ttk.Combobox(row, state="readonly", values=[])
        box.pack(side="left", fill="x", expand=True)
        return box

    # ---------------------------------------------------------- settings

    def _settings_tab(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=14)
        notebook.add(page, text="  Settings  ")
        self._settings_page = page

        account = self._card(page)
        tk.Label(
            account, text="HON ACCOUNT", bg=CARD, fg=CRUST, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")
        tk.Label(
            account,
            text=(
                "The service encrypts this under its own Windows account. It is never "
                "stored here, and it cannot be read back out."
            ),
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self._entry(account, "Email", self.username)
        self._entry(account, "Password", self.password, secret=True)
        tk.Button(
            account,
            text="Save account",
            command=self._save_account,
            bg=CARD_HI,
            fg=TEXT,
            relief="flat",
            padx=12,
            pady=4,
        ).pack(anchor="w", pady=(8, 0))

        self._messenger_cards = tk.Frame(page, bg=BG)
        self._messenger_cards.pack(fill="both", expand=True)

    def _entry(
        self, parent: tk.Misc, label: str, variable: tk.Variable, *, secret: bool = False
    ) -> None:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9), width=14, anchor="w"
        ).pack(side="left")
        tk.Entry(
            row,
            textvariable=variable,
            show="*" if secret else "",
            bg=FIELD,
            fg=INK,
            relief="flat",
            insertbackground=INK,
        ).pack(side="left", fill="x", expand=True, ipady=3)

    def _draw_messengers(self, messengers: list[Any], values: dict[str, Any]) -> None:
        """Build a card per messenger, from what the messenger said it needs.

        Nothing in this method knows what a Hue bridge or a Chromecast is.
        """
        for child in self._messenger_cards.winfo_children():
            child.destroy()
        self._fields.clear()

        for messenger in messengers:
            card = tk.Frame(self._messenger_cards, bg=CARD, padx=16, pady=14)
            card.pack(fill="x", pady=(0, 12))
            tk.Label(
                card,
                text=messenger.label.upper(),
                bg=CARD,
                fg=CRUST,
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 6))

            saved = dict(values.get(messenger.name, {}))
            fields: dict[str, tk.Variable] = {}
            for setting in messenger.settings:
                fields[setting["key"]] = self._draw_setting(card, setting, saved)
            self._fields[messenger.name] = fields
            name = str(messenger.name)

            buttons = tk.Frame(card, bg=CARD)
            buttons.pack(anchor="w", pady=(8, 0))
            tk.Button(
                buttons,
                text="Save",
                command=partial(self._save_messenger, name),
                bg=CARD_HI,
                fg=TEXT,
                relief="flat",
                padx=12,
                pady=4,
            ).pack(side="left")
            tk.Button(
                buttons,
                text="Test",
                command=partial(self._test_messenger, name),
                bg=CARD_HI,
                fg=TEXT,
                relief="flat",
                padx=12,
                pady=4,
            ).pack(side="left", padx=(8, 0))

    def _draw_setting(
        self, card: tk.Frame, setting: dict[str, Any], saved: dict[str, Any]
    ) -> tk.Variable:
        kind = setting.get("kind", "text")
        value = saved.get(setting["key"], setting.get("default"))

        if kind == "bool":
            variable: tk.Variable = tk.BooleanVar(value=bool(value))
            tk.Checkbutton(
                card,
                text=setting["label"],
                variable=variable,
                bg=CARD,
                fg=TEXT,
                selectcolor=CARD_HI,
                activebackground=CARD,
                activeforeground=TEXT,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=2)
            return variable

        variable = tk.StringVar(value="" if value is None else str(value))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", pady=2)
        tk.Label(
            row,
            text=setting["label"],
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            width=16,
            anchor="w",
        ).pack(side="left")

        if kind == "choice":
            box = ttk.Combobox(row, state="readonly", values=list(setting.get("choices", [])))
            box.set(variable.get())
            box.bind("<<ComboboxSelected>>", partial(_copy_choice, variable, box))
            box.pack(side="left", fill="x", expand=True)
        else:
            tk.Entry(
                row,
                textvariable=variable,
                show="*" if kind == "secret" else "",
                bg=FIELD,
                fg=INK,
                relief="flat",
                insertbackground=INK,
            ).pack(side="left", fill="x", expand=True, ipady=3)

        if setting.get("help"):
            tk.Label(
                card,
                text=setting["help"],
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=500,
                justify="left",
            ).pack(anchor="w", padx=(112, 0))
        return variable

    # ------------------------------------------------------------ actions

    def _refresh(self) -> None:
        self._work.run("status", self._client.status)
        self.after(REFRESH_MS, self._refresh)

    def _save_account(self) -> None:
        username, password = self.username.get().strip(), self.password.get()
        if not username or not password:
            messagebox.showinfo("Pastie", "An email address and a password are both needed.")
            return
        self._work.run("account", lambda: self._client.set_account(username, password))
        self.password.set("")  # not kept here, not even in a text box

    def _save_messenger(self, name: str) -> None:
        values = {key: _value(variable) for key, variable in self._fields.get(name, {}).items()}

        def save() -> str:
            self._client.save_messenger(name, values)
            return name

        self._work.run("saved", save)

    def _test_messenger(self, name: str) -> None:
        self._work.run("tested", lambda: self._client.test_messenger(name))

    def _start(self) -> None:
        if not self._appliance:
            return
        extra: dict[str, Any] = {}
        dryness = self._dry_ids.get(_chosen(self.dryness_box))
        if dryness:
            extra["dryLevel"] = dryness
        temperature = self._temp_ids.get(_chosen(self.temperature_box))
        if temperature:
            extra["tempLevel"] = temperature
        programme = self._programme_ids.get(_chosen(self.programme_box), "")
        appliance = self._appliance
        self._work.run("command", lambda: self._client.start(appliance, programme, **extra))

    def _stop(self) -> None:
        if not self._appliance:
            return
        appliance = self._appliance
        self._work.run("command", lambda: self._client.stop(appliance))

    # ------------------------------------------------------------ answers

    def _drain(self) -> None:
        try:
            while True:
                self._apply(self._work.answers.get_nowait())
        except queue.Empty:
            pass
        self.after(200, self._drain)

    def _apply(self, answer: Answer) -> None:
        if answer.error:
            if answer.kind == "status":
                self.health_label.configure(text=answer.error, fg=RED)
            else:
                messagebox.showwarning("Pastie", answer.error)
            return

        if answer.kind == "status":
            self._show_status(answer.payload)
        elif answer.kind == "account":
            messagebox.showinfo(
                "Pastie",
                "Saved. The service picks up a new password when it next restarts."
                if answer.payload
                else "Saved.",
            )
        elif answer.kind == "saved":
            self._flash(f"Saved {answer.payload}.")
        elif answer.kind == "tested":
            ok, detail = answer.payload
            messagebox.showinfo("Pastie", detail or ("That worked." if ok else "That failed."))
        elif answer.kind == "command":
            self.command_label.configure(text="\n".join(answer.payload))
            self._settings_refresh_needed = False

    def _flash(self, message: str) -> None:
        self.health_label.configure(text=message, fg=GREEN)

    def _show_status(self, status: dict[str, Any]) -> None:
        health = str(status.get("health", ""))
        self.health_label.configure(
            text=str(status.get("health_message", "")),
            fg=GREEN if health == "ok" else (AMBER if health == "slow" else RED),
        )

        appliances = status.get("appliances") or []
        if not appliances:
            self.name_label.configure(text="No appliance yet")
            return

        appliance = appliances[0]
        self._appliance = str(appliance.get("id"))
        name = str(appliance.get("name", "appliance"))
        self.name_label.configure(text=f"{name[:1].upper()}{name[1:]}")
        self.model_label.configure(text=str(appliance.get("model", "")))

        state = str(appliance.get("state", "unknown"))
        unverified = appliance.get("trust") != "verified"
        label = state.upper() + ("  (unverified - raw readings only)" if unverified else "")
        self.state_label.configure(text=label, fg=STATE_COLOURS.get(state, MUTED))

        lines = []
        if appliance.get("programme"):
            lines.append(f"Programme   {appliance['programme']}")
        lines.append(f"Remaining   {appliance.get('remaining', 'unknown')}")
        if appliance.get("fault_code"):
            lines.append(f"Fault       {appliance['fault_code']}")
        for item in appliance.get("maintenance", []):
            if item.get("due"):
                lines.append(f"Due         {item['name']}")
        self.detail_label.configure(text="\n".join(lines))

        progress = appliance.get("progress")
        self.progress_bar.configure(value=0 if progress is None else float(progress) * 100)

        self._show_controls(appliance)

        recent = status.get("recent") or []
        self.recent_label.configure(
            text="\n".join(f"{item['at'][11:16]}  {item['message']}" for item in recent[:6])
            or "Nothing yet."
        )
        if status.get("command"):
            self.command_label.configure(text="\n".join(status["command"]))

    def _show_controls(self, appliance: dict[str, Any]) -> None:
        self._programme_ids = {
            item["label"]: item["id"] for item in appliance.get("programmes", [])
        }
        self._dry_ids = {item["label"]: item["id"] for item in appliance.get("dry_levels", [])}
        self._temp_ids = {item["label"]: item["id"] for item in appliance.get("temperatures", [])}

        for box, ids in (
            (self.programme_box, self._programme_ids),
            (self.dryness_box, self._dry_ids),
            (self.temperature_box, self._temp_ids),
        ):
            names = list(ids)
            if list(box["values"]) != names:
                box["values"] = names
                if names and not _chosen(box):
                    box.set(names[0])

        can_start = "startProgram" in appliance.get("commands", [])
        armed = appliance.get("remote_allowed")
        self.start_button.configure(state="normal" if can_start and armed else "disabled")
        if not can_start:
            self.armed_label.configure(
                text=(
                    "This appliance type has not been verified, so Pastie will not "
                    "send it commands."
                ),
                fg=MUTED,
            )
        elif armed:
            self.armed_label.configure(
                text="Ready: the machine is armed for remote control.", fg=GREEN
            )
        else:
            self.armed_label.configure(
                text=(
                    "Not armed. Switch the machine on and turn the dial to the remote "
                    "position - it disarms itself after every completed cycle."
                ),
                fg=AMBER,
            )


def _chosen(box: ttk.Combobox) -> str:
    """The selected text of a dropdown.

    `Combobox.get` has no type of its own in the bundled stubs, so this is the
    one place that is said out loud rather than at every call site.
    """
    return str(box.get())


def _value(variable: tk.Variable) -> Any:
    """A widget variable's current value.

    `Variable.get` is untyped in the bundled stubs, so the cast happens here
    once rather than at every call site.
    """
    return variable.get()  # type: ignore[no-untyped-call]


def _copy_choice(variable: tk.Variable, box: ttk.Combobox, _event: object) -> None:
    variable.set(_chosen(box))


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    client = ServiceClient(PipeClient().ask)
    App(client).mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
