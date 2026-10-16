#!/usr/bin/env python3
"""Add a mutually-exclusive custom startup command mode to SMCAMDProcessor.

Run this script from the local repository root. It patches the existing
PStateEditorViewController.swift and AppDelegate.swift and creates backups.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
EDITOR_PATH = ROOT / "AMD Power Gadget/Power Tool/PStateEditorViewController.swift"
APP_PATH = ROOT / "AMD Power Gadget/AppDelegate.swift"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"Expected exactly one anchor for {label}; found {count}. No files have been changed.")
    return source.replace(old, new, 1)


if not EDITOR_PATH.is_file() or not APP_PATH.is_file():
    fail("Run from the repository root; the PState editor or AppDelegate source file is missing.")

editor = EDITOR_PATH.read_text(encoding="utf-8")
app = APP_PATH.read_text(encoding="utf-8")

if "startupCommandEnabledKey" in editor or "runStartupCommandIfEnabled" in app:
    fail("The startup-command feature appears to be present already; refusing to patch twice.")

editor = replace_once(
    editor,
    "class PStateEditorViewController: NSViewController, NSTableViewDelegate, NSTableViewDataSource {",
    '''class PStateEditorViewController: NSViewController, NSTableViewDelegate, NSTableViewDataSource, NSTextFieldDelegate {

    static let autoLoadEnabledKey = "pstateAutoLoadEnabled"
    static let startupCommandEnabledKey = "pstateStartupCommandEnabled"
    static let startupCommandTextKey = "pstateStartupCommand"
    static let startupCommandExample = "sudo ./PStateRestore ./fixed.pstate"''',
    "PState editor class declaration",
)

editor = replace_once(
    editor,
    """    private var autoLoadCheckbox: NSButton!
    private var autoPathField: NSTextField!""",
    """    private var autoLoadCheckbox: NSButton!
    private var autoPathField: NSTextField!
    private var startupCommandCheckbox: NSButton!
    private var startupCommandField: NSTextField!""",
    "PState editor controls",
)

old_setup = '''    private func setupPStateAutoLoadControls() {
        // Add controls at runtime so the original storyboard IDs remain untouched.
        if let scroll = tableView.enclosingScrollView {
            var frame = scroll.frame
            frame.origin.y += 24
            frame.size.height = max(100, frame.size.height - 24)
            scroll.frame = frame
        }

        autoLoadCheckbox = NSButton(
            checkboxWithTitle: "启动加载PState：",
            target: self,
            action: #selector(autoLoadCheckboxChanged(_:))
        )
        autoLoadCheckbox.frame = NSRect(x: 20, y: 50, width: 188, height: 18)
        autoLoadCheckbox.state = UserDefaults.standard.bool(forKey: "pstateAutoLoadEnabled") ? .on : .off
        autoLoadCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(autoLoadCheckbox)

        autoPathField = NSTextField(labelWithString: Self.autoPStateURL.path)
        autoPathField.frame = NSRect(x: 160, y: 45, width: max(280, view.bounds.width - 160), height: 20)
        autoPathField.font = NSFont.systemFont(ofSize: 10)
        autoPathField.lineBreakMode = .byTruncatingMiddle
        autoPathField.toolTip = Self.autoPStateURL.path
        autoPathField.autoresizingMask = [.width, .minYMargin]
        view.addSubview(autoPathField)
    }

    @objc private func autoLoadCheckboxChanged(_ sender: NSButton) {
        UserDefaults.standard.set(sender.state == .on, forKey: "pstateAutoLoadEnabled")
    }'''

new_setup = '''    private func setupPStateAutoLoadControls() {
        // Add controls at runtime so the original storyboard IDs remain untouched.
        // Reserve two rows below the P-State table.
        if let scroll = tableView.enclosingScrollView {
            var frame = scroll.frame
            frame.origin.y += 48
            frame.size.height = max(80, frame.size.height - 48)
            scroll.frame = frame
        }

        let autoLoadEnabled = UserDefaults.standard.bool(forKey: Self.autoLoadEnabledKey)
        let requestedCommandEnabled = UserDefaults.standard.bool(forKey: Self.startupCommandEnabledKey)
        let commandEnabled = requestedCommandEnabled && !autoLoadEnabled

        // Repair conflicting saved preferences; preserve the existing built-in loader.
        if requestedCommandEnabled && autoLoadEnabled {
            UserDefaults.standard.set(false, forKey: Self.startupCommandEnabledKey)
        }

        autoLoadCheckbox = NSButton(
            checkboxWithTitle: "启动加载 PState",
            target: self,
            action: #selector(autoLoadCheckboxChanged(_:))
        )
        autoLoadCheckbox.frame = NSRect(x: 20, y: 50, width: 140, height: 18)
        autoLoadCheckbox.state = autoLoadEnabled ? .on : .off
        autoLoadCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(autoLoadCheckbox)

        autoPathField = NSTextField(labelWithString: Self.autoPStateURL.path)
        autoPathField.frame = NSRect(x: 160, y: 45, width: max(220, view.bounds.width - 175), height: 20)
        autoPathField.font = NSFont.systemFont(ofSize: 10)
        autoPathField.lineBreakMode = .byTruncatingMiddle
        autoPathField.toolTip = Self.autoPStateURL.path
        autoPathField.autoresizingMask = [.width, .minYMargin]
        view.addSubview(autoPathField)

        startupCommandCheckbox = NSButton(
            checkboxWithTitle: "启动执行命令",
            target: self,
            action: #selector(startupCommandCheckboxChanged(_:))
        )
        startupCommandCheckbox.frame = NSRect(x: 20, y: 23, width: 140, height: 18)
        startupCommandCheckbox.state = commandEnabled ? .on : .off
        startupCommandCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(startupCommandCheckbox)

        startupCommandField = NSTextField(
            string: UserDefaults.standard.string(forKey: Self.startupCommandTextKey) ?? ""
        )
        startupCommandField.frame = NSRect(x: 160, y: 19, width: max(220, view.bounds.width - 175), height: 22)
        startupCommandField.font = NSFont.systemFont(ofSize: 11)
        startupCommandField.isEditable = true
        startupCommandField.isSelectable = true
        startupCommandField.isBordered = true
        startupCommandField.placeholderString = Self.startupCommandExample
        startupCommandField.toolTip = "请输入命令。建议使用绝对路径；若使用相对路径，请先进入 PStateRestore 所在目录。"
        startupCommandField.delegate = self
        startupCommandField.autoresizingMask = [.width, .minYMargin]
        view.addSubview(startupCommandField)

        UserDefaults.standard.set(commandEnabled, forKey: Self.startupCommandEnabledKey)
    }

    @objc private func autoLoadCheckboxChanged(_ sender: NSButton) {
        let enabled = sender.state == .on
        UserDefaults.standard.set(enabled, forKey: Self.autoLoadEnabledKey)

        if enabled {
            // The two startup modes are mutually exclusive.
            startupCommandCheckbox.state = .off
            UserDefaults.standard.set(false, forKey: Self.startupCommandEnabledKey)
        }
    }

    @objc private func startupCommandCheckboxChanged(_ sender: NSButton) {
        let enabled = sender.state == .on
        UserDefaults.standard.set(enabled, forKey: Self.startupCommandEnabledKey)

        if enabled {
            // Choosing a shell command turns off the built-in .pstate loader.
            autoLoadCheckbox.state = .off
            UserDefaults.standard.set(false, forKey: Self.autoLoadEnabledKey)
        }
    }

    func controlTextDidChange(_ notification: Notification) {
        guard let field = notification.object as? NSTextField,
              field === startupCommandField else { return }
        UserDefaults.standard.set(field.stringValue, forKey: Self.startupCommandTextKey)
    }

    func controlTextDidEndEditing(_ notification: Notification) {
        guard let field = notification.object as? NSTextField,
              field === startupCommandField else { return }
        UserDefaults.standard.set(field.stringValue, forKey: Self.startupCommandTextKey)
    }'''
editor = replace_once(editor, old_setup, new_setup, "PState startup controls block")

app = replace_once(
    app,
    '''        // Delay restore slightly so launch-time driver initialization does not immediately reset the selection.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.restorePreferredPStateSelection()
        }''',
    '''        // Delay restore slightly so launch-time driver initialization does not immediately reset the selection.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            // Finish the table-restore command first, then restore a remembered P0/P1/P2 selection.
            self?.runStartupCommandIfEnabled(trigger: "login") { [weak self] in
                self?.restorePreferredPStateSelection()
            }
        }''',
    "login delayed restoration",
)

old_wake = '''    @objc private func pstateRestoreSelectionDidWake(_ notification: Notification) {
        // After wake, allow the driver/work loop time to resume before re-applying the saved selector.
        guard UserDefaults.standard.bool(forKey: "AMDPowerGadgetRememberPStateEnabled"),
              UserDefaults.standard.object(forKey: "AMDPowerGadgetPreferredPStateIndex") != nil else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.restorePreferredPStateSelection()
        }
    }'''

new_wake = '''    @objc private func pstateRestoreSelectionDidWake(_ notification: Notification) {
        // Run the selected startup action after the driver/work loop has time to resume.
        // Do not gate this callback on P-State memory: command mode must work independently.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.runStartupCommandIfEnabled(trigger: "wake") { [weak self] in
                self?.restorePreferredPStateSelection()
            }
        }
    }

    private func runStartupCommandIfEnabled(
        trigger: String,
        completion: (() -> Void)? = nil
    ) {
        // Never run the custom command when the built-in table loader is selected.
        guard UserDefaults.standard.bool(
            forKey: PStateEditorViewController.startupCommandEnabledKey
        ), !UserDefaults.standard.bool(
            forKey: PStateEditorViewController.autoLoadEnabledKey
        ) else {
            completion?()
            return
        }

        let command = (UserDefaults.standard.string(
            forKey: PStateEditorViewController.startupCommandTextKey
        ) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

        guard !command.isEmpty else {
            NSLog("P-State startup command is enabled, but the command field is empty (trigger=%@).", trigger)
            completion?()
            return
        }

        NSLog("Launching P-State startup command (trigger=%@).", trigger)

        DispatchQueue.global(qos: .utility).async {
            defer {
                DispatchQueue.main.async {
                    completion?()
                }
            }

            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            // A login shell supports shell syntax and the user's PATH. Relative paths depend
            // on the working directory; absolute paths or an explicit cd command are safer.
            process.arguments = ["-lc", command]

            do {
                try process.run()
                process.waitUntilExit()
                NSLog(
                    "P-State startup command finished (trigger=%@, exit status=%d).",
                    trigger,
                    process.terminationStatus
                )
            } catch {
                NSLog(
                    "Unable to launch P-State startup command (trigger=%@): %@",
                    trigger,
                    error.localizedDescription
                )
            }
        }
    }'''
app = replace_once(app, old_wake, new_wake, "wake callback")

# Write only after every source anchor and transformation was verified.
editor_backup = EDITOR_PATH.with_suffix(EDITOR_PATH.suffix + ".before-pstate-startup-command.bak")
app_backup = APP_PATH.with_suffix(APP_PATH.suffix + ".before-pstate-startup-command.bak")
if editor_backup.exists() or app_backup.exists():
    fail("A startup-command backup already exists. Move the existing backup(s) aside before re-running.")

shutil.copy2(EDITOR_PATH, editor_backup)
shutil.copy2(APP_PATH, app_backup)
EDITOR_PATH.write_text(editor, encoding="utf-8")
APP_PATH.write_text(app, encoding="utf-8")

print("Patch applied successfully.")
print("Modified:", EDITOR_PATH.relative_to(ROOT))
print("Modified:", APP_PATH.relative_to(ROOT))
print("Backups:", editor_backup.name, "and", app_backup.name)
print("New control: startup command checkbox + editable command field")
print("Runs when checked: 2-second delayed app launch and 2-second delayed wake notification")
print("Note: an app-based command runs after user login, not before login at the macOS boot screen.")
print("Build and test in Xcode before enabling it on your daily system.")
