//
//  StatusbarController.swift
//  AMD Power Gadget
//
//  Menu-bar layout modification:
//  - CPU label is vertical like TEM/PWR.
//  - Layout and spacing are controlled by StatusbarLayout constants.
//  - Temperature turns red above 75 C; power turns red above 10 W.
//

import Cocoa

/// Tweak these constants to adjust menu-bar positions and spacing.
private enum StatusbarLayout {
    static let itemWidth: CGFloat = 95

    static let cpuX: CGFloat = 0
    static let temperatureX: CGFloat = 33
    static let powerX: CGFloat = 68

    static let labelWidth: CGFloat = 8
    static let labelOriginY: CGFloat = -4.5
    static let frequencyValueOffsetX: CGFloat = 8
    static let metricValueOffsetX: CGFloat = 8
    static let valueOriginY: CGFloat = 2.5

    static let frequencyTopY: CGFloat = 10
    static let frequencyBottomY: CGFloat = 0

    static let frequencyThreshold: Float = 3.2
    static let temperatureThreshold: Float = 70
    static let powerThreshold: Float = 10

    static let highlightColor = NSColor(
        calibratedRed: 1,
        green: 0.6,
        blue: 0,
        alpha: 1
    )
}

fileprivate class StatusbarView: NSView {

    var meanFreq: Float = 0
    var maxFreq: Float = 0
    var temp: Float = 0
    var pwr: Float = 0

    var normalLabel: [NSAttributedString.Key: NSObject]?
    var compactLabel: [NSAttributedString.Key: NSObject]?
    var normalValue: [NSAttributedString.Key: NSObject]?
    var compactValue: [NSAttributedString.Key: NSObject]?

    func setup() {
        let compactLineHeight: CGFloat = 6

        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.minimumLineHeight = compactLineHeight
        paragraphStyle.maximumLineHeight = compactLineHeight

        compactLabel = [
            .font: NSFont(name: "Monaco", size: 7.2)!,
            .foregroundColor: NSColor.labelColor,
            .paragraphStyle: paragraphStyle
        ]

        normalValue = [
            .font: NSFont.systemFont(ofSize: 14, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]

        compactValue = [
            .font: NSFont.systemFont(ofSize: 9, weight: .semibold),
            .foregroundColor: NSColor.labelColor
        ]

        normalLabel = [
            .font: NSFont.systemFont(ofSize: 13, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]
    }

    override func draw(_ dirtyRect: NSRect) {
        guard NSGraphicsContext.current?.cgContext != nil else { return }

        let averageFrequencyGHz = meanFreq * 0.001
        let maximumFrequencyGHz = maxFreq * 0.001
        let averageFrequency = String(format: "%.1f", averageFrequencyGHz)
        let maximumFrequency = String(format: "%.1f", maximumFrequencyGHz)

        // CPU is drawn vertically like TEM/PWR. Each frequency value turns pink
        // independently when its own value is greater than 3.2 GHz.
        drawDoubleCompactValue(
            label: "CPU",
            up: "\(maximumFrequency)ᴳ",
            down: "\(averageFrequency)ᴳ",
            x: StatusbarLayout.cpuX,
            upColor: maximumFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor,
            downColor: averageFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

        // Only the metric that crosses its own threshold turns red.
        drawCompactSingle(
            label: "TMP",
            value: "\(Int(round(temp)))º",
            x: StatusbarLayout.temperatureX,
            valueColor: temp > StatusbarLayout.temperatureThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

        drawCompactSingle(
            label: "PWR",
            value: "\(Int(round(pwr)))ᵂ",
            x: StatusbarLayout.powerX,
            valueColor: pwr > StatusbarLayout.powerThreshold ? StatusbarLayout.highlightColor : .labelColor
        )
    }

    /// Draw a compact vertical label in exactly the same narrow text area used by TEM/PWR.
    private func drawVerticalLabel(_ label: String, x: CGFloat) {
        let attributedLabel = NSAttributedString(string: label, attributes: compactLabel)
        attributedLabel.draw(
            in: NSRect(
                x: x,
                y: StatusbarLayout.labelOriginY,
                width: StatusbarLayout.labelWidth,
                height: frame.height
            )
        )
    }

    /// Draw a vertical label followed by two stacked frequency values.
    func drawDoubleCompactValue(
        label: String,
        up: String,
        down: String,
        x: CGFloat,
        upColor: NSColor = .labelColor,
        downColor: NSColor = .labelColor
    ) {
        drawVerticalLabel(label, x: x)

        var upperAttributes = compactValue ?? [:]
        upperAttributes[.foregroundColor] = upColor
        let upperValue = NSAttributedString(string: up, attributes: upperAttributes)
        upperValue.draw(
            at: NSPoint(
                x: x + StatusbarLayout.frequencyValueOffsetX,
                y: StatusbarLayout.frequencyTopY
            )
        )

        var lowerAttributes = compactValue ?? [:]
        lowerAttributes[.foregroundColor] = downColor
        let lowerValue = NSAttributedString(string: down, attributes: lowerAttributes)
        lowerValue.draw(
            at: NSPoint(
                x: x + StatusbarLayout.frequencyValueOffsetX,
                y: StatusbarLayout.frequencyBottomY
            )
        )
    }

    /// Draw a vertical label and a value whose color can change with the live metric.
    func drawCompactSingle(
        label: String,
        value: String,
        x: CGFloat,
        valueColor: NSColor = .labelColor
    ) {
        drawVerticalLabel(label, x: x)

        var valueAttributes = normalValue ?? [:]
        valueAttributes[.foregroundColor] = valueColor

        let attributedValue = NSAttributedString(string: value, attributes: valueAttributes)
        attributedValue.draw(
            at: NSPoint(
                x: x + StatusbarLayout.metricValueOffsetX,
                y: StatusbarLayout.valueOriginY
            )
        )
    }
}

class StatusbarController {

    var statusItem: NSStatusItem!
    fileprivate var view: StatusbarView!

    var updateTimer: Timer?
    var menu: NSMenu?

    init() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.isVisible = true

        view = StatusbarView()
        view.setup()

        statusItem.button?.wantsLayer = true
        statusItem.button?.addSubview(view)

        statusItem.button?.target = self
        statusItem.button?.action = #selector(itemClicked)
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        statusItem.length = StatusbarLayout.itemWidth
        view.frame = statusItem.button!.bounds

        addMenuItems()

        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { _ in
            self.update()
        })
    }

    func dismiss() {
        updateTimer?.invalidate()
        NSStatusBar.system.removeStatusItem(statusItem!)
        statusItem = nil
    }

    func update() {
        let numberOfCores = ProcessorModel.shared.getNumOfCore()
        let outputStr: [Float] = ProcessorModel.shared.getMetric(forced: false)

        let power = outputStr[0]
        let temperature = outputStr[1]
        var frequencies: [Float] = []

        for i in 0...(numberOfCores - 1) {
            frequencies.append(outputStr[Int(i + 3)])
        }

        let meanFre = Float(frequencies.reduce(0, +) / Float(frequencies.count))
        let maxFre = Float(frequencies.max()!)

        view?.meanFreq = meanFre
        view?.maxFreq = maxFre
        view?.temp = temperature
        view?.pwr = power
        view.setNeedsDisplay(view.frame)
    }

    @objc func itemClicked() {
        switch NSApp.currentEvent?.type {
        case .leftMouseUp:
            NSApp.activate(ignoringOtherApps: true)
            ViewController.launch(forceFocus: true)

        case .rightMouseUp:
            guard let m = menu else { return }
            statusItem.popUpMenu(m)

        default:
            break
        }
    }

    @objc func gadget() {
        ViewController.launch(forceFocus: true)
    }

    @objc func tool() {
        PowerToolViewController.launch(forceFocus: true)
    }

    @objc func fans() {
        SystemMonitorViewController.launch(forceFocus: true)
    }

    @objc func exitApp() {
        exit(0)
    }

    private func addMenuItems() {
        menu = NSMenu()
        guard let m = menu else { return }

        var item = NSMenuItem(title: "AMD Power Gadget", action: #selector(gadget), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        item = NSMenuItem(title: "AMD Power Tool", action: #selector(tool), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        item = NSMenuItem(title: "SMC Fans", action: #selector(fans), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        m.addItem(NSMenuItem.separator())

        item = NSMenuItem(title: "Exit", action: #selector(exitApp), keyEquivalent: "")
        item.target = self
        m.addItem(item)
    }
}
