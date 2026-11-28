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
                durationSec: Double,
                isPlaying: Bool
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
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 2 分钟后标记为过期：App 被杀掉后灵动岛很快消失；
                // 活着时每次歌词更新都会把过期时间往后推，不会误杀。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 2, to: Date()
                )
                let activityContent = ActivityContent(
                    state: contentState, staleDate: staleDate)

                // 同一时间只保留一个歌词活动：如果已存在且是同一首歌，
                // 直接更新它；换歌了则结束旧活动重开（歌名/歌手存在活动
                // 属性里，update 改不了，不重开岛上一直是上一首的歌，
                // 歌词却是新歌的，岛和锁屏就“打架”）。
                let existing = Activity<LyricsLiveActivityAttributes>.activities
                if let activity = existing.first {
                    if activity.attributes.title == title &&
                        activity.attributes.artist == artist {
                        Task {
                            await activity.update(activityContent)
                        }
                        return true
                    }
                    Task {
                        await activity.end(nil, dismissalPolicy: .immediate)
                    }
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
                durationSec: Double,
                isPlaying: Bool
            ) -> Void in
            if #available(iOS 16.2, *) {
                let startedAt = Date(timeIntervalSince1970: startedAtMs / 1000)
                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    nextLine: nextLine,
                    startedAt: startedAt,
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 更新也带 2 分钟过期时间：App 被杀掉后不再更新，
                // 活动很快过期消失；活着时下次更新会续期。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 2, to: Date()
                )
                let updatedContent = ActivityContent(
                    state: contentState, staleDate: staleDate)

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
                        // .immediate：结束时锁屏横幅立刻消失。.default 会把
                        // 锁屏横幅留下来当通知，用户看到的就是“歌词放完了
                        // 还显示在锁屏上，关不掉”。
                        await activity.end(nil, dismissalPolicy: .immediate)
                    }
                }
            }
        }
    }
}
