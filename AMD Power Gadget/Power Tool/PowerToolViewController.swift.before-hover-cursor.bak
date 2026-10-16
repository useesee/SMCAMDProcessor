//
//  PowerToolViewController.swift
//  AMD Power Gadget
//
//  Created by trulyspinach on 3/3/20.
//

import Cocoa

class PowerToolViewController: NSViewController, NSWindowDelegate {

    @IBOutlet weak var cpuFreqGraph: CPUPowerStepView!
    
    var timer : Timer?
    
    var vaildStatesClock : [Float] = []
    
    @IBOutlet weak var basicLabel: NSTextField!
    @IBOutlet weak var overviewSpeedShift: CPUSpeedShiftView!

    private static let rememberPStateDefaultsKey = "AMDPowerGadgetRememberPStateEnabled"
    private static let preferredPStateDefaultsKey = "AMDPowerGadgetPreferredPStateIndex"
    private var pstateMemoryCheckbox: NSButton?
    
    @IBOutlet weak var configTabView: NSTabView!
    @IBOutlet weak var configControl: NSSegmentedControl!
    @IBAction func onConfigControl(_ sender: Any) {
        configTabView.selectTabViewItem(at: configControl.indexOfSelectedItem)
    }
    
    @IBOutlet weak var pStateControl: NSSegmentedControl!
    @IBAction func onPStateControl(_ sender: Any) {
        
    }
    
    
    @IBOutlet var vsView: NSVisualEffectView!
    @IBOutlet weak var boxView: NSBox!
    func toggleTranslucency(enabled : Bool) {
        vsView.state = enabled ? .active : .inactive
        boxView.isTransparent = enabled
    }
    
