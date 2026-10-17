// Named role tokens for the Mac window.
// Components use these roles only — no raw hex or ad-hoc opacity in views.
// Shared numbers live in app/preview/tokens.json so contrast tests stay honest.

import AppKit
import SwiftUI

enum HSTheme {
    // MARK: Spacing & radius

    enum Space {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
    }

    enum Radius {
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let pill: CGFloat = 999
    }

    /// Motion budgets. Frequent controls stay ≤120ms; panel changes ≤220ms. Never above 300ms.
    enum Motion {
        static let instant: Double = 0.08
        static let control: Double = 0.12
        static let panel: Double = 0.22
        static let max: Double = 0.30
    }

    // MARK: Role colours (adaptive)

    static let canvas = Color(light: Token.canvasLight, dark: Token.canvasDark)
    static let surface = Color(light: Token.surfaceLight, dark: Token.surfaceDark)
    static let surfaceMuted = Color(light: Token.surfaceMutedLight, dark: Token.surfaceMutedDark)
    static let ink = Color(light: Token.inkLight, dark: Token.inkDark)
    static let inkSecondary = Color(light: Token.inkSecondaryLight, dark: Token.inkSecondaryDark)
    static let border = Color(light: Token.borderLight, dark: Token.borderDark)
    static let borderStrong = Color(light: Token.borderStrongLight, dark: Token.borderStrongDark)
    static let accent = Color(light: Token.accentLight, dark: Token.accentDark)
    static let accentSoft = Color(light: Token.accentSoftLight, dark: Token.accentSoftDark)
    static let accentOn = Color(light: Token.accentOnLight, dark: Token.accentOnDark)
    static let success = Color(light: Token.successLight, dark: Token.successDark)
    static let successSoft = Color(light: Token.successSoftLight, dark: Token.successSoftDark)
    static let warning = Color(light: Token.warningLight, dark: Token.warningDark)
    static let danger = Color(light: Token.dangerLight, dark: Token.dangerDark)
    static let dangerSoft = Color(light: Token.dangerSoftLight, dark: Token.dangerSoftDark)
    static let focusRing = Color(light: Token.focusLight, dark: Token.focusDark)
    static let dropTarget = Color(light: Token.dropTargetLight, dark: Token.dropTargetDark)

    /// Hard-coded sRGB values mirrored in tokens.json (source of truth for contrast tests).
    enum Token {
        static let canvasLight = RGB(0.973, 0.976, 0.980)
        static let canvasDark = RGB(0.110, 0.110, 0.118)
        static let surfaceLight = RGB(1, 1, 1)
        static let surfaceDark = RGB(0.173, 0.173, 0.180)
        static let surfaceMutedLight = RGB(0.949, 0.953, 0.961)
        static let surfaceMutedDark = RGB(0.220, 0.220, 0.231)
        static let inkLight = RGB(0.110, 0.110, 0.118)
        static let inkDark = RGB(0.957, 0.957, 0.965)
        static let inkSecondaryLight = RGB(0.420, 0.435, 0.463)
        static let inkSecondaryDark = RGB(0.655, 0.667, 0.698)
        static let borderLight = RGB(0.863, 0.875, 0.890)
        static let borderDark = RGB(0.310, 0.318, 0.341)
        static let borderStrongLight = RGB(0.780, 0.796, 0.820)
        static let borderStrongDark = RGB(0.400, 0.412, 0.439)
        static let accentLight = RGB(0.145, 0.388, 0.922)
        static let accentDark = RGB(0.353, 0.549, 0.980)
        static let accentSoftLight = RGB(0.898, 0.925, 0.988)
        static let accentSoftDark = RGB(0.180, 0.255, 0.420)
        static let accentOnLight = RGB(1, 1, 1)
        static let accentOnDark = RGB(0.070, 0.090, 0.160)
        static let successLight = RGB(0.086, 0.471, 0.227)
        static let successDark = RGB(0.345, 0.800, 0.522)
        static let successSoftLight = RGB(0.890, 0.965, 0.918)
        static let successSoftDark = RGB(0.145, 0.255, 0.196)
        static let warningLight = RGB(0.804, 0.435, 0.110)
        static let warningDark = RGB(0.953, 0.643, 0.290)
        static let dangerLight = RGB(0.780, 0.180, 0.220)
        static let dangerDark = RGB(0.980, 0.455, 0.478)
        static let dangerSoftLight = RGB(0.988, 0.910, 0.918)
        static let dangerSoftDark = RGB(0.290, 0.145, 0.165)
        static let focusLight = RGB(0.145, 0.388, 0.922)
        static let focusDark = RGB(0.525, 0.690, 1.0)
        static let dropTargetLight = RGB(0.898, 0.925, 0.988)
        static let dropTargetDark = RGB(0.180, 0.255, 0.420)
    }

    struct RGB {
        let r, g, b: Double
        init(_ r: Double, _ g: Double, _ b: Double) { self.r = r; self.g = g; self.b = b }
        var color: Color { Color(.sRGB, red: r, green: g, blue: b, opacity: 1) }
    }
}

enum HSTypography {
    static let brand = Font.system(size: 17, weight: .semibold)
    static let brandTag = Font.system(size: 12, weight: .regular)
    static let title = Font.system(size: 22, weight: .semibold)
    static let headline = Font.system(size: 15, weight: .semibold)
    static let body = Font.system(size: 14, weight: .regular)
    static let callout = Font.system(size: 13, weight: .regular)
    static let caption = Font.system(size: 12, weight: .regular)
    static let label = Font.system(size: 12, weight: .semibold)
}

extension Color {
    init(light: HSTheme.RGB, dark: HSTheme.RGB) {
        self.init(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let rgb = isDark ? dark : light
            return NSColor(srgbRed: rgb.r, green: rgb.g, blue: rgb.b, alpha: 1)
        })
    }
}

extension Animation {
    static func hsControl(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : .easeOut(duration: HSTheme.Motion.control)
    }

    static func hsPanel(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : .easeInOut(duration: HSTheme.Motion.panel)
    }
}
