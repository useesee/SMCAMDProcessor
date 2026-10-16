//
//  PStateEditorViewController.swift
//  AMD Power Gadget
//
//  Created by trulyspinach on 3/10/20.
//

import Cocoa

class PStateEditorViewController: NSViewController, NSTableViewDelegate, NSTableViewDataSource, NSTextFieldDelegate {

    static let autoLoadEnabledKey = "pstateAutoLoadEnabled"
    static let startupCommandEnabledKey = "pstateStartupCommandEnabled"
    static let startupCommandTextKey = "pstateStartupCommand"
    static let startupCommandExample = "sudo ./PStateRestore ./fixed.pstate"

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
    private var startupCommandCheckbox: NSButton!
    private var startupCommandField: NSTextField!

    var data : [[String: UInt32]] = []
    
    var changed = false
    
    @IBOutlet weak var tableView: NSTableView!
    
    override func viewDidLoad() {
        super.viewDidLoad()
        // Do view setup here.
        
        tableView.dataSource = self
        tableView.delegate = self
        
        tableView.sizeToFit()
        
        data = ProcessorModel.shared.getPStateDef().map({value2Dict(v: $0)})
        setupPStateAutoLoadControls()
    }

    private func setupPStateAutoLoadControls() {
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

        autoLoadCheckbox = HoverCursorButton(
            checkboxWithTitle: "启动加载PState",
            target: self,
            action: #selector(autoLoadCheckboxChanged(_:))
        )
        autoLoadCheckbox.frame = NSRect(x: 20, y: 80, width: 128, height: 18)
        autoLoadCheckbox.state = autoLoadEnabled ? .on : .off
        autoLoadCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(autoLoadCheckbox)

        autoPathField = NSTextField(labelWithString: Self.autoPStateURL.path)
        autoPathField.frame = NSRect(x: 150, y: 75, width: max(220, view.bounds.width - 175), height: 20)
        autoPathField.font = NSFont.systemFont(ofSize: 10)
        autoPathField.lineBreakMode = .byTruncatingMiddle
        autoPathField.toolTip = Self.autoPStateURL.path
        autoPathField.autoresizingMask = [.width, .minYMargin]
        view.addSubview(autoPathField)

        startupCommandCheckbox = HoverCursorButton(
            checkboxWithTitle: "启动执行命令",
            target: self,
            action: #selector(startupCommandCheckboxChanged(_:))
        )
        startupCommandCheckbox.frame = NSRect(x: 20, y: 50, width: 128, height: 18)
        startupCommandCheckbox.state = commandEnabled ? .on : .off
        startupCommandCheckbox.autoresizingMask = [.maxXMargin, .minYMargin]
        view.addSubview(startupCommandCheckbox)

        startupCommandField = NSTextField(
            string: UserDefaults.standard.string(forKey: Self.startupCommandTextKey) ?? ""
        )
        startupCommandField.frame = NSRect(x: 150, y: 50, width: max(220, view.bounds.width - 175), height: 18)
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
    }
    
    func value2Dict(v : UInt64) -> [String: UInt32]{
        var r = [String: UInt32]()
        
        r["enabled"] = UInt32(v >> 63)
        r["IddDiv"] = UInt32((v >> 30) & 0x3)
        r["IddValue"] = UInt32((v >> 22) & 0xff)
        r["CpuVid"] = UInt32((v >> 14) & 0xff)
        r["CpuDfsId"] = UInt32((v >> 8) & 0x1f)
        r["CpuFid"] = UInt32(v & 0xff)

        
        return r
    }

    func dict2Value(d : [String: UInt32]) -> UInt64 {
        var r : UInt64 = 0
        
        r |= UInt64(d["enabled"]!) << 63
        r |= (UInt64(d["IddDiv"]!) & 0x3) << 30
        r |= (UInt64(d["IddValue"]!) & 0xff) << 22
        r |= (UInt64(d["CpuVid"]!) & 0xff) << 14
        r |= (UInt64(d["CpuDfsId"]!) & 0x1f) << 8
        r |= UInt64(d["CpuFid"]!) & 0xff
        
        return r
    }
    
    func dict2Speed(v : [String: UInt32]) -> Float{
        return Float(v["CpuFid"]!) / Float(v["CpuDfsId"]!) * 200.0
    }
    
    func speed2Dict(v : [String: UInt32], speed : UInt32) -> [String: UInt32] {
        var nd = v
        let targetFid = Float(speed) / 200.0 * Float(v["CpuDfsId"]!)
        nd["CpuFid"] = UInt32(targetFid)
        
        return nd
    }
    
