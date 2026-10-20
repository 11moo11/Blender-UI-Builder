# Blender UI Builder

Design the interface of a Blender addon *before* you write it. Add every modern Blender UI
element, rename it, see a live mockup, then export real code — for yourself, or as a prompt
for an LLM to wire up.

Targets Blender 3.6+ (exports can target 2.93+). Only tested headless on Blender 5.2 so far — see Development.

## Install

1. Run `python tools/build_zip.py` (or zip the `ui_builder/` folder yourself).
2. Blender: **Edit > Preferences > Add-ons > Install…** (4.2+: *Install from Disk*) and pick `dist/ui_builder.zip`.
3. Enable **UI Builder**.

## Use

Open the 3D Viewport sidebar (`N`) and pick the **UI Builder** tab.

| Step | How |
|---|---|
| Add elements | **Add Element** menu (Layout, Text, Properties, Buttons & Menus, Templates). New elements go **directly below the selected row**: as the container's first child if you select an expanded container, after the whole block if it is folded, or right after a selected control at the same level. |
| Rename | Double-click the name in the list, or edit it under **Selected Element**. |
| Swap a type | **Replace Selected** (next to Add Element) changes the type of the ticked / active elements in place: a Row becomes a Column, Split or Box without touching its children or nesting. Custom names and settings are kept; turning a container into a non-container moves its children up a level. |
| Select several | Tick the checkbox at the start of each row (click and drag down the checkboxes to tick many), or use the **Select** menu above the buttons (All / None / Invert / Add Children / Same Level). |
| Reorder / nest | Buttons next to the list act on all ticked rows (or the active row if none are ticked): ↑↓ reorder (children move with their parent; a group stops at the top or bottom as one), → moves into the container above, ← moves out, duplicate and delete work on the group too. |
| Tweak | **Selected Element**: icon picker, tooltip, default value, options, and layout modifiers (enabled, active, alert, scale, emboss, alignment). |
| Preview | Use **Mockup Beside** (above the list) to split the area and show the mockup next to the builder, or **Mockup Window** to open it in its own window (drag it to another monitor). |
| Preview (tabs) | The **Mockup** tab (3D Viewport sidebar) and the **Scene** tab of the Properties editor draw the UI with real Blender widgets. Buttons are inert placeholders. |
| Export | **Export** panel: choose a format, then *Text Editor*, *Copy* or *Save…*. |

New to it? **Project menu (▾ in the header) > Load Example**.

### Choices that show different controls per option

A **Choice** (dropdown or row of buttons) gets one **Option** row in the list for every entry in its *Options* field, nested directly under it. Put controls under an option (select the option row and *Add Element*) and they appear in the mockup, and in the exported `if props.choice == "option_a":` blocks, only while that option is selected. Pick an option in the mockup to see its branch.

Option rows stay in sync automatically: rename options and their contents stay with the same position, add an option and a new row appears, reorder the text and the rows follow. An option you delete that still has controls inside is kept and marked *(removed option)* until you delete or re-add it. Existing elements can be moved into a Choice's options too: with an element directly below a Choice, **Nest In** (→) puts it in the Choice's first option, **Move Down / Up** hops it between options (an element at the end of one option jumps into the next, and back), and **Nest Out** (←) takes it out of the Choice entirely. Together this builds tab-style UIs: one option per tab, each holding its own controls. Rows can be folded with the triangle at the start of a row. Controls added straight under the Choice itself (not under an option) are always shown.

#### Choice as buttons

A Choice can be a **Dropdown**, **Buttons (stacked)** (one above the other, like the expanded list in a sidebar) or **Buttons (side by side)** (one row). Tick **Icons Only** to show just the icons, and give each option an icon by selecting its Option row and using *Pick Icon*. Icons are used on the buttons and the dropdown entries, and exported in the enum items. The importer reads option icons and keeps the "this was in a row" information (a row holding one expanded dropdown becomes *side by side*), so a BlenderKit-style icon strip comes through intact.

### Where it lives

Not everything is in a sidebar panel: a panel can sit in a header dropdown, the Image Editor or the Properties editor, and some things (a viewport overlay, a gizmo, a header button) aren't drawn by a panel at all. The **Where It Lives** panel shows this:

- A schematic of the Blender window lights up every area the project uses (blue) and the selected item's area (red), with a zoomed map of the exact region (header, toolbar, main area, sidebar).
- **Panels:** choose *Same as project*, a preset (Image Editor sidebar, Properties tab...) or *Custom* editor + region + context + tab, and optionally a built-in **Parent Panel** (e.g. `VIEW3D_PT_overlay` puts it in the Overlays dropdown).
- **Other elements:** *Drawn In* marks things that live elsewhere (3D Viewport overlay, header, popup...), with a free-text note. The mockup shows them as greyed, tagged stand-ins, and they aren't emitted into the panel's `draw`.
- The importer records each scanned panel's real editor / region / parent automatically.
- Locations flow into the exported code (`bl_space_type`, `bl_region_type`, `bl_parent_id`, `# NOTE` lines) and the LLM prompt.

