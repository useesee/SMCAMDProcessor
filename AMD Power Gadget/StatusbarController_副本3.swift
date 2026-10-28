//
//  StatusbarController.swift
//  AMD Power Gadget
//
//  Menu-bar layout modification:
//  - CPU label is vertical like TEM/PWR.
//  - Layout and spacing are controlled by StatusbarLayout constants.
//  - Temperature turns red above 70 C; power turns red above 10 W.
//

import Cocoa
import Darwin.Mach
import QuartzCore

/// Tweak these constants to adjust menu-bar positions and spacing.
// BEGIN statusbar-fan-memory patch (2026-10-22)
/// All menu-bar geometry and thresholds are centralized here.
private enum StatusbarLayout {
    static let fanX: CGFloat = 0
    static let fanSize: CGFloat = 18
    static let frequencyValueOffsetX: CGFloat = 2
    static var cpuValueX: CGFloat { fanX + fanSize + frequencyValueOffsetX }

    static let temperatureX: CGFloat = 42
    static let powerX: CGFloat = 72
    static let labelWidth: CGFloat = 8
    static let labelOriginY: CGFloat = -4
    static let metricValueOffsetX: CGFloat = 6
    static let valueOriginY: CGFloat = 2.5
    static let frequencyTopY: CGFloat = 9
    static let frequencyBottomY: CGFloat = -1

    static let memoryPieSize: CGFloat = 18
    static let powerValueWidth: CGFloat = 18
    static let powerToMemoryPieGap: CGFloat = 6
    static var memoryPieX: CGFloat {
        powerX + metricValueOffsetX + powerValueWidth + powerToMemoryPieGap
    }
    static let memoryPieToValueGap: CGFloat = 2
    static var memoryValueX: CGFloat {
        memoryPieX + memoryPieSize + memoryPieToValueGap
    }
    static let memoryValueWidth: CGFloat = 28
    static var itemWidth: CGFloat { memoryValueX + memoryValueWidth + 2 }

    static let frequencyThreshold: Float = 3.2
    static let temperatureThreshold: Float = 70
    static let fanTemperatureThreshold: Float = 65
    static let powerThreshold: Float = 10

    // The fan hot state uses the exact same color as the highlighted CPU frequency.
    static let highlightColor = NSColor(
        calibratedRed: 1,
        green: 0.6,
        blue: 0,
        alpha: 1
    )
    static let fanNormalColor = NSColor.white
    static let availableColor = NSColor(calibratedRed: 0.20, green: 0.76, blue: 0.36, alpha: 1)
    static let appMemoryColor = NSColor(calibratedRed: 0.88, green: 0.57, blue: 0.12, alpha: 1)
    static let wiredColor = NSColor(calibratedRed: 0.20, green: 0.6, blue: 0.98, alpha: 1)
    static let compressedColor = NSColor(calibratedRed: 0.8, green: 0.36, blue: 0.5, alpha: 1)
}

