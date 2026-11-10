import SwiftUI

@main
struct HeadshotsApp: App {
    var body: some Scene {
        WindowGroup("Headshots") {
            ContentView()
        }
        .windowStyle(.automatic)
        .windowToolbarStyle(.unifiedCompact(showsTitle: true))
        .windowResizability(.contentMinSize)
        .defaultSize(width: 680, height: 620)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
