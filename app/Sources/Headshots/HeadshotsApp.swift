import SwiftUI

@main
struct HeadshotsApp: App {
    var body: some Scene {
        WindowGroup("Headshots") {
            ContentView()
        }
        .windowResizability(.contentMinSize)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}