/// Four curved swept blades. One Core Animation rotation is installed in init;
/// speed changes only remap layer time and therefore keep the current phase.
private final class FanIndicatorView: NSView {
    private let rotorLayer = CALayer()
    private let bladesLayer = CAShapeLayer()
    private let hubLayer = CAShapeLayer()
    private var currentLayerSpeed: Float = 1.0
    private var isHot = false

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        rotorLayer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        rotorLayer.addSublayer(bladesLayer)
        rotorLayer.addSublayer(hubLayer)
        layer?.addSublayer(rotorLayer)
        configurePaths()
        installRotationAnimation()
        applyColor(isHot: false)
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        rotorLayer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        rotorLayer.addSublayer(bladesLayer)
        rotorLayer.addSublayer(hubLayer)
        layer?.addSublayer(rotorLayer)
        configurePaths()
        installRotationAnimation()
        applyColor(isHot: false)
    }

    private func installRotationAnimation() {
        let rotation = CABasicAnimation(keyPath: "transform.rotation.z")
        rotation.fromValue = 0.0
        rotation.toValue = -2.0 * Double.pi // negative angle is clockwise in layer coordinates
        rotation.duration = 10.0             // base speed: one turn in ten seconds
        rotation.repeatCount = .infinity
        rotation.timingFunction = CAMediaTimingFunction(name: .linear)
        rotorLayer.add(rotation, forKey: "fan.rotation")
    }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        bladesLayer.frame = rotorLayer.bounds
        hubLayer.frame = rotorLayer.bounds
        configurePaths()
        CATransaction.commit()
    }

    func updateTemperature(_ temperature: Float, crossedThreshold: Bool) {
        guard temperature.isFinite else { return }
        updateRotationSpeed(forTemperature: temperature)
        if crossedThreshold {
            applyColor(isHot: temperature > StatusbarLayout.fanTemperatureThreshold)
        }
    }

    func setInitialTemperature(_ temperature: Float) {
        guard temperature.isFinite else { return }
        updateRotationSpeed(forTemperature: temperature)
        applyColor(isHot: temperature > StatusbarLayout.fanTemperatureThreshold)
    }

    private func applyColor(isHot newValue: Bool) {
        isHot = newValue
        let color = (newValue ? StatusbarLayout.highlightColor : StatusbarLayout.fanNormalColor).cgColor
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        bladesLayer.fillColor = color
        CATransaction.commit()
    }

    /// Returns the requested revolution period. The function is continuous at
    /// 68 C, gentle below it, and substantially steeper above it.
    private func revolutionPeriod(forTemperature temperature: Float) -> Double {
        let value = min(85.0, max(50.0, Double(temperature)))
        let rotationsPerSecond: Double
        if value <= 68.0 {
            let progress = (value - 50.0) / 18.0
            rotationsPerSecond = 0.1 + 0.4 * pow(progress, 1.7)
        } else {
            let progress = (value - 68.0) / 17.0
            rotationsPerSecond = 0.5 + ((1.0 / 0.3) - 0.5) * pow(progress, 0.9)
        }
        return 1.0 / rotationsPerSecond
    }

    private func updateRotationSpeed(forTemperature temperature: Float) {
        let period = revolutionPeriod(forTemperature: temperature)
        let newSpeed = Float(10.0 / period) // animation itself remains a single 10-second loop
        guard abs(newSpeed - currentLayerSpeed) > 0.0001 else { return }

        // Preserve the current layer-local time as the new speed takes effect.
        // Local time is the animation phase source; no animation is removed/re-added.
        let now = CACurrentMediaTime()
        let currentLocalTime = rotorLayer.convertTime(now, from: nil)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        rotorLayer.speed = newSpeed
        rotorLayer.beginTime = now
        rotorLayer.timeOffset = currentLocalTime
        CATransaction.commit()
        currentLayerSpeed = newSpeed
    }

    private func configurePaths() {
        let side = max(bounds.width, bounds.height)
        guard side > 0 else { return }
        let center = CGPoint(x: side / 2.0, y: side / 2.0)

        // REFERENCE_TRACE_POINTS: initial mockup contour traced from its blade silhouette.
        // Coordinates are normalized from the original four-lobed icon, rather than a generic fan glyph.
        // The contour is smoothed from the original image mask to retain a round outer cap and narrow swept root.
        let contourPoints: [CGPoint] = [
            CGPoint(x: side * 0.49518, y: side * 0.99508),
            CGPoint(x: side * 0.46909, y: side * 0.98574),
            CGPoint(x: side * 0.44274, y: side * 0.97778),
            CGPoint(x: side * 0.41687, y: side * 0.96582),
            CGPoint(x: side * 0.39465, y: side * 0.94588),
            CGPoint(x: side * 0.37605, y: side * 0.92223),
            CGPoint(x: side * 0.36100, y: side * 0.89875),
            CGPoint(x: side * 0.35032, y: side * 0.87304),
            CGPoint(x: side * 0.34583, y: side * 0.84411),
            CGPoint(x: side * 0.34702, y: side * 0.81426),
            CGPoint(x: side * 0.34740, y: side * 0.78354),
            CGPoint(x: side * 0.34578, y: side * 0.75285),
            CGPoint(x: side * 0.35022, y: side * 0.72483),
            CGPoint(x: side * 0.36331, y: side * 0.69988),
            CGPoint(x: side * 0.37153, y: side * 0.67257),
            CGPoint(x: side * 0.38611, y: side * 0.64960),
            CGPoint(x: side * 0.40286, y: side * 0.62351),
            CGPoint(x: side * 0.42378, y: side * 0.61909),
            CGPoint(x: side * 0.44925, y: side * 0.63243),
            CGPoint(x: side * 0.47396, y: side * 0.64545),
            CGPoint(x: side * 0.50264, y: side * 0.64703),
            CGPoint(x: side * 0.51464, y: side * 0.67107),
            CGPoint(x: side * 0.52779, y: side * 0.69578),
            CGPoint(x: side * 0.54239, y: side * 0.72039),
            CGPoint(x: side * 0.55953, y: side * 0.74304),
            CGPoint(x: side * 0.57741, y: side * 0.76541),
            CGPoint(x: side * 0.59418, y: side * 0.78953),
            CGPoint(x: side * 0.61215, y: side * 0.81301),
            CGPoint(x: side * 0.63407, y: side * 0.83292),
            CGPoint(x: side * 0.65977, y: side * 0.84906),
            CGPoint(x: side * 0.68288, y: side * 0.86686),
            CGPoint(x: side * 0.69663, y: side * 0.89162),
            CGPoint(x: side * 0.69800, y: side * 0.92043),
            CGPoint(x: side * 0.68602, y: side * 0.94574),
            CGPoint(x: side * 0.66222, y: side * 0.96290),
            CGPoint(x: side * 0.63429, y: side * 0.97447),
            CGPoint(x: side * 0.60904, y: side * 0.98333),
            CGPoint(x: side * 0.58095, y: side * 0.98727),
            CGPoint(x: side * 0.55215, y: side * 0.99294),
            CGPoint(x: side * 0.52537, y: side * 1.00008)
        ]

        // Mirror the traced blade horizontally around the rotor centre.
        // This reverses the blade sweep seen in the previous build, while preserving
        // the exact silhouette, fourfold layout, hub and clockwise rotor animation.
        let mirroredContourPoints = contourPoints.map {
            CGPoint(x: side - $0.x, y: $0.y)
        }

        let blade = CGMutablePath()
        let pointCount = mirroredContourPoints.count
        if pointCount > 2 {
            blade.move(to: mirroredContourPoints[0])
            // Smooth the mirrored screenshot-traced contour with closed Catmull-Rom-to-Bezier
            // segments. This avoids a polygonal appearance at the 16 pt menu-bar size.
            for index in 0..<pointCount {
                let p0 = mirroredContourPoints[(index - 1 + pointCount) % pointCount]
                let p1 = mirroredContourPoints[index]
                let p2 = mirroredContourPoints[(index + 1) % pointCount]
                let p3 = mirroredContourPoints[(index + 2) % pointCount]
                let control1 = CGPoint(
                    x: p1.x + (p2.x - p0.x) / 6.0,
                    y: p1.y + (p2.y - p0.y) / 6.0
                )
                let control2 = CGPoint(
                    x: p2.x - (p3.x - p1.x) / 6.0,
                    y: p2.y - (p3.y - p1.y) / 6.0
                )
                blade.addCurve(to: p2, control1: control1, control2: control2)
            }
            blade.closeSubpath()
        }

        // Rotate the traced lobe around the exact center four times. Keeping the gaps
        // and asymmetry of this contour is what makes it match the reference fan symbol.
        let allBlades = CGMutablePath()
        for index in 0..<4 {
            let angle = CGFloat(index) * CGFloat.pi / 2.0
            let cosine = cos(angle)
            let sine = sin(angle)
            let transform = CGAffineTransform(
                a: cosine,
                b: sine,
                c: -sine,
                d: cosine,
                tx: center.x - cosine * center.x + sine * center.y,
                ty: center.y - sine * center.x - cosine * center.y
            )
            allBlades.addPath(blade, transform: transform)
        }
        bladesLayer.path = allBlades
        bladesLayer.fillColor = (isHot ? StatusbarLayout.highlightColor : StatusbarLayout.fanNormalColor).cgColor

        // The reference uses a white circular hub with a narrow dark outline.
        // This stroke remains independent of the temperature-colored blades.
        let hubRadius = side * 0.090
        hubLayer.path = CGPath(
            ellipseIn: CGRect(x: center.x - hubRadius, y: center.y - hubRadius,
                             width: hubRadius * 2.0, height: hubRadius * 2.0),
            transform: nil
        )
        hubLayer.fillColor = NSColor.white.cgColor
        hubLayer.strokeColor = NSColor(calibratedWhite: 0.12, alpha: 1).cgColor
        hubLayer.lineWidth = 0.5
        hubLayer.lineJoin = .round
    }
}

