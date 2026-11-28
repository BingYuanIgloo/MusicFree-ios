import ActivityKit
import WidgetKit
import SwiftUI

/// 歌词 Live Activity 的 Widget（锁屏横幅 + 灵动岛）。
///
/// 布局规则（照 DriveVerse / montyp0x 的经验）：
/// 锁屏和灵动岛用同一套固定视图树，行变化时只换字符串，不用
/// if / ViewThatFits / .id，系统自己做交叉淡入淡出，避免行切换时闪烁。
/// 单岛模式：歌词岛就是播放器，长按展开页和锁屏横幅都带播放按钮
///（上一首 / 播放暂停 / 下一首），经 URL Scheme 回调主 App。
/// 不再清系统 Now Playing：清掉它会把锁屏媒体卡也清空
///（只剩空播放框）。歌词岛本身就是唯一的岛。
@main
struct MusicFreeWidgetsBundle: WidgetBundle {
    var body: some Widget {
        LyricsLiveActivity()
    }
}

struct LyricsLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: LyricsLiveActivityAttributes.self) { context in
            // MARK: - 锁屏横幅
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(context.attributes.title)
                        .font(.system(size: 14, weight: .bold))
                        .lineLimit(1)
                    Text(context.attributes.artist)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text(context.state.currentLine)
                    .font(.system(size: 18, weight: .semibold))
                    .lineLimit(2)
                Text(context.state.nextLine)
                    .font(.system(size: 13))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                ProgressView(
                    timerInterval: context.state.startedAt...progressEnd(
                        startedAt: context.state.startedAt,
                        duration: context.state.duration),
                    countsDown: false
                )
                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
                // 回主 App（见 liveActivityLinking.ts），不直接操作音频。
                // 居中（QQ/网易云式）：按钮组占满整行宽度再居中，
                // 否则 HStack 跟着外层 leading 对齐，全挤在左边。
                HStack(spacing: 32) {
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/previous")!) {
                        Image(systemName: "backward.fill")
                            .font(.system(size: 18))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/playpause")!) {
                        Image(systemName: context.state.isPlaying ? "pause.fill" : "play.fill")
                            .font(.system(size: 22))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/next")!) {
                        Image(systemName: "forward.fill")
                            .font(.system(size: 18))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)
            }
            .padding(12)
            .activityBackgroundTint(.black.opacity(0.35))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.attributes.title)
                            .font(.system(size: 14, weight: .bold))
                            .lineLimit(1)
                        Text(context.attributes.artist)
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Image(systemName: "music.note")
                        .font(.system(size: 20))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.currentLine)
                            .font(.system(size: 16, weight: .semibold))
                            .lineLimit(2)
                        Text(context.state.nextLine)
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
                // 回主 App（见 liveActivityLinking.ts），不直接操作音频。
                // 居中（QQ/网易云式）：按钮组占满整行宽度再居中。
                HStack(spacing: 32) {
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/previous")!) {
                        Image(systemName: "backward.fill")
                            .font(.system(size: 18))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/playpause")!) {
                        Image(systemName: context.state.isPlaying ? "pause.fill" : "play.fill")
                            .font(.system(size: 22))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/next")!) {
                        Image(systemName: "forward.fill")
                            .font(.system(size: 18))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)
                    }
                }
            } compactLeading: {
                Image(systemName: "music.note")
            } compactTrailing: {
                Text(context.attributes.title)
                    .lineLimit(1)
            } minimal: {
                Image(systemName: "music.note")
            }
            .keylineTint(.white)
        }
    }

    /// 进度条的结束时间。duration 为 0（未知时长）时给 1 秒，
    /// 避免空区间导致进度条异常；下一行更新会带上真实时长。
    private func progressEnd(startedAt: Date, duration: TimeInterval) -> Date {
        startedAt.addingTimeInterval(max(duration, 1))
    }
}

struct LyricsLiveActivityPreviews: PreviewProvider {
    static let attributes = LyricsLiveActivityAttributes(
        title: "晴天", artist: "周杰伦")
    static let contentState = LyricsLiveActivityAttributes.ContentState(
        currentLine: "故事的小黄花 从出生那年就飘着",
        nextLine: "童年的荡秋千 随记忆一直晃到现在",
        startedAt: Date(), duration: 269, isPlaying: true)

    static var previews: some View {
        attributes
            .previewContext(contentState, viewKind: .content)
            .previewDisplayName("Lock Screen")
        attributes
            .previewContext(contentState, viewKind: .dynamicIsland(.compact))
            .previewDisplayName("Island Compact")
        attributes
            .previewContext(contentState, viewKind: .dynamicIsland(.expanded))
            .previewDisplayName("Island Expanded")
        attributes
            .previewContext(contentState, viewKind: .dynamicIsland(.minimal))
            .previewDisplayName("Minimal")
    }
}
