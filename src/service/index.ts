import RNTrackPlayer, { registerRemoteHandlers } from "@rntp/player";
import TrackPlayer from "@/core/trackPlayer";

/**
 * 后台播放会话（v5 的 registerPlaybackSession 替代 v4 的 registerPlaybackService）。
 *
 * 注意：这里注册的处理器必须在函数开头的同步部分完成（第一个 await 之前），
 * 这样它们在无界面冷启动（headless）时也存在。
 */
module.exports = async function () {
    // v5：Remote* 事件已废弃（6.0 删除），改用 registerRemoteHandlers。
    // play / pause / next / previous / stop / seek 六个处理器；
    // 通知栏 / 锁屏上出现哪些按钮，由 bootstrap 里 setCommands 的
    // capabilities 列表决定。
    registerRemoteHandlers({
        play: () => TrackPlayer.play(),
        pause: () => TrackPlayer.pause(),
        next: () => TrackPlayer.skipToNext(),
        previous: () => TrackPlayer.skipToPrevious(),
        stop: () => RNTrackPlayer.stop(),
        seek: command => TrackPlayer.seekTo(command.position),
    });

    // v5 没有 RemoteDuck：临时降低音量 / 暂停后恢复的自定义逻辑没有等价物。
    // 中断（来电、其他 App 抢音频焦点）现在由原生层处理（暂停；结束后按系统
    // 行为恢复）。设置里的 basic.notInterrupt / basic.tempRemoteDuck /
    // basic.tempRemoteDuckVolume 从此不起作用（后续可隐藏这几项设置）。
    //
    // 原来这里还有一个 PlaybackProgressUpdated 监听（把进度写进
    // PersistStatus 供下次恢复用）；v5 里那个事件不再定期触发，
    // 改由 lyricManager 的进度轮询统一写 PersistStatus。
};
