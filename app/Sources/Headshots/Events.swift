// What the `headshots --json` command sends back, one JSON object per line.
//
// The command line and this app run exactly the same code; the app is a window over it. If a
// field here ever disagrees with the tool, the tool is right - see src/headshots/events.py.

import Foundation

enum Event {
    case start(total: Int, unchanged: Int, out: String)
    case photo(Photo)
    case polished(Polished)
    case grouped(Grouped)
    case log(String)

    struct Photo: Decodable, Identifiable {
        let source: String
        let grade: String
        let reasons: [String]
        let notes: [String]
        let output: String?
        var id: String { source }
        var why: String { (reasons + notes).joined(separator: "; ") }
    }

    struct Polished: Decodable {
        let processed: Int
        let unchanged: Int
        let counts: [String: Int]
        let flagged: Int
        let setNote: String?
        let sheet: String
        let pages: Int
        let out: String

        enum CodingKeys: String, CodingKey {
            case processed, unchanged, counts, flagged, sheet, pages, out
            case setNote = "set_note"
        }
    }

    struct Grouped: Decodable {
        let students: Int
        let photos: Int
        let threshold: Double
        let why: String
        let groups: [Group]
        let report: String
        let sheets: [String]

        struct Group: Decodable, Identifiable {
            let id: String
            let photos: [String]
            let pick: String
        }
    }

    /// Decode one line. Unknown or malformed lines are ignored rather than fatal: a future version
    /// of the tool may send events this build has never heard of.
    static func decode(_ line: String) -> Event? {
        guard let data = line.data(using: .utf8),
              let head = try? JSONDecoder().decode(Kind.self, from: data) else { return nil }
        switch head.event {
        case "start":
            let s = try? JSONDecoder().decode(Start.self, from: data)
            return s.map { .start(total: $0.total, unchanged: $0.unchanged, out: $0.out) }
        case "photo":
            return (try? JSONDecoder().decode(Photo.self, from: data)).map(Event.photo)
        case "polished":
            return (try? JSONDecoder().decode(Polished.self, from: data)).map(Event.polished)
        case "grouped":
            return (try? JSONDecoder().decode(Grouped.self, from: data)).map(Event.grouped)
        case "log":
            return (try? JSONDecoder().decode(Log.self, from: data)).map { .log($0.text) }
        default:
            return nil
        }
    }

    private struct Kind: Decodable { let event: String }
    private struct Start: Decodable { let total: Int; let unchanged: Int; let out: String }
    private struct Log: Decodable { let text: String }
}
