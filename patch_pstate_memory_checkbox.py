#!/usr/bin/env python3
"""Add a persistent '记忆' checkbox for P-State selection restore.

Run from the SMCAMDProcessor repository root, after:
  1) patch_pstate_autosave.py (if you use it), and
  2) patch_pstate_selection_restore.py.

The patch edits PowerToolViewController.swift and AppDelegate.swift only.
It validates every anchor before writing and creates side-by-side backups.
"""
from pathlib import Path
import shutil
import sys

root = Path.cwd()
power_tool_path = root / "AMD Power Gadget/Power Tool/PowerToolViewController.swift"
app_path = root / "AMD Power Gadget/AppDelegate.swift"
REMEMBER_KEY = "AMDPowerGadgetRememberPStateEnabled"
PREFERRED_KEY = "AMDPowerGadgetPreferredPStateIndex"
PATCH_MARKER = "pstateMemoryCheckbox"


def fail(message: str) -> None:
    print("ERROR:", message, file=sys.stderr)
    raise SystemExit(1)


def replace_once(source: str, anchor: str, replacement: str, label: str) -> str:
    count = source.count(anchor)
    if count != 1:
        fail(f"Anchor check failed for {label}: expected exactly 1 match, found {count}. No source files were changed.")
    return source.replace(anchor, replacement, 1)


# Step 1: verify expected source files exist.
for path in (power_tool_path, app_path):
    if not path.is_file():
        fail(f"Missing {path.relative_to(root)}. Run this script from the SMCAMDProcessor repository root.")

power_tool = power_tool_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")

# Step 2: reject duplicate application before attempting any replacement.
if PATCH_MARKER in power_tool or REMEMBER_KEY in power_tool or REMEMBER_KEY in app:
    fail("The P-State memory-checkbox patch appears to have already been applied. No files were changed.")

# Step 3: add the checkbox property and stable UserDefaults keys.
anchor = '''    @IBOutlet weak var overviewSpeedShift: CPUSpeedShiftView!
'''
addition = f'''    @IBOutlet weak var overviewSpeedShift: CPUSpeedShiftView!

    private static let rememberPStateDefaultsKey = "{REMEMBER_KEY}"
    private static let preferredPStateDefaultsKey = "{PREFERRED_KEY}"
    private var {PATCH_MARKER}: NSButton?
'''
power_tool = replace_once(power_tool, anchor, addition, "PowerToolViewController outlet declaration")
print("Anchor OK: PowerToolViewController outlet declaration")

# Step 4: create the checkbox in the Overview tab after its existing content is initialized.
anchor = '''        setupOverview()

        updatePStateDef()
'''
replacement = '''        setupOverview()
        setupPStateMemoryCheckbox()

        updatePStateDef()
'''
power_tool = replace_once(power_tool, anchor, replacement, "viewDidLoad Overview setup")
print("Anchor OK: viewDidLoad Overview setup")

# Step 5: save a selected index only when the checkbox is enabled.
anchor = '''        // Persist only an explicit user choice from the P-State selector.
        UserDefaults.standard.set(selectedState, forKey: "AMDPowerGadgetPreferredPStateIndex")
'''
replacement = '''        // Persist only an explicit user choice when the user enables P-State memory.
        if UserDefaults.standard.bool(forKey: Self.rememberPStateDefaultsKey) {
            UserDefaults.standard.set(selectedState, forKey: Self.preferredPStateDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }
'''
power_tool = replace_once(power_tool, anchor, replacement, "onOverviewSpeedStep persistence block")
print("Anchor OK: onOverviewSpeedStep persistence block")

