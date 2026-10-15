#!/usr/bin/env python3
"""Persist the selected P-State index and restore it on app launch and macOS wake."""
from pathlib import Path
import shutil
import sys

root = Path.cwd()
power_tool_path = root / "AMD Power Gadget/Power Tool/PowerToolViewController.swift"
app_path = root / "AMD Power Gadget/AppDelegate.swift"
KEY = "AMDPowerGadgetPreferredPStateIndex"
WAKE_MARKER = "pstateRestoreSelectionDidWake"


def fail(message: str) -> None:
    print("ERROR:", message, file=sys.stderr)
    raise SystemExit(1)

for path in (power_tool_path, app_path):
    if not path.is_file():
        fail(f"Missing {path.relative_to(root)}. Run this script from the SMCAMDProcessor repository root.")

power_tool = power_tool_path.read_text()
app = app_path.read_text()

if KEY in power_tool or WAKE_MARKER in app:
    fail("This patch appears to have already been applied. No files were changed.")

old_step = '''    @IBAction func onOverviewSpeedStep(_ sender: Any) {
        ProcessorModel.shared.setPPM(enabled: false)
        ProcessorModel.shared.setPState(state: overviewSpeedShift.selectedItem)
        updateASA()
    }
'''
new_step = f'''    @IBAction func onOverviewSpeedStep(_ sender: Any) {{
        let selectedState = overviewSpeedShift.selectedItem
        guard selectedState >= 0 else {{ return }}

        // Persist only an explicit user choice from the P-State selector.
        UserDefaults.standard.set(selectedState, forKey: "{KEY}")
        ProcessorModel.shared.setPPM(enabled: false)
        ProcessorModel.shared.setPState(state: selectedState)
        updateASA()
    }}
'''
if old_step not in power_tool:
    fail("Could not find onOverviewSpeedStep(_:) in PowerToolViewController.swift; source layout may differ.")
power_tool = power_tool.replace(old_step, new_step, 1)

old_asa = '''    @IBAction func onASA(_ sender: Any) {
        ProcessorModel.shared.setPPM(enabled: asaBox.state == .on)

        overviewSpeedShift.setOptions(newOptions: nil, selection: asaBox.state == .on ? -1 : 0)

        updateASA()
    }
'''
new_asa = f'''    @IBAction func onASA(_ sender: Any) {{
        let adaptiveEnabled = asaBox.state == .on
        ProcessorModel.shared.setPPM(enabled: adaptiveEnabled)

        // If the user explicitly switches back to adaptive mode, don't force a fixed P-State later.
        if adaptiveEnabled {{
            UserDefaults.standard.removeObject(forKey: "{KEY}")
        }}

        overviewSpeedShift.setOptions(newOptions: nil, selection: adaptiveEnabled ? -1 : 0)
        updateASA()
    }}
'''
if old_asa not in power_tool:
    fail("Could not find onASA(_:) in PowerToolViewController.swift; source layout may differ.")
power_tool = power_tool.replace(old_asa, new_asa, 1)

anchor = '''        let useTran = UserDefaults.standard.bool(forKey: "usetranslucency")
'''
addition = f'''        // Restore a user-selected fixed P-State after the driver has initialized.
        // The selection is separate from the exported P-State definition table.
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector({WAKE_MARKER}(_:)),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
        restorePreferredPStateSelection()

'''
if anchor not in app:
    fail("Could not find the AppDelegate startup anchor before 'let useTran'.")
app = app.replace(anchor, addition + anchor, 1)

# Place restoration methods inside AppDelegate, before its final closing brace.
# The last method in the known upstream source is applyStartAtLogin(enabled:).
app_method_anchor = '''    func applyStartAtLogin(enabled: Bool) {
        startAtLoginToggle.state = enabled ? .on : .off
        UserDefaults.standard.set(enabled, forKey: "startAtLogin")
        SMLoginItemSetEnabled("wtf.spinach.APGLaunchHelper" as CFString, enabled)
    }
'''
methods = f'''

    private func restorePreferredPStateSelection() {{
        guard let preferredState = UserDefaults.standard.object(forKey: "{KEY}") as? Int else {{
            return // No fixed state has been explicitly chosen; leave adaptive/default mode untouched.
        }}

        let model = ProcessorModel.shared
        let validStateCount = model.getVaildPStateClocks().count
        guard preferredState >= 0, preferredState < validStateCount, preferredState <= 7 else {{
            NSLog("Saved P-State index %d is not valid for the current P-State table (count=%d).", preferredState, validStateCount)
            return
        }}

        // Selecting a fixed state disables the app's adaptive PPM mode first.
        model.setPPM(enabled: false)
        model.setPState(state: preferredState)
        NSLog("Restored AMD Power Gadget P-State index %d.", preferredState)
    }}

    @objc private func {WAKE_MARKER}(_ notification: Notification) {{
        // After wake, allow the driver/work loop time to resume before re-applying the saved selector.
        guard UserDefaults.standard.object(forKey: "{KEY}") != nil else {{ return }}
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {{ [weak self] in
            self?.restorePreferredPStateSelection()
        }}
    }}
'''
if app_method_anchor not in app:
    fail("Could not find applyStartAtLogin(enabled:) to place the restoration methods.")
app = app.replace(app_method_anchor, app_method_anchor + methods, 1)

# Back up first, then write. Do not overwrite an older backup automatically.
changes = [(power_tool_path, power_tool), (app_path, app)]
backups = []
for path, _ in changes:
    backup = path.with_suffix(path.suffix + ".before-pstate-selection-restore.bak")
    if backup.exists():
        fail(f"Backup already exists: {backup.relative_to(root)}. Move it aside before retrying.")
    backups.append((path, backup))

for original, backup in backups:
    shutil.copy2(original, backup)
for path, contents in changes:
    path.write_text(contents)

print("P-State selection persistence patch applied.")
print("Backups created beside PowerToolViewController.swift and AppDelegate.swift.")
print("Stored preference key:", KEY)
print("Behavior: user selection persists; app launch and wake re-apply it; enabling adaptive/ASA mode clears the fixed-state preference.")
print("Next: rebuild the AMD Power Gadget target in Xcode and test P0, P1, P2, then sleep/wake.")