### Importing another addon's UI

Enable the addon you want to study, then open **UI Builder > Import From Addon**: pick the addon (its panels are listed straight away), untick any you don't want and press **Import**. The panels are replayed against a recording layout, so the result mirrors what the addon really draws: layout containers, property types (with names, tooltips, enum options, ranges and current values), operator buttons, menus, popovers, lists, and panel/sub-panel structure. The addon's name, author, location and tab are copied too (*Replace Project* mode), or choose *Append* to add to what you have. From there you can edit it and export it like any other design.

The import tidies up the layout scaffolding addons generate: empty rows/columns are dropped, single-child rows/columns are unwrapped (their scale/enabled/alert modifiers move onto the child), nested same-kind columns/rows are merged, and stray separators are removed. A text label directly followed by an unnamed value control (Choice, slider, text field, number, color, checkbox... the `Device:` + dropdown pattern) becomes a single control named after the label, with *Label on the Left* on. `template_icon` becomes a *Preview Image* element; dynamic dropdowns keep their current value as an option.

What is scraped for each field: the declared **default** (not the live runtime value, which can be arbitrary state), range, tooltip and, for dropdowns, the **options**: static lists are read from Blender, and runtime-generated lists are obtained by calling the addon's own items function. When options still can't be read, the dropdown gets clearly fake entries (`PLACEHOLDER_OPTION_1`, `PLACEHOLDER_OPTION_2`, or `PLACEHOLDER_ITEM_n` for menus) plus an `UNKNOWN OPTIONS` note in its tooltip, a red warning in the Selected Element panel, and a "Placeholders - do not treat as real" section in the LLM prompt telling the model not to guess.

After an import every fold is rolled up, so you start from a tidy outline of panels and expand what you need.

UI Builder can import itself. The live **Mockup** panels are left out (their content is your current project, not a fixed layout), and any panel, popover or menu that reaches itself while being scraped is skipped, so it always terminates. Use *Append* if you don't want to replace the project you have open.

Limits: panels whose draw code needs context that isn't there (for example a selected object) are imported up to the point where they stop, and you get a warning. Unsupported templates appear as a `(template_x)` label placeholder. Select an object / open the right editor first for the best result.

### Elements

- **Layout:** Panel, Sub-panel, Collapsible Box, Row, Column, Box, Split, Grid, Separator / Spacer
- **Text:** Label, Text Block
- **Properties:** Checkbox / Toggle, Integer, Float, Slider, Percentage, Angle, Distance, Text, File path, Folder path, Choice (dropdown or row of buttons), Color (optional Alpha), Vector 2D/3D, Euler, Data-block pointer, Search field
- **Buttons & Menus:** Button (operator), Action Menu, Popover
- **Templates:** List (UIList), Data-block selector (`template_ID`), Color wheel, Preview image, Progress bar

### Export formats

- **Python Addon** – one complete file: `bl_info`, a `PropertyGroup` with a typed property per control (your current values become defaults), a `Panel` per panel / sub-panel, operator stubs for buttons (marked `TODO`), menus, UILists, popovers, and `register()`.
- **LLM Prompt** – Markdown containing a UI outline, a property table, the operators to implement and the generated code, with a spot to describe the behaviour you want. Paste it into an LLM.
- **JSON Layout** – save the project and load it again (**Project menu > Import**).

Names become identifiers (`Render Still` → `render_still`); duplicates are numbered on export. Set the addon name, prefix, placement (3D Viewport, Properties tabs, Image/Node/Sequencer/Text/Clip editors) and tab name in the Export panel.

## Updating from GitHub

The addon updates itself from this repository:

- On startup (and via **Preferences > Add-ons > UI Builder** or the *Updates* panel) it reads the version in `ui_builder/__init__.py` on the configured branch.
- If the remote version is newer, an **Update available** banner appears. **Update Now** downloads the branch archive, replaces the addon files (rolling back on any error) and offers a **Restart Blender** button (it saves your file first, then reopens it). Scripts are deliberately not hot-reloaded, because that can crash Blender.
- **Private repository?** GitHub answers 404 to anonymous requests for private repos. Paste a read-only GitHub access token into *Access Token* in the addon preferences.
- If the configured branch doesn't exist, the repository's default branch is used. **Update Now** is only enabled when a newer version was found.
- Repository and branch are configurable in the addon preferences (default `11moo11/Blender-UI-Builder`, branch `main`). Startup checks can be turned off. Nothing is sent except the request itself, and nothing happens without Blender's *Allow Online Access* enabled (4.2+).

**To ship an update:** bump `version` in `ui_builder/__init__.py` (and `blender_manifest.toml`) and push to the update branch.

> Updating downloads and runs code from the configured repository. Only point it at repositories you trust.

## Development

```
python -m venv .venv && .venv/bin/pip install bpy
.venv/bin/python -I tests/test_headless.py
```

The test registers the addon headless, drives the operators, validates every layout call in the preview *and* in the exported code against Blender's real `UILayout` API, executes the generated addon, round-trips the JSON, and tests the updater against a fake archive.
