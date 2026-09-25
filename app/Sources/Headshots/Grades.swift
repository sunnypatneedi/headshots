import SwiftUI

enum GradeStyle {
    static func color(_ grade: String) -> Color {
        switch grade {
        case "PASS": return .green
        case "REVIEW": return .orange
        case "SKIPPED": return .secondary
        default: return .red
        }
    }

    static func shortLabel(_ grade: String) -> String {
        switch grade {
        case "PASS": return "PASS"
        case "REVIEW": return "REVIEW"
        case "FAIL": return "FAIL"
        case "SKIPPED": return "SKIP"
        default: return grade
        }
    }
}

struct GradeBadge: View {
    let grade: String

    var body: some View {
        Text(GradeStyle.shortLabel(grade))
            .font(.caption2.weight(.bold))
            .tracking(0.3)
            .foregroundStyle(GradeStyle.color(grade))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(GradeStyle.color(grade).opacity(0.14))
            )
            .accessibilityHidden(true)
    }
}

struct GradeChip: View {
    let grade: String
    let count: Int

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(GradeStyle.color(grade))
                .frame(width: 7, height: 7)
            Text("\(count) \(grade.lowercased())")
                .font(.caption.weight(.medium))
                .foregroundStyle(.primary)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(
            Capsule(style: .continuous)
                .fill(GradeStyle.color(grade).opacity(0.14))
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(count) \(grade)")
    }
}