/// Physical-memory snapshot; all values are byte counts and pie segments sum
/// to installed physical RAM. App memory follows the requested internal-purgeable estimate.
private struct MemorySnapshot {
    let availableBytes: UInt64
    let appBytes: UInt64
    let wiredBytes: UInt64
    let compressedBytes: UInt64

    var usedBytes: UInt64 { appBytes + wiredBytes + compressedBytes }
    var totalBytes: UInt64 { availableBytes + usedBytes }
    var availableGB: Double { Double(availableBytes) / 1_073_741_824.0 }
    var appGB: Double { Double(appBytes) / 1_073_741_824.0 }
    var wiredGB: Double { Double(wiredBytes) / 1_073_741_824.0 }
    var compressedGB: Double { Double(compressedBytes) / 1_073_741_824.0 }
    var usedGB: Double { Double(usedBytes) / 1_073_741_824.0 }

    static let zero = MemorySnapshot(availableBytes: 0, appBytes: 0, wiredBytes: 0, compressedBytes: 0)
}

/// Sampled once per existing one-second status-bar update; no extra timer is created.
private enum MemorySampler {
    static func sample() -> MemorySnapshot? {
        var statistics = vm_statistics64_data_t()
        let capacity = MemoryLayout<vm_statistics64_data_t>.size / MemoryLayout<integer_t>.size
        var count = mach_msg_type_number_t(capacity)
        var pageSize: vm_size_t = 0

        let host = mach_host_self()
        defer { mach_port_deallocate(mach_task_self_, host) }

        guard host_page_size(host, &pageSize) == KERN_SUCCESS, pageSize > 0 else { return nil }
        let result = withUnsafeMutablePointer(to: &statistics) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: capacity) {
                host_statistics64(host, HOST_VM_INFO64, $0, &count)
            }
        }
        guard result == KERN_SUCCESS else { return nil }

        let total = ProcessInfo.processInfo.physicalMemory
        guard total > 0 else { return nil }
        let pageBytes = UInt64(pageSize)
        let internalPages = UInt64(statistics.internal_page_count)
        let purgeablePages = UInt64(statistics.purgeable_count)
        let appPages = internalPages > purgeablePages ? internalPages - purgeablePages : 0

        let rawApp = appPages * pageBytes
        let rawWired = UInt64(statistics.wire_count) * pageBytes
        let rawCompressed = UInt64(statistics.compressor_page_count) * pageBytes

        // Clamp defensively so category totals cannot exceed physical RAM.
        var remaining = total
        let app = min(rawApp, remaining); remaining -= app
        let wired = min(rawWired, remaining); remaining -= wired
        let compressed = min(rawCompressed, remaining); remaining -= compressed
        let available = remaining
        return MemorySnapshot(
            availableBytes: available,
            appBytes: app,
            wiredBytes: wired,
            compressedBytes: compressed
        )
    }
}

