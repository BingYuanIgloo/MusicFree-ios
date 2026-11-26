import ExpoModulesCore
import ActivityKit

/// 暴露给 JS 的原生模块（react-native-widget-extension 的 Module.swift）。
///
/// 注意：这个文件**不**编译进 MusicFreeWidgets 扩展目标；
/// 构建流程会把它连同 Attributes.swift 一起拷到
/// node_modules/react-native-widget-extension/ios/，由
/// ReactNativeWidgetExtension 这个 pod 编进主 App（见 podspec 的
/// source_files）。JS 侧通过 expo-modules-core 的
/// requireNativeModule("ReactNativeWidgetExtension") 调用它，
/// 不直接 import npm 包，这样包还没装好时 App 也能正常启动
///（模块缺失时 JS 侧静默 no-op）。
///
/// JS 侧的调用约定（src/core/liveActivityLyrics.ts）：
///   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec)
///   updateActivity(currentLine, nextLine, startedAtMs, durationSec)
///   endActivity()
///   areActivitiesEnabled() -> Bool
public class ReactNativeWidgetExtensionModule: Module {
    public func definition() -> ModuleDefinition {
        Name("ReactNativeWidgetExtension")

        Function("areActivitiesEnabled") { () -> Bool in
            if #available(iOS 16.2, *) {
                return ActivityAuthorizationInfo().areActivitiesEnabled
            } else {
                return false
            }
        }

        Function("startActivity") {
            (
                title: String,
                artist: String,
                currentLine: String,
                nextLine: String,
                startedAtMs: Double,
                durationSec: Double
            ) -> Bool in
            if #available(iOS 16.2, *) {
                let startedAt = Date(timeIntervalSince1970: startedAtMs / 1000)
                let attributes = LyricsLiveActivityAttributes(
                    title: title,
                    artist: artist
                )
                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    nextLine: nextLine,
                    startedAt: startedAt,
                    duration: max(durationSec, 0)
                )
                // 30 分钟后标记为过期：App 异常退出时系统能及时收起活动。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 30, to: Date()
                )
                let activityContent = ActivityContent(
                    state: contentState, staleDate: staleDate)

                // 同一时间只保留一个歌词活动：如果已存在，先更新它而不是再开一个。
                let existing = Activity<LyricsLiveActivityAttributes>.activities
                if let activity = existing.first {
                    Task {
                        await activity.update(activityContent)
                    }
                    return true
                }

                do {
                    let activity = try Activity.request(
                        attributes: attributes, content: activityContent)
                    print("[LyricsLiveActivity] started \(activity.id)")
                    return true
                } catch {
                    print("[LyricsLiveActivity] start failed: \(error)")
                    return false
                }
            } else {
                return false
            }
        }

        Function("updateActivity") {
            (
                currentLine: String,
                nextLine: String,
                startedAtMs: Double,
                durationSec: Double
            ) -> Void in
            if #available(iOS 16.2, *) {
                let startedAt = Date(timeIntervalSince1970: startedAtMs / 1000)
                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    nextLine: nextLine,
                    startedAt: startedAt,
                    duration: max(durationSec, 0)
                )
                let updatedContent = ActivityContent(
                    state: contentState, staleDate: nil)

                Task {
                    for activity in Activity<LyricsLiveActivityAttributes>.activities {
                        await activity.update(updatedContent)
                    }
                }
            }
        }

        Function("endActivity") { () -> Void in
            if #available(iOS 16.2, *) {
                Task {
                    for activity in Activity<LyricsLiveActivityAttributes>.activities {
                        await activity.end(nil, dismissalPolicy: .default)
                    }
                }
            }
        }
    }
}
