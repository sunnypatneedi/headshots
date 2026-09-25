// Runs the bundled `headshots` command and turns its output into events on the main actor.
//
// The command lives inside the app bundle (Contents/Resources/bin/headshots). If it is missing -
// which happens when you build the app without building the command first - we say so plainly
// instead of failing silently.

import Foundation

@MainActor
final class Runner: ObservableObject {
    @Published var running = false
    @Published var done = 0
    @Published var total = 0
    @Published var photos: [Event.Photo] = []
    @Published var polished: Event.Polished?
    @Published var grouped: Event.Grouped?
    @Published var lines: [String] = []
    @Published var failure: String?
    /// Output folder from the `start` / `polished` events — gallery tiles resolve `photo.output` here.
    @Published var outDir: String?

    private var process: Process?
    private var userCancelled = false

    static var toolURL: URL? {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("bin/headshots")
        if let bundled, FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        // A developer build: fall back to whatever `headshots` is on PATH.
        for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
            let p = URL(fileURLWithPath: dir).appendingPathComponent("headshots")
            if FileManager.default.isExecutableFile(atPath: p.path) { return p }
        }
        return nil
    }

    func cancel() {
        userCancelled = true
        process?.terminate()
        process = nil
        running = false
        failure = "Polishing was cancelled."
    }

    /// Clear results so the window returns to the Select step (new folder / polish again from scratch).
    func resetResults() {
        if running {
            userCancelled = true
            process?.terminate()
            process = nil
            running = false
            // Leave userCancelled set until terminationHandler runs, so SIGTERM stderr is ignored.
        } else {
            userCancelled = false
        }
        photos = []
        lines = []
        polished = nil
        grouped = nil
        failure = nil
        outDir = nil
        done = 0
        total = 0
    }

    func run(folder: URL, options: Options) {
        guard let tool = Runner.toolURL else {
            failure = "The headshots command is missing from this app. Build it with `make app`, "
                + "or install it with `pipx install headshots`."
            return
        }
        photos = []; lines = []; polished = nil; grouped = nil; failure = nil; outDir = nil
        done = 0; total = 0; running = true; userCancelled = false

        let task = Process()
        task.executableURL = tool
        task.arguments = ["--json"] + options.arguments(folder: folder)
        let out = Pipe(), err = Pipe()
        task.standardOutput = out
        task.standardError = err
        process = task

        // Stream stdout line by line so the window fills in as the work happens.
        Task.detached {
            var buffer = Data()
            let handle = out.fileHandleForReading
            while let chunk = try? handle.read(upToCount: 4096), !chunk.isEmpty {
                buffer.append(chunk)
                while let nl = buffer.firstIndex(of: UInt8(ascii: "\n")) {
                    let line = String(decoding: buffer[..<nl], as: UTF8.self)
                    buffer.removeSubrange(...nl)
                    if let event = Event.decode(line) {
                        await MainActor.run { self.apply(event) }
                    }
                }
            }
        }

        task.terminationHandler = { finished in
            let stderr = String(decoding: err.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            Task { @MainActor in
                self.running = false
                self.process = nil
                if self.userCancelled {
                    // cancel() already set a clear message; do not overwrite with SIGTERM noise.
                    self.userCancelled = false
                    return
                }
                // Exit code 1 just means at least one photo graded FAIL, which is a result, not an error.
                if finished.terminationStatus > 1 {
                    self.failure = stderr.isEmpty ? "The command stopped unexpectedly." : stderr
                } else {
                    self.hydrateGalleryIfNeeded()
                }
            }
        }

        do { try task.run() } catch {
            failure = error.localizedDescription
            running = false
        }
    }

    private func apply(_ event: Event) {
        switch event {
        case let .start(total, _, out):
            self.total = total
            self.outDir = out
        case let .photo(p):
            photos.append(p)
            done += 1
        case let .polished(p):
            polished = p
            outDir = p.out
            hydrateGalleryIfNeeded()
        case let .grouped(g):
            grouped = g
        case let .log(text):
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { lines.append(trimmed) }
        }
    }

    /// Defense in depth: older CLIs skipped `photo` events on full cache hits. Read `_report.json`
    /// (or scan polished JPEGs) so the gallery still has tiles.
    private func hydrateGalleryIfNeeded() {
        guard photos.isEmpty else { return }
        let dir = outDir ?? polished?.out
        guard let dir else { return }

        if let report = PolishedReport.load(from: dir), !report.photos.isEmpty {
            photos = report.photos.map { $0.asPhoto() }
            done = photos.count
            if total < photos.count { total = photos.count }
            return
        }

        let folder = URL(fileURLWithPath: dir)
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: folder,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return }

        let jpgs = files.filter { url in
            let name = url.lastPathComponent
            guard name.lowercased().hasSuffix(".jpg") || name.lowercased().hasSuffix(".jpeg") else { return false }
            return !name.hasPrefix("_")
        }
        .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }

        guard !jpgs.isEmpty else { return }
        photos = jpgs.map { url in
            Event.Photo(
                source: url.lastPathComponent,
                grade: "PASS",
                reasons: [],
                notes: ["Loaded from polished folder"],
                output: url.lastPathComponent
            )
        }
        done = photos.count
        if total < photos.count { total = photos.count }
    }
}

struct Options {
    enum Shape: String, CaseIterable, Identifiable {
        case fourFive = "4:5", twoThree = "2:3", square = "1:1"
        var id: String { rawValue }
        var label: String {
            switch self {
            case .fourFive: return "4:5 — standard headshot"
            case .twoThree: return "2:3 — taller, prints at 4×6"
            case .square: return "1:1 — square"
            }
        }
    }

    var shape: Shape = .fourFive
    var width = 1600
    var zoom = 1.0
    var blackAndWhite = false
    var groupByPerson = true

    func arguments(folder: URL) -> [String] {
        var a = [groupByPerson ? "run" : "polish", folder.path,
                 "--ratio", shape.rawValue,
                 "--width", String(width),
                 "--zoom", String(format: "%.2f", zoom)]
        a.append(blackAndWhite ? "--bw" : "--no-bw")
        return a
    }
}
