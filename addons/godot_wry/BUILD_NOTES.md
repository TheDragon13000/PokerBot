# Godot WRY — patched build used by this spike

The macOS universal framework in `bin/universal-apple-darwin/` is **not** the stock
1.0.2 release. It is built from upstream `doceazedo/godot_wry` PR #93 (embedded
sub-window offset fix) plus `canvas-transform-positioning.patch`, which:

- Positions the native WebView using the Control's full canvas → screen transform
  (`Viewport.get_final_transform() * Control.get_global_transform_with_canvas()`),
  so `display/window/stretch/mode = canvas_items` (scaled + letterboxed canvases,
  fullscreen, resized windows) resolve to the correct pixels. The stock code used
  `get_global_position()` and a separate window/viewport ratio, which double-applied
  the stretch scale and ignored the letterbox offset.
- Converts Godot pixel units to native points with `screen_get_max_scale()` (what Godot
  itself uses for every window on macOS) instead of the NSWindow's per-display
  `backingScaleFactor`. With a Retina panel plus a 1x monitor attached, the stock code
  was exactly 2x off on the 1x monitor and correct on the Retina one.
- Adds `WebView.get_native_bounds() -> Rect2` (logical points) for verification.
- Warns and skips WebView creation when the display server has no native window
  handle (the editor's *embedded* game window on macOS) instead of panicking.
  The spike projects set `embed_on_play=false` in `.godot/editor/project_metadata.cfg`
  so Play from the editor opens a real window.

Rebuild:

    git clone https://github.com/doceazedo/godot_wry && cd godot_wry
    gh pr checkout 93            # or: git fetch origin pull/93/head && git checkout FETCH_HEAD
    git apply <this dir>/canvas-transform-positioning.patch
    cd rust && just build-macos-universal

Verified with `BET2BOT_WEBVIEW_AUTOTEST=1 BET2BOT_WEBVIEW_GEOMTEST=1 <app>`:
native bounds == drawn monitor screen at 1152x648, 1600x1000, 900x400 and fullscreen,
on every attached display (1x and 2x), all within 1px.