private final class MemoryColorDotView: NSView {
    var color: NSColor = .green { didSet { needsDisplay = true } }

    override func draw(_ dirtyRect: NSRect) {
        color.setFill()
        NSBezierPath(ovalIn: bounds.insetBy(dx: 0.25, dy: 0.25)).fill()
    }
}

/// Native popover tooltip with fixed 128-point width and four same-color dots.
private final class MemoryTooltipViewController: NSViewController {
    private var valueFields: [NSTextField] = []
    private let rowLabels = ["可用内存：", "App 内存：", "联动内存：", "压缩内存："]
    private let rowColors = [
        StatusbarLayout.availableColor,
        StatusbarLayout.appMemoryColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.compressedColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 128, height: 88))
        for index in 0..<4 {
            let rowY = CGFloat(66 - index * 19)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 1, width: 7, height: 7))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let field = NSTextField(labelWithString: "")
            field.frame = NSRect(x: 20, y: rowY - 3, width: 101, height: 16)
            field.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            field.textColor = NSColor.labelColor
            field.lineBreakMode = .byTruncatingTail
            content.addSubview(field)
            valueFields.append(field)
        }
        view = content
    }

    func update(snapshot: MemorySnapshot) {
        // Accessing view triggers lazy loading and is compatible with macOS 10.13.
        _ = self.view
        let values = [snapshot.availableGB, snapshot.appGB, snapshot.wiredGB, snapshot.compressedGB]
        for index in 0..<min(valueFields.count, values.count) {
            let newText = rowLabels[index] + String(format: "%.1fG", values[index])
            if valueFields[index].stringValue != newText {
                valueFields[index].stringValue = newText
            }
        }
    }
}

