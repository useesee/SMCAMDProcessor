#!/usr/bin/env python3
"""Add native hover cursors to interactive controls in AMD Power Gadget.

Run from the SMCAMDProcessor repository root:
    python3 patch_hover_cursor.py

The patch keeps editable text fields and ordinary views untouched, while push
buttons, checkboxes/radio buttons, popup buttons and segmented controls use a
pointing-hand cursor when enabled and hovered.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
APP_DIR = ROOT / "AMD Power Gadget"
APP_DELEGATE = APP_DIR / "AppDelegate.swift"
STORYBOARD = APP_DIR / "Base.lproj" / "Main.storyboard"
BACKUP_SUFFIX = ".before-hover-cursor.bak"

CURSOR_CLASSES = r'''// Native hover cursors for interactive AppKit controls.
// These subclasses are also used by Main.storyboard via customClass.
final class HoverCursorButton: NSButton {
    override func resetCursorRects() {
        super.resetCursorRects()
        guard isEnabled, !isHidden, alphaValue > 0 else { return }
        addCursorRect(bounds, cursor: .pointingHand)
    }
}

final class HoverCursorSegmentedControl: NSSegmentedControl {
    override func resetCursorRects() {
        super.resetCursorRects()
        guard isEnabled, !isHidden, alphaValue > 0 else { return }
        addCursorRect(bounds, cursor: .pointingHand)
    }
}

final class HoverCursorPopUpButton: NSPopUpButton {
    override func resetCursorRects() {
        super.resetCursorRects()
        guard isEnabled, !isHidden, alphaValue > 0 else { return }
        addCursorRect(bounds, cursor: .pointingHand)
    }
}
'''


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        fail(f"Cannot read {path}: {exc}")


def patch_app_delegate(text: str) -> tuple[str, bool]:
    class_names = (
        "HoverCursorButton",
        "HoverCursorSegmentedControl",
        "HoverCursorPopUpButton",
    )
    present = [name in text for name in class_names]
    if all(present):
        return text, False
    if any(present):
        fail("AppDelegate.swift contains only some hover-cursor classes; inspect the file before retrying.")

    anchor = "import ServiceManagement\n"
    if text.count(anchor) != 1:
        fail("Could not uniquely locate `import ServiceManagement` in AppDelegate.swift.")
    text = text.replace(anchor, anchor + "\n" + CURSOR_CLASSES + "\n", 1)
    return text, True


def patch_storyboard(text: str) -> tuple[str, bool, dict[str, int]]:
    class_for_tag = {
        "button": "HoverCursorButton",
        "segmentedControl": "HoverCursorSegmentedControl",
        "popUpButton": "HoverCursorPopUpButton",
    }
    changed = False
    counts: dict[str, int] = {}

    for tag, class_name in class_for_tag.items():
        pattern = re.compile(rf"<{re.escape(tag)}\b[^>]*>")
        matches = list(pattern.finditer(text))
        counts[tag] = len(matches)
        if not matches:
            continue

        def replace_tag(match: re.Match[str]) -> str:
            nonlocal changed
            fragment = match.group(0)
            existing = re.search(r'\bcustomClass="([^"]+)"', fragment)
            if existing:
                old_class = existing.group(1)
                if old_class == class_name:
                    return fragment
                fail(
                    f"Storyboard <{tag}> already uses custom class {old_class!r}; "
                    f"not overwriting it with {class_name!r}."
                )
            # The app's storyboard uses AMD_Power_Gadget as its Swift module.
            insertion = f' customClass="{class_name}" customModule="AMD_Power_Gadget"'
            changed = True
            return fragment[:-1] + insertion + ">"

        text = pattern.sub(replace_tag, text)

    return text, changed, counts


def patch_dynamic_button_initializers(path: Path, text: str) -> tuple[str, bool, int]:
    # Any NSButton instantiated in Swift gets the cursor-aware subclass; IBOutlet
    # property declarations and NSButton type references remain unchanged.
    result, count = re.subn(r"\bNSButton(?=\s*\()", "HoverCursorButton", text)
    return result, result != text, count


def main() -> None:
    if not APP_DELEGATE.is_file() or not STORYBOARD.is_file():
        fail("Run this script from the repository root; AMD Power Gadget source files were not found.")

    candidates = [APP_DELEGATE, STORYBOARD]
    candidates.extend(p for p in APP_DIR.rglob("*.swift") if p != APP_DELEGATE)
    originals = {p: read_text(p) for p in dict.fromkeys(candidates)}
    updated = dict(originals)
    changed_paths: set[Path] = set()

    updated[APP_DELEGATE], changed = patch_app_delegate(updated[APP_DELEGATE])
    if changed:
        changed_paths.add(APP_DELEGATE)

    updated[STORYBOARD], changed, storyboard_counts = patch_storyboard(updated[STORYBOARD])
    if changed:
        changed_paths.add(STORYBOARD)

    dynamic_count = 0
    for path in candidates:
        if path == APP_DELEGATE or path == STORYBOARD:
            continue
        new_text, changed, n = patch_dynamic_button_initializers(path, updated[path])
        updated[path] = new_text
        dynamic_count += n
        if changed:
            changed_paths.add(path)

    # If no source was changed, treat that as an already-applied patch rather than
    # writing duplicate backups or modifying timestamps.
    if not changed_paths:
        print("Hover cursor patch is already applied; no files changed.")
        print(f"Storyboard controls checked: {storyboard_counts}")
        return

    conflicts = [Path(str(path) + BACKUP_SUFFIX) for path in changed_paths if Path(str(path) + BACKUP_SUFFIX).exists()]
    if conflicts:
        fail("Backup already exists; move it aside before retrying:\n" + "\n".join(map(str, conflicts)))

    # Validate target class coverage before touching files.
    for cls in ("HoverCursorButton", "HoverCursorSegmentedControl", "HoverCursorPopUpButton"):
        if cls not in updated[APP_DELEGATE]:
            fail(f"Missing class definition after patch: {cls}")
    for tag, cls in (("button", "HoverCursorButton"),
                     ("segmentedControl", "HoverCursorSegmentedControl"),
                     ("popUpButton", "HoverCursorPopUpButton")):
        if f'customClass="{cls}"' not in updated[STORYBOARD] and storyboard_counts[tag] > 0:
            fail(f"Storyboard class assignment was not applied for <{tag}>.")

    for path in sorted(changed_paths):
        backup = Path(str(path) + BACKUP_SUFFIX)
        shutil.copy2(path, backup)
    for path in sorted(changed_paths):
        path.write_text(updated[path], encoding="utf-8")

    print("Hover cursor patch applied.")
    print("Files changed:")
    for path in sorted(changed_paths):
        print(f"  - {path.relative_to(ROOT)}")
    print("Backups created beside each modified file with suffix " + BACKUP_SUFFIX)
    print(f"Storyboard control tags found: {storyboard_counts}")
    print(f"Dynamic NSButton initializers changed: {dynamic_count}")
    print("Build the AMD Power Gadget target in Xcode and test enabled/disabled controls.")


if __name__ == "__main__":
    main()
