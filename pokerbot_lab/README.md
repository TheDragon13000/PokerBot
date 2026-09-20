# PokerBot Lab (Bet2Bot inside the computer)

Walk to the computer and press **E**: the screen opens the PokerBot Lab — the
[Bet2Bot](https://github.com/Monoamial/Bet2Bot) poker-bot app (Learn / Play / Campaign)
running inside the game. **Esc** or the Close button returns to the room.

## How it works

```
computer.gd  --E-->  PokerBotLab.open()          (autoload, pokerbot_lab.tscn)
                       |- pauses the game, shows a CanvasLayer with a header + Close
                       |- WebView (Godot WRY) shows Bet2Bot
                       '- Bet2Bot is served from pokerbot_lab/web on http://127.0.0.1:18321
                          by local_server.py  -> fully offline, no account, no internet
```

- `pokerbot_lab/web/` is a production build of Bet2Bot (HTML/JS/CSS + the Python poker
  engine + the Pyodide runtime that runs it in the page). Rebuild it from the Bet2Bot repo
  with `npm run build -- --base=/` and copy `game/dist/` here; bump `web/bundle-version.txt`
  so exported builds re-extract it.
- The Lab loads once at game start (the Python engine takes a few seconds to boot) and is
  then just shown/hidden, so opening the computer is instant after the first time.
- The original Python code editor (`code_editor_ui.tscn`) is untouched. To use it instead,
  tick **Use Code Editor** on the computer node in `room_1.tscn`.

## Running from the Godot editor

The WebView is a real native view and needs a real window, so the game must **not** run
embedded inside the editor. If pressing Play shows the game inside the editor's Game tab,
open the **Embedding options** menu in that tab's toolbar and untick
**Embed Game on Next Play**. (You'll see a `Godot WRY: ... no native window handle`
warning instead of the Lab if it is still embedded.)

## Exporting

Both presets (Windows Desktop, macOS) already include `pokerbot_lab/web/**` and
`local_server.py`. The local server needs Python 3 on the machine (`python` on Windows,
system `python3` on macOS) — the same assumption the code editor makes. Replacing it
with a built-in server so no Python is needed is a planned follow-up.

`addons/godot_wry/` is a **patched** Godot WRY (see `BUILD_NOTES.md` there). The macOS
framework is built from the patch; the Windows/Linux binaries are still the stock
1.0.2 release and will position the WebView wrongly under the project's
`canvas_items` stretch until they are rebuilt from the same source.

## Self-test

```
POKERBOT_LAB_AUTOTEST=1 <godot or exported binary> --path .
```

opens the Lab at startup and checks that the native WebView sits exactly on its Control
at several window sizes on every attached display, printing `GEOMTEST PASS`/`FAIL`.