    @IBOutlet weak var boardHelpButton: NSButton!
    @IBAction func boardHelp(_ sender: Any) {
        let alert = NSAlert()
        alert.messageText = "To enable motherboard display:"
        alert.informativeText = """
        Open your OpenCore config file,
        
        Go to Misc -> Security -> ExposeSensitiveData,
        
        Set the value to 0x08 to expose board information.
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Done")
        alert.beginSheetModal(for: view.window!, completionHandler: nil)
    }
    @IBOutlet weak var cpbSupportedBox: NSButton!
    @IBOutlet weak var cpbEnabledBox: NSButton!
    @IBAction func cpbEnabledBox(_ sender: Any) {
        ProcessorModel.shared.setCPB(enabled: cpbEnabledBox.state == .on)
        updateCPB()
    }
    
    @IBOutlet weak var asaBox: NSButton!
    @IBAction func onASA(_ sender: Any) {
        let adaptiveEnabled = asaBox.state == .on
        ProcessorModel.shared.setPPM(enabled: adaptiveEnabled)

        // If the user explicitly switches back to adaptive mode, don't force a fixed P-State later.
        if adaptiveEnabled {
            UserDefaults.standard.removeObject(forKey: "AMDPowerGadgetPreferredPStateIndex")
        }

        overviewSpeedShift.setOptions(newOptions: nil, selection: adaptiveEnabled ? -1 : 0)
        updateASA()
    }
    
    @IBOutlet weak var lpmBox: NSButton!
    @IBAction func onLPM(_ sender: Any) {
        ProcessorModel.shared.setLPM(enabled: lpmBox.state == .on)
        updateLPM()
    }
    
    @IBOutlet weak var topLabel1: NSTextField!
    @IBOutlet weak var topLabel2: NSTextField!
    
    var updateTime : Double = 0.25
    var freqMax : Float = 0
    var instDelta : UInt64 = 0
    var sumCount = 0
    
    static var activeSelf : PowerToolViewController?
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
    }
    
    @IBAction func fanControlButton(_ sender: Any) {
        SystemMonitorViewController.launch()
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        // 设置 Configurations 选中项的背景为粉色
        configControl.selectedSegmentBezelColor = NSColor.systemPink
        vaildStatesClock = ProcessorModel.shared.getVaildPStateClocks()
        cpuFreqGraph.setup(totalCores: ProcessorModel.shared.getNumOfCore())

        sampleCPUGraph()

        timer = Timer.scheduledTimer(withTimeInterval: updateTime, repeats: true, block: { (_) in
            self.sampleCPUGraph()
        })

        setupOverview()
        setupPStateMemoryCheckbox()

        updatePStateDef()
        updateCPB()
        updateASA()
        
        topLabel1.font = NSFont(name: "SF Pro Rounded", size: 32)
        topLabel2.font = NSFont(name: "SF Pro Rounded", size: 32)
        
        toggleTranslucency(enabled: UserDefaults.standard.bool(forKey: "usetranslucency"))
        
        PowerToolViewController.activeSelf = self
        AppDelegate.updateDockIcon()
    }
    
    override func viewWillAppear() {
        view.window!.delegate = self
        if timer == nil || !timer!.isValid{
            timer = Timer.scheduledTimer(withTimeInterval: updateTime, repeats: true, block: { (_) in
                self.sampleCPUGraph()
            })
        }
    }
    
    override func viewWillDisappear() {
        timer?.invalidate()
    }
    

    
    func windowWillClose(_ notification: Notification) {
        PowerToolViewController.activeSelf = nil
        AppDelegate.updateDockIcon()
    }
    
    func sampleCPUGraph() {
        let metric = ProcessorModel.shared.getMetric(forced: true)
        let load = ProcessorModel.shared.getLoadIndex()
        let a = ProcessorModel.shared.getInstructionDelta()
        let freqs = Array(metric[3...metric.count-1])
        
        cpuFreqGraph.setFreqData(data: Array(metric[3...metric.count-1]),
                                 states: vaildStatesClock, load: load)

        freqMax = max(freqMax, freqs.max()!)
        instDelta += a.reduce(0, +)

        if sumCount >= Int(1 / updateTime) {
            
            topLabel1.stringValue = String(format: "%.1f Ghz", freqMax * 0.001)
            topLabel2.stringValue = suffixNumber(number: NSNumber(value: instDelta))

            sumCount = 0
            freqMax = 0
            instDelta = 0
        } else {
            sumCount += 1
        }
        updatePStateDef()
    }
    
    @IBAction func onOverviewSpeedStep(_ sender: Any) {
        let selectedState = overviewSpeedShift.selectedItem
        guard selectedState >= 0 else { return }

        // Persist only an explicit user choice when the user enables P-State memory.
        if UserDefaults.standard.bool(forKey: Self.rememberPStateDefaultsKey) {
            UserDefaults.standard.set(selectedState, forKey: Self.preferredPStateDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }
        ProcessorModel.shared.setPPM(enabled: false)
        ProcessorModel.shared.setPState(state: selectedState)
        updateASA()
    }
    
    func setupOverview() {
        let id = ProcessorModel.shared.cpuidBasic
        let supported = id[7] == 1 ? "Yes" : "Not yet :)"
        
        let memGB = Int(ProcessorModel.shared.systemConfig["mem"]!)! / 1024
        var storageGB = "?"
        if let rs = ProcessorModel.shared.systemConfig["rs"] {
            storageGB = "\(Int(rs)! / 1024)"
        }
         
        basicLabel.stringValue = """
        \(ProcessorModel.shared.systemConfig["cpu"]!)
        Family: \(String(format:"%02X", id[0]))h, Model: \(String(format:"%02X", id[1]))h
        Physical: \(id[2]), Logical: \(id[3])
        L1(Total): \(id[4] * id[2]) KB, L2(Total): \(id[5] * id[2] / 1024) MB, L3(Shared): \(id[6] / 1024) MB
        
        Motherboard: \(ProcessorModel.shared.boardName)
        \(ProcessorModel.shared.boardVender)
        Graphics: \(ProcessorModel.shared.systemConfig["gpu"]!)
        Memory: \(memGB)GB, Storage: \(storageGB)GB
        
        macOS Version: \(ProcessorModel.shared.systemConfig["os"]!)
        AMDRyzenCPUPowerManagement:
          Version: \(ProcessorModel.shared.AMDRyzenCPUPowerManagementVersion), CPU Supported: \(supported)
        
        """
        if ProcessorModel.shared.boardValid {
            boardHelpButton.removeFromSuperview()
        }
    }
    
    private func setupPStateMemoryCheckbox() {
        // The checkbox is added to the Overview tab's existing container, next to “频率档位”.
        // This avoids changing storyboard IDs or existing outlet connections.
        guard let overviewContainer = overviewSpeedShift.superview else {
            NSLog("Unable to add the P-State memory checkbox: Overview container is missing.")
            return
        }

        let checkbox = NSButton(
            checkboxWithTitle: "",
            target: self,
            action: #selector(pstateMemoryCheckboxChanged(_:))
        )
        checkbox.frame = NSRect(x: 428, y: 240, width: 28, height: 19)
        checkbox.state = UserDefaults.standard.bool(forKey: Self.rememberPStateDefaultsKey) ? .on : .off
        checkbox.toolTip = "勾选后记忆当前的PState，并在应用启动或系统唤醒后恢复"
        overviewContainer.addSubview(checkbox)
        self.pstateMemoryCheckbox = checkbox

        // Remove any preference left by the older always-on patch when memory is disabled.
        if checkbox.state != .on {
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }
    }

    @objc private func pstateMemoryCheckboxChanged(_ sender: NSButton) {
        let rememberEnabled = sender.state == .on
        UserDefaults.standard.set(rememberEnabled, forKey: Self.rememberPStateDefaultsKey)

        guard rememberEnabled else {
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
            return
        }

        // If memory is enabled while a fixed state is already selected, save it immediately.
        // Adaptive PPM mode has no fixed P-State to remember.
        let selectedState = overviewSpeedShift.selectedItem
        if selectedState >= 0 && !ProcessorModel.shared.getPPM() {
            UserDefaults.standard.set(selectedState, forKey: Self.preferredPStateDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.preferredPStateDefaultsKey)
        }
    }

    func updatePStateDef() {
        ProcessorModel.shared.refreshPStateDef()
        vaildStatesClock = ProcessorModel.shared.getVaildPStateClocks()
        let pstateCur = ProcessorModel.shared.getPState()
        let s = ProcessorModel.shared.getPPM()
        let pdt = vaildStatesClock.map{ "\(Int($0))Mhz" }
        overviewSpeedShift.setOptions(newOptions: pdt, selection: s ? -1 : pstateCur)
    }
    
    func updateCPB() {
        let s = ProcessorModel.shared.getCPB()
        
        cpbSupportedBox.state = s[0] ? NSControl.StateValue.on : NSControl.StateValue.off
        cpbEnabledBox.state = s[1] ? NSControl.StateValue.on : NSControl.StateValue.off
    }
    
    func updateASA() {
        let s = ProcessorModel.shared.getPPM()
        
        asaBox.state = s ? NSControl.StateValue.on : NSControl.StateValue.off
        updateLPM()
    }
    
    func updateLPM() {
        lpmBox.isEnabled = ProcessorModel.shared.getPPM()
        
        let s = ProcessorModel.shared.getLPM()
        
        lpmBox.state = s ? NSControl.StateValue.on : NSControl.StateValue.off
    }
    
    @IBAction func openGitHub(_ sender: Any) {
        NSWorkspace.shared.open(URL(string: "https://github.com/trulyspinach/SMCAMDProcessor")!)
    }
    
    func suffixNumber(number:NSNumber) -> String {
        var num:Double = number.doubleValue
        let sign = ((num < 0) ? "-" : "" )

        num = fabs(num)
        if (num < 1000.0){
            return "\(sign)\(num)"
        }
        let exp:Int = Int(log10(num) / 3.0 )
        let units:[String] = ["K","M","G","T","P","E"]
        let roundedNum:Double = round(10 * num / pow(1000.0,Double(exp))) / 10

        return "\(sign)\(roundedNum)\(units[exp-1])"
    }
}
