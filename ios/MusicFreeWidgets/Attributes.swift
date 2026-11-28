import ActivityKit
import WidgetKit
import SwiftUI

/// Live Activity 的数据模型：歌词上灵动岛 / 锁屏。
///
/// 静态属性（开始时确定，活动期间不变）：歌名、歌手。
/// 动态状态（行变化时更新）：当前行、下一行、歌曲开始时间、总时长。
/// 全部内容保持在 4 KB 以内：只传文字，不传图片。
struct LyricsLiveActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        /// 当前歌词行（空字符串表示当前无歌词行）
        var currentLine: String
        /// 下一行歌词（可为空）
        var nextLine: String
        /// 歌曲开始播放的墙钟时间（用于锁屏进度条自己走）
        var startedAt: Date
        /// 歌曲总时长（秒）
        var duration: TimeInterval
        /// 是否正在播放（决定播放按钮显示播放还是暂停图标）
        var isPlaying: Bool
    }

    /// 歌名
    var title: String
    /// 歌手
    var artist: String
}
