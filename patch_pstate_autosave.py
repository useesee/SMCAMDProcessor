#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys

root = Path.cwd()
editor_path = root / "AMD Power Gadget/Power Tool/PStateEditorViewController.swift"
app_path = root / "AMD Power Gadget/AppDelegate.swift"

def fail(message):
    print("ERROR:", message, file=sys.stderr)
    sys.exit(1)

if not editor_path.is_file() or not app_path.is_file():
    fail("Run from the repository root; expected AMD Power Gadget source files were not found.")

editor = editor_path.read_text()
app = app_path.read_text()
if "pstateAutoLoadEnabled" in editor or "PStateAutoStore" in editor:
    fail("The editor already appears patched; refusing to apply twice.")

anchor = "class PStateEditorViewController: NSViewController, NSTableViewDelegate, NSTableViewDataSource {\n"
addition = r'''
    // Shared .pstate file for Apply-time export and app-launch restore.
    static let autoPStateURL: URL = {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory,
                                                  in: .userDomainMask).first!
        return appSupport
            .appendingPathComponent("AMD Power Gadget", isDirectory: true)
            .appendingPathComponent("PState", isDirectory: true)
            .appendingPathComponent("automatic.pstate", isDirectory: false)
    }()

    static func loadSavedPState() -> [UInt64]? {
        guard let array = NSArray(contentsOf: autoPStateURL), array.count == 8 else {
            return nil
        }
        let values = array.compactMap { ($0 as? NSNumber)?.uint64Value }
        return values.count == 8 ? values : nil
    }

    @discardableResult
    static func savePState(_ values: [UInt64]) -> Bool {
        guard values.count == 8 else { return false }
        do {
            try FileManager.default.createDirectory(
                at: autoPStateURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            return (values as NSArray).write(to: autoPStateURL, atomically: true)
        } catch {
            NSLog("P-State auto-export failed: %@", error.localizedDescription)
            return false
        }
    }

    private var autoLoadCheckbox: NSButton!
    private var autoPathField: NSTextField!
'''
if anchor not in editor:
    fail("Could not find the PStateEditorViewController class declaration.")
editor = editor.replace(anchor, anchor + addition, 1)

anchor = '''        data = ProcessorModel.shared.getPStateDef().map({value2Dict(v: $0)})
    }
'''
replacement = r'''        data = ProcessorModel.shared.getPStateDef().map({value2Dict(v: $0)})
        setupPStateAutoLoadControls()
    }

    private func setupPStateAutoLoadControls() {
        // Add controls at runtime so the original storyboard IDs remain untouched.
        if let scroll = tableView.enclosingScrollView {
            var frame = scroll.frame
            frame.origin.y += 24
            frame.size.height = max(100, frame.size.height - 24)
            scroll.frame = frame
        }

        autoLoadCheckbox = NSButton(
            checkboxWithTitle: "启动时自动加载并应用已保存的 P-State",
            target: self,
            action: #selector(autoLoadCheckboxChanged(_:))
        )
        autoLoadCheckbox.frame = NSRect(x: 20, y: 49, width: 285, height: 18)
        autoLoadCheckbox.state = UserDefaults.standard.bool(forKey: "pstateAutoLoadEnabled") ? .on : .off
        autoLoadCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(autoLoadCheckbox)

        autoPathField = NSTextField(labelWithString: Self.autoPStateURL.path)
        autoPathField.frame = NSRect(x: 300, y: 48, width: max(180, view.bounds.width - 320), height: 20)
        autoPathField.font = NSFont.systemFont(ofSize: 10)
        autoPathField.lineBreakMode = .byTruncatingMiddle
        autoPathField.toolTip = Self.autoPStateURL.path
        autoPathField.autoresizingMask = [.width, .minYMargin]
        view.addSubview(autoPathField)
    }

    @objc private func autoLoadCheckboxChanged(_ sender: NSButton) {
        UserDefaults.standard.set(sender.state == .on, forKey: "pstateAutoLoadEnabled")
    }
'''
if anchor not in editor:
    fail("Could not find the P-State editor's viewDidLoad initialization.")
editor = editor.replace(anchor, replacement, 1)

old = '''        if err != 0 {
            alertNoPrivilege()
        } else {
            changed = false
        }
'''
new = r'''        if err != 0 {
            alertNoPrivilege()
        } else {
            changed = false
            if !Self.savePState(arr) {
                let alert = NSAlert()
                alert.messageText = "P-State 已应用，但自动导出失败"
                alert.informativeText = "无法写入以下文件：\n\(Self.autoPStateURL.path)"
                alert.alertStyle = .warning
                alert.addButton(withTitle: "好")
                alert.beginSheetModal(for: view.window!, completionHandler: nil)
            }
        }
'''
if old not in editor:
    fail("Could not find the Apply success/failure block.")
editor = editor.replace(old, new, 1)

# Avoid a force-unwrap crash if the user cancels the original Export panel.
old = '''        op.runModal()

        let arr = data.map{ dict2Value(d: $0) }
        (arr as NSArray).write(to: op.url!, atomically: true)
'''
new = '''        guard op.runModal() == .OK, let url = op.url else {
            return
        }

        let arr = data.map{ dict2Value(d: $0) }
        (arr as NSArray).write(to: url, atomically: true)
'''
if old in editor:
    editor = editor.replace(old, new, 1)

anchor = '''        UserDefaults.standard.register(defaults: keyDefaults)
        
        let useTran = UserDefaults.standard.bool(forKey: "usetranslucency")
'''
replacement = r'''        UserDefaults.standard.register(defaults: keyDefaults)

        // Restore the table at app launch only when the user has opted in.
        if UserDefaults.standard.bool(forKey: "pstateAutoLoadEnabled") {
            if let savedPState = PStateEditorViewController.loadSavedPState() {
                let result = ProcessorModel.shared.setPState(def: savedPState)
                if result != 0 {
                    let alert = NSAlert()
                    alert.messageText = "自动加载 P-State 失败"
                    alert.informativeText =
                        "无法将已保存的 P-State 表写入驱动。请检查当前用户权限，或打开 Power Tool 后手动 Apply。\n文件：\(PStateEditorViewController.autoPStateURL.path)"
                    alert.alertStyle = .warning
                    alert.addButton(withTitle: "好")
                    alert.runModal()
                }
            } else {
                NSLog("P-State auto-load is enabled, but no valid 8-entry file exists at %@",
                      PStateEditorViewController.autoPStateURL.path)
            }
        }

        let useTran = UserDefaults.standard.bool(forKey: "usetranslucency")
'''
if anchor not in app:
    fail("Could not find AppDelegate's defaults registration anchor.")
app = app.replace(anchor, replacement, 1)

for path in (editor_path, app_path):
    backup = path.with_suffix(path.suffix + ".before-pstate-autosave.bak")
    if backup.exists():
        fail("Backup already exists: " + str(backup) + "; move it aside before retrying.")
    shutil.copy2(path, backup)

editor_path.write_text(editor)
app_path.write_text(app)

print("Patch applied successfully.")
print("Backups created beside both modified source files.")
print("Auto-save path: ~/Library/Application Support/AMD Power Gadget/PState/automatic.pstate")
print("The checkbox defaults to OFF. Build and test in Xcode before enabling auto-load.")
