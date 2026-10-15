#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch PowerTool window activation when launched from the menu bar.

Run from the SMCAMDProcessor repository root:
    python3 patch_powertool_window_activation.py
"""
from pathlib import Path
import sys

TARGET = Path("AMD Power Gadget/Power Tool/PowerToolViewController.swift")
BACKUP = TARGET.with_name(TARGET.name + ".before-powertool-window-activation.bak")


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def anchor(source: str, text: str, label: str, expected: int = 1) -> None:
    count = source.count(text)
    if count != expected:
        fail(f"{label}: expected {expected} anchor match(es), found {count}. No files changed.")


def addition(source: str, old: str, new: str, label: str) -> str:
    anchor(source, old, label)
    return source.replace(old, new, 1)


def main() -> None:
    if not TARGET.is_file():
        fail(f"Cannot find {TARGET}. Run this script from the repository root.")

    source = TARGET.read_text(encoding="utf-8")
    if "PATCH: PowerTool window activation fix" in source:
        fail("The PowerTool window activation fix is already present.")

    old_launch = '''    static var activeSelf : PowerToolViewController?
    static func launch(forceFocus: Bool = false){
        if let vc = PowerToolViewController.activeSelf {
            vc.view.window?.orderFrontRegardless()
        } else {
            let mainStoryboard = NSStoryboard.init(name: NSStoryboard.Name("Main"), bundle: nil)
            let controller = mainStoryboard.instantiateController(withIdentifier: NSStoryboard.SceneIdentifier("AMDPowerTool")) as! NSWindowController
            controller.showWindow(self)

            controller.window?.isMovableByWindowBackground = true
            
            if forceFocus {controller.window?.orderFrontRegardless()}
        }
    }'''

    new_launch = '''    static var activeSelf : PowerToolViewController?
    // PATCH: PowerTool window activation fix
    static func launch(forceFocus: Bool = false){
        if let vc = PowerToolViewController.activeSelf {
            if let window = vc.view.window {
                if forceFocus {
                    NSApp.activate(ignoringOtherApps: true)
                    window.makeKeyAndOrderFront(nil)
                } else {
                    window.orderFrontRegardless()
                }
            }
        } else {
            let mainStoryboard = NSStoryboard.init(name: NSStoryboard.Name("Main"), bundle: nil)
            let controller = mainStoryboard.instantiateController(withIdentifier: NSStoryboard.SceneIdentifier("AMDPowerTool")) as! NSWindowController
            controller.showWindow(self)

            controller.window?.isMovableByWindowBackground = true

            if forceFocus, let window = controller.window {
                NSApp.activate(ignoringOtherApps: true)
                window.makeKeyAndOrderFront(nil)
            }
        }
    }'''

    anchor(source, old_launch, "PowerToolViewController.launch(forceFocus:) implementation")
    patched = addition(source, old_launch, new_launch, "PowerToolViewController.launch(forceFocus:) implementation")

    if BACKUP.exists():
        fail(f"Backup already exists: {BACKUP}. Refusing to overwrite it.")
    BACKUP.write_text(source, encoding="utf-8")
    TARGET.write_text(patched, encoding="utf-8")
    print("[OK] PowerTool window activation patch applied.")
    print(f"[OK] Backup: {BACKUP}")
    print("Next: rebuild the AMD Power Gadget target in Xcode and test from the menu bar.")


if __name__ == "__main__":
    main()