# Step 6: add the runtime checkbox and its toggle handler immediately before updatePStateDef().
anchor = '''    func updatePStateDef() {
'''
addition = f'''    private func setupPStateMemoryCheckbox() {{
        // The checkbox is added to the Overview tab's existing container, next to “频率档位”.
        // This avoids changing storyboard IDs or existing outlet connections.
        guard let overviewContainer = overviewSpeedShift.superview else {{
            NSLog("Unable to add the P-State memory checkbox: Overview container is missing.")
            return
        }}

        let checkbox = NSButton(
            checkboxWithTitle: "记忆",
            target: self,
            action: #selector(pstateMemoryCheckboxChanged(_:))
        )
        checkbox.frame = NSRect(x: 367, y: 240, width: 67, height: 19)
        checkbox.state = UserDefaults.standard.bool(forKey: Self.rememberPStateDefaultsKey) ? .on : .off
        checkbox.toolTip = "勾选后，记忆当前的 P-State，并在应用启动或系统唤醒后恢复"
        overviewContainer.addSubview(checkbox)
        self.{PATCH_MARKER} = checkbox

        // Remove any preference left by the older always-on patch when memory is disabled.
        if checkbox.state != .on {{
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }}
    }}

    @objc private func pstateMemoryCheckboxChanged(_ sender: NSButton) {{
        let rememberEnabled = sender.state == .on
        UserDefaults.standard.set(rememberEnabled, forKey: Self.rememberPStateDefaultsKey)

        guard rememberEnabled else {{
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
            return
        }}

        // If memory is enabled while a fixed state is already selected, save it immediately.
        // Adaptive PPM mode has no fixed P-State to remember.
        let selectedState = overviewSpeedShift.selectedItem
        if selectedState >= 0 && !ProcessorModel.shared.getPPM() {{
            UserDefaults.standard.set(selectedState, forKey: Self.preferredPStateDefaultsKey)
        }} else {{
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }}
    }}

    func updatePStateDef() {{
'''
power_tool = replace_once(power_tool, anchor, addition, "updatePStateDef method insertion")
print("Anchor OK: updatePStateDef method insertion")

# Step 7: delay the launch restore until app/login and driver initialization have settled.
anchor = '''        restorePreferredPStateSelection()

        let useTran = UserDefaults.standard.bool(forKey: "usetranslucency")
'''
replacement = '''        // Delay restore slightly so launch-time driver initialization does not immediately reset the selection.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.restorePreferredPStateSelection()
        }

        let useTran = UserDefaults.standard.bool(forKey: "usetranslucency")
'''
app = replace_once(app, anchor, replacement, "applicationDidFinishLaunching restore call")
print("Anchor OK: applicationDidFinishLaunching restore call")

# Step 8: only restore when the user has enabled the checkbox.
anchor = f'''    private func restorePreferredPStateSelection() {{
        guard let preferredState = UserDefaults.standard.object(forKey: "{PREFERRED_KEY}") as? Int else {{
'''
replacement = f'''    private func restorePreferredPStateSelection() {{
        guard UserDefaults.standard.bool(forKey: "{REMEMBER_KEY}") else {{
            return // Memory is opt-in; keep the normal driver/default selection when unchecked.
        }}
        guard let preferredState = UserDefaults.standard.object(forKey: "{PREFERRED_KEY}") as? Int else {{
'''
app = replace_once(app, anchor, replacement, "restorePreferredPStateSelection opt-in guard")
print("Anchor OK: restorePreferredPStateSelection opt-in guard")

# Step 9: avoid even scheduling a wake restore when memory is disabled.
anchor = f'''        guard UserDefaults.standard.object(forKey: "{PREFERRED_KEY}") != nil else {{ return }}
'''
replacement = f'''        guard UserDefaults.standard.bool(forKey: "{REMEMBER_KEY}"),
              UserDefaults.standard.object(forKey: "{PREFERRED_KEY}") != nil else {{ return }}
'''
app = replace_once(app, anchor, replacement, "wake notification guard")
print("Anchor OK: wake notification guard")

# Step 10: refuse to overwrite backups; back up both files before writing either one.
changes = [(power_tool_path, power_tool), (app_path, app)]
backups = []
for path, _ in changes:
    backup = path.with_suffix(path.suffix + ".before-pstate-memory-checkbox.bak")
    if backup.exists():
        fail(f"Backup already exists: {backup.relative_to(root)}. Move it aside before retrying.")
    backups.append((path, backup))

for original, backup in backups:
    shutil.copy2(original, backup)
for path, contents in changes:
    path.write_text(contents, encoding="utf-8")

print("P-State memory checkbox patch applied successfully.")
print("Backups created beside PowerToolViewController.swift and AppDelegate.swift.")
print("Behavior: checkbox ON remembers the selected fixed P-State; OFF clears the saved index and disables launch/wake restoration.")
print("The checkbox preference itself is retained in UserDefaults across app relaunches.")
print("Next: rebuild the AMD Power Gadget target in Xcode; test P0/P1/P2 with memory ON, then test OFF and sleep/wake.")