    func scale2Speed(scale : Float) -> UInt32 {
        return UInt32(dict2Speed(v: data[0]) * scale)
    }
    
    func dict2scale(v : [String: UInt32]) -> Float{
        return dict2Speed(v: v) / dict2Speed(v: data[0])
    }
    
    func numberOfRows(in tableView: NSTableView) -> Int {
        return 8
    }
    
    @IBAction func apply(_ sender: Any) {
        let arr = data.map{ dict2Value(d: $0) }
        let err = ProcessorModel.shared.setPState(def: arr)
        if err != 0 {
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
    }
    
    func tableView(_ tableView: NSTableView, heightOfRow row: Int) -> CGFloat {
        return 24
    }
    
    func tableView(_ tableView: NSTableView, objectValueFor tableColumn: NSTableColumn?, row: Int) -> Any? {
        
        if tableColumn!.identifier.rawValue == "id"{
            return row
        }
        
        if tableColumn!.identifier.rawValue == "speed"{
            return dict2Speed(v: data[row])
        }
        
        if tableColumn!.identifier.rawValue == "scale"{
            return dict2scale(v: data[row])
        }
        
        return String(format: "%X", data[row][tableColumn!.identifier.rawValue]!)
    }
    
    func tableView(_ tableView: NSTableView, setObjectValue object: Any?, for tableColumn: NSTableColumn?, row: Int) {
        if tableColumn!.identifier.rawValue == "enabled"{
            data[row]["enabled"] = (object as! UInt32)
            changed = true
        } else if tableColumn!.identifier.rawValue == "scale"{
            if row == 0 {
                return
            }
            data[row] = speed2Dict(v: data[row], speed: scale2Speed(scale: Float(truncating: object as! NSNumber)))
            changed = true
            tableView.reloadData(forRowIndexes: IndexSet(arrayLiteral: row), columnIndexes: IndexSet(6...8))
            
        } else {
            if let v = UInt32(object as! String, radix: 16){
                data[row][tableColumn!.identifier.rawValue] = v
                changed = true
            } else {
                alertInvaildInput()
            }
        }
    }
    
    func alertInvaildInput(){
        let alert = NSAlert()
        alert.messageText = "Invaild Input"
        alert.informativeText = "Please type in numbers in hexadecimal."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Done")
        alert.beginSheetModal(for: view.window!, completionHandler: nil)
    }
    
    func alertNoPrivilege(){
        let alert = NSAlert()
        alert.messageText = "Unable to Set PStateDef"
        alert.informativeText = """
        Action was denied as current user does not have enough privilege,
        or was canceled by current user.
        
        
        Run AMD Power Gadget as root user or disable privilege check with boot-arg '-amdpnopchk'
        
        Otherwise, click 'Once' in the warning message to allow this change.
        """
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Done")
        alert.beginSheetModal(for: view.window!, completionHandler: nil)
    }
    
    @IBAction func revert(_ sender: Any) {
        data = ProcessorModel.shared.getPStateDef().map({value2Dict(v: $0)})
        tableView.reloadData()
    }
    
    @IBAction func close(_ sender: Any) {
        if !changed{
            closeActually()
            return
        }
        
        let alert = NSAlert()
        alert.messageText = "Your changes will not be saved"
        alert.informativeText = "Click apply to save changes before closing this windows."
        alert.alertStyle = .warning
        alert.addButton(withTitle: "Cancel")
        alert.addButton(withTitle: "Close without saving")
        alert.beginSheetModal(for: view.window!) { (res) in
            if res == NSApplication.ModalResponse.alertSecondButtonReturn {
                self.closeActually()
            }
        }
    }
    
    func closeActually() {
        if let vc = presentingViewController as? PowerToolViewController{
            vc.updatePStateDef()
        }
        
        presentingViewController?.dismiss(self)
    }
    
    @IBAction func `import`(_ sender: Any) {
        let op = NSOpenPanel()
        op.runModal()
        
        if op.url == nil {
            return
        }
        
        let arr = NSArray.init(contentsOf: op.url!) as! [UInt64]

        data = arr.map({value2Dict(v: $0)})
        tableView.reloadData()
    }
    
    @IBAction func export(_ sender: Any) {
        let op = NSSavePanel()
        op.isExtensionHidden = false
        op.allowedFileTypes = ["pstate"]
        
        op.runModal()
        
        let arr = data.map{ dict2Value(d: $0) }
        (arr as NSArray).write(to: op.url!, atomically: true)
    }
}