// END statusbar-fan-memory patch (2026-10-22)


fileprivate class StatusbarView: NSView {
    var meanFreq: Float = 0
    var maxFreq: Float = 0
    var temp: Float = 0
    var pwr: Float = 0
    private var memorySnapshot = MemorySnapshot.zero

    var normalLabel: [NSAttributedString.Key: NSObject]?
    var compactLabel: [NSAttributedString.Key: NSObject]?
    var normalValue: [NSAttributedString.Key: NSObject]?
    var compactValue: [NSAttributedString.Key: NSObject]?

    private var fanIndicatorView: FanIndicatorView?
    private var memoryPopover: NSPopover?
    private var memoryTooltipController: MemoryTooltipViewController?
    private var memoryTrackingArea: NSTrackingArea?
    private var hoveringMemoryPie = false
    private var previousFanTemperature: Float?

    func setup() {
        let compactLineHeight: CGFloat = 6
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.minimumLineHeight = compactLineHeight
        paragraphStyle.maximumLineHeight = compactLineHeight

        compactLabel = [
            .font: NSFont(name: "Monaco", size: 7)!,
            .foregroundColor: NSColor.labelColor,
            .paragraphStyle: paragraphStyle
        ]
        normalValue = [
            .font: NSFont.systemFont(ofSize: 14, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]
        compactValue = [
            .font: NSFont.systemFont(ofSize: 10, weight: .semibold),
            .foregroundColor: NSColor.labelColor
        ]
        normalLabel = [
            .font: NSFont.systemFont(ofSize: 12, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]

        let fan = FanIndicatorView(frame: NSRect(
            x: StatusbarLayout.fanX, y: 0,
            width: StatusbarLayout.fanSize, height: StatusbarLayout.fanSize
        ))
        fanIndicatorView = fan
        addSubview(fan)

        let tooltipController = MemoryTooltipViewController(nibName: nil, bundle: nil)
        let popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 128, height: 88)
        popover.contentViewController = tooltipController
        memoryTooltipController = tooltipController
        memoryPopover = popover
        tooltipController.update(snapshot: memorySnapshot)
    }

    override func layout() {
        super.layout()
        fanIndicatorView?.frame = NSRect(
            x: StatusbarLayout.fanX,
            y: max(0, (bounds.height - StatusbarLayout.fanSize) / 2.0),
            width: StatusbarLayout.fanSize,
            height: StatusbarLayout.fanSize
        )
        fanIndicatorView?.needsLayout = true
        refreshMemoryTrackingArea()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        refreshMemoryTrackingArea()
    }

    private var memoryPieRect: NSRect {
        NSRect(
            x: StatusbarLayout.memoryPieX,
            y: max(0, (bounds.height - StatusbarLayout.memoryPieSize) / 2.0),
            width: StatusbarLayout.memoryPieSize,
            height: StatusbarLayout.memoryPieSize
        )
    }

    private func refreshMemoryTrackingArea() {
        if let oldArea = memoryTrackingArea {
            removeTrackingArea(oldArea)
            memoryTrackingArea = nil
        }
        guard bounds.height >= StatusbarLayout.memoryPieSize else { return }
        let area = NSTrackingArea(
            rect: memoryPieRect,
            options: [.mouseEnteredAndExited, .activeAlways],
            owner: self,
            userInfo: nil
        )
        memoryTrackingArea = area
        addTrackingArea(area)
    }

    override func mouseEntered(with event: NSEvent) {
        guard let area = memoryTrackingArea, event.trackingArea === area else {
            super.mouseEntered(with: event)
            return
        }
        hoveringMemoryPie = true
        memoryTooltipController?.update(snapshot: memorySnapshot)
        if let popover = memoryPopover, !popover.isShown {
            popover.show(relativeTo: memoryPieRect, of: self, preferredEdge: .minY)
        }
    }

    override func mouseExited(with event: NSEvent) {
        guard let area = memoryTrackingArea, event.trackingArea === area else {
            super.mouseExited(with: event)
            return
        }
        hoveringMemoryPie = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) { [weak self] in
            guard let self = self, !self.hoveringMemoryPie else { return }
            if let popover = self.memoryPopover, popover.isShown {
                popover.performClose(nil)
            }
        }
    }

    func closeMemoryTooltip() {
        hoveringMemoryPie = false
        if let popover = memoryPopover, popover.isShown {
            popover.performClose(nil)
        }
    }

    func updateMetrics(meanFreq: Float, maxFreq: Float, temperature: Float, power: Float,
                       memory: MemorySnapshot?) {
        self.meanFreq = meanFreq
        self.maxFreq = maxFreq
        self.temp = temperature
        self.pwr = power
        if let memory = memory {
            memorySnapshot = memory
            memoryTooltipController?.update(snapshot: memory)
        }

        if let previous = previousFanTemperature {
            if previous != temperature {
                let crossed = (previous > StatusbarLayout.fanTemperatureThreshold)
                    != (temperature > StatusbarLayout.fanTemperatureThreshold)
                fanIndicatorView?.updateTemperature(temperature, crossedThreshold: crossed)
                previousFanTemperature = temperature
            }
        } else {
            fanIndicatorView?.setInitialTemperature(temperature)
            previousFanTemperature = temperature
        }
        setNeedsDisplay(bounds)
    }

    override func draw(_ dirtyRect: NSRect) {
        guard NSGraphicsContext.current?.cgContext != nil else { return }

        let averageFrequencyGHz = meanFreq * 0.001
        let maximumFrequencyGHz = maxFreq * 0.001
        let averageFrequency = String(format: "%.1f", averageFrequencyGHz)
        let maximumFrequency = String(format: "%.1f", maximumFrequencyGHz)

        // The fan replaces the former CPU text label. CPU values start six points
        // after the 16-point fan, and keep the original top/bottom arrangement.
        drawDoubleCompactValue(
            up: "\(maximumFrequency)ᴳ",
            down: "\(averageFrequency)ᴳ",
            x: StatusbarLayout.cpuValueX,
            upColor: maximumFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor,
            downColor: averageFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

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
            valueColor: pwr > StatusbarLayout.powerThreshold ? StatusbarLayout.highlightColor : .labelColor,
            rightAligned: true,
            valueWidth: StatusbarLayout.powerValueWidth
        )

        drawMemoryPie()
        drawMemoryValues()
    }

    private func drawMemoryPie() {
        let rect = memoryPieRect
        let center = NSPoint(x: rect.midX, y: rect.midY)
        let radius = min(rect.width, rect.height) / 2.0
        let pieces: [(UInt64, NSColor)] = [
            (memorySnapshot.availableBytes, StatusbarLayout.availableColor),
            (memorySnapshot.appBytes, StatusbarLayout.appMemoryColor),
            (memorySnapshot.wiredBytes, StatusbarLayout.wiredColor),
            (memorySnapshot.compressedBytes, StatusbarLayout.compressedColor)
        ]
        let total = pieces.reduce(UInt64(0)) { $0 + $1.0 }
        guard total > 0 else {
            StatusbarLayout.availableColor.setFill()
            NSBezierPath(ovalIn: rect).fill()
            return
        }

        var startAngle: CGFloat = 90.0
        for (bytes, color) in pieces where bytes > 0 {
            let sweep = CGFloat(Double(bytes) / Double(total) * 360.0)
            let endAngle = startAngle - sweep
            let startRadians = startAngle * CGFloat.pi / 180.0
            let path = NSBezierPath()
            path.move(to: center)
            path.line(to: NSPoint(
                x: center.x + cos(startRadians) * radius,
                y: center.y + sin(startRadians) * radius
            ))
            path.appendArc(
                withCenter: center,
                radius: radius,
                startAngle: startAngle,
                endAngle: endAngle,
                clockwise: true
            )
            path.close()
            color.setFill()
            path.fill() // intentionally no black outline/stroke
            startAngle = endAngle
        }
    }

    private func drawMemoryValues() {
        var attributes = compactValue ?? [:]
        attributes[.foregroundColor] = NSColor.labelColor
        let available = String(format: "%.1fG", memorySnapshot.availableGB)
        let used = String(format: "%.1fG", memorySnapshot.usedGB)
        drawRightAlignedValue(available, x: StatusbarLayout.memoryValueX,
                              y: StatusbarLayout.frequencyTopY,
                              width: StatusbarLayout.memoryValueWidth, attributes: attributes)
        drawRightAlignedValue(used, x: StatusbarLayout.memoryValueX,
                              y: StatusbarLayout.frequencyBottomY,
                              width: StatusbarLayout.memoryValueWidth, attributes: attributes)
    }

    private func drawRightAlignedValue(_ text: String, x: CGFloat, y: CGFloat,
                                       width: CGFloat,
                                       attributes: [NSAttributedString.Key: NSObject]) {
        let measuredWidth = (text as NSString).size(withAttributes: attributes).width
        NSAttributedString(string: text, attributes: attributes).draw(
            at: NSPoint(x: x + max(0, width - measuredWidth), y: y)
        )
    }

    private func drawVerticalLabel(_ label: String, x: CGFloat) {
        let attributedLabel = NSAttributedString(string: label, attributes: compactLabel)
        attributedLabel.draw(in: NSRect(
            x: x,
            y: StatusbarLayout.labelOriginY,
            width: StatusbarLayout.labelWidth,
            height: bounds.height
        ))
    }

    private func drawDoubleCompactValue(up: String, down: String, x: CGFloat,
                                        upColor: NSColor = .labelColor,
                                        downColor: NSColor = .labelColor) {
        var upperAttributes = compactValue ?? [:]
        upperAttributes[.foregroundColor] = upColor
        NSAttributedString(string: up, attributes: upperAttributes).draw(
            at: NSPoint(x: x, y: StatusbarLayout.frequencyTopY)
        )
        var lowerAttributes = compactValue ?? [:]
        lowerAttributes[.foregroundColor] = downColor
        NSAttributedString(string: down, attributes: lowerAttributes).draw(
            at: NSPoint(x: x, y: StatusbarLayout.frequencyBottomY)
        )
    }

    private func drawCompactSingle(label: String, value: String, x: CGFloat,
                                   valueColor: NSColor = .labelColor,
                                   rightAligned: Bool = false,
                                   valueWidth: CGFloat = 0) {
        drawVerticalLabel(label, x: x)
        var attributes = normalValue ?? [:]
        attributes[.foregroundColor] = valueColor
        if rightAligned {
            let valueX = x + StatusbarLayout.metricValueOffsetX
            let measuredWidth = (value as NSString).size(withAttributes: attributes).width
            NSAttributedString(string: value, attributes: attributes).draw(
                at: NSPoint(x: valueX + max(0, valueWidth - measuredWidth),
                            y: StatusbarLayout.valueOriginY)
            )
        } else {
            NSAttributedString(string: value, attributes: attributes).draw(
                at: NSPoint(x: x + StatusbarLayout.metricValueOffsetX,
                            y: StatusbarLayout.valueOriginY)
            )
        }
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

        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { [weak self] _ in
            self?.update()
        })
        update()
    }

    func dismiss() {
        updateTimer?.invalidate()
        updateTimer = nil
        view?.closeMemoryTooltip()
        if let item = statusItem {
            NSStatusBar.system.removeStatusItem(item)
        }
        statusItem = nil
        view = nil
    }

    func update() {
        let model = ProcessorModel.shared
        let numberOfCores = model.getNumOfCore()
        guard numberOfCores > 0 else { return }
        let outputStr = model.getMetric(forced: false)
        guard outputStr.count > numberOfCores + 2 else { return }

        let power = outputStr[0]
        let temperature = outputStr[1]
        var frequencies: [Float] = []
        for index in 0..<numberOfCores {
            frequencies.append(outputStr[index + 3])
        }
        guard !frequencies.isEmpty, let maximum = frequencies.max() else { return }
        let mean = frequencies.reduce(0, +) / Float(frequencies.count)

        // Exactly one memory sample per existing one-second update; no second timer.
        let memory = MemorySampler.sample()
        view?.updateMetrics(
            meanFreq: mean,
            maxFreq: maximum,
            temperature: temperature,
            power: power,
            memory: memory
        )
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
