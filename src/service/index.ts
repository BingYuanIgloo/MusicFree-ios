import Config from "@/core/appConfig";
import RNTrackPlayer, { Event, State } from "react-native-track-player";
import TrackPlayer from "@/core/trackPlayer";
import { musicIsPaused } from "@/utils/trackUtils";
import PersistStatus from "@/utils/persistStatus";
import getOrCreateMMKV from "@/utils/getOrCreateMMKV";
import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";

let resumeState: State | null;
module.exports = async function () {
    RNTrackPlayer.addEventListener(Event.RemotePlay, () => TrackPlayer.play());
    RNTrackPlayer.addEventListener(Event.RemotePause, () =>
        TrackPlayer.pause(),
    );
    RNTrackPlayer.addEventListener(Event.RemotePrevious, () =>
        TrackPlayer.skipToPrevious(),
    );
    RNTrackPlayer.addEventListener(Event.RemoteNext, () =>
        TrackPlayer.skipToNext(),
    );
    RNTrackPlayer.addEventListener(
        Event.RemoteDuck,
        async ({ paused, permanent }) => {
            if (Config.getConfig("basic.notInterrupt")) {
                return;
            }
            if (permanent) {
                return TrackPlayer.pause();
            }
            const tempRemoteDuckConf = Config.getConfig(
                "basic.tempRemoteDuck",
            );
            if (tempRemoteDuckConf === "lowerVolume") {
                if (paused) {
                    const tempRemoteDuckVolume = Config.getConfig(
                        "basic.tempRemoteDuckVolume",
                    ) ?? 0.5;
                    return RNTrackPlayer.setVolume(1 - tempRemoteDuckVolume);
                } else {
                    return RNTrackPlayer.setVolume(1);
                }
            } else {
                if (paused) {
                    resumeState =
                        (await RNTrackPlayer.getPlaybackState()).state ??
                        State.Paused;
                    return TrackPlayer.pause();
                } else {
                    if (resumeState && !musicIsPaused(resumeState)) {
                        resumeState = null;
                        return TrackPlayer.play();
                    }
                    resumeState = null;
                }
            }
        },
    );


    // 后台歌词同步：主线程切后台会被挂起，歌词行就停在原地。
    // 这里是 headless service，后台也能收到进度事件，按进度算当前
    // 行推给灵动岛。歌词数据由主线程写进 lyric.liveActivity MMKV。
    // 行没变就不推，省更新预算。
    const headlessLyricStore = getOrCreateMMKV("lyric.liveActivity");
    let lastHeadlessLyricLine = "";
    // 上次成功推岛的时间。歌词行很久不变（前奏/间奏长）时也要定期
    // 推一次，只为把活动的过期时间往后推，不然 2 分钟无更新活动
    // 就过期，灵动岛会把岛收掉，只剩锁屏横幅。
    let lastHeadlessPushTime = 0;
    const HEADLESS_HEARTBEAT_MS = 45000;
    const headlessSyncLyric = (position: number, duration: number) => {
        try {
            const raw = headlessLyricStore.getString("current");
            if (!raw) {
                return;
            }
            const data = JSON.parse(raw) as {
                title?: string;
                artist?: string;
                offset?: number;
                items?: Array<{
                    time: number;
                    lrc: string;
                    translation?: string;
                }>;
            };
            const items = data.items ?? [];
            if (!items.length) {
                return;
            }
            const pos = position - (data.offset ?? 0);
            if (pos < items[0].time) {
                return;
            }
            let current = items[0];
            for (let i = 0; i < items.length; i++) {
                if (items[i].time <= pos) {
                    current = items[i];
                } else {
                    break;
                }
            }
            const line = current.lrc ?? "";
            const now = Date.now();
            const lineChanged = !!line && line !== lastHeadlessLyricLine;
            const heartbeatDue =
                now - lastHeadlessPushTime >= HEADLESS_HEARTBEAT_MS;
            if (!line || (!lineChanged && !heartbeatDue)) {
                return;
            }
            lastHeadlessLyricLine = line;
            lastHeadlessPushTime = now;
            const idx = items.indexOf(current);
            const next = items[idx + 1]?.lrc ?? "";
            // 走 start：原生侧已有活动就更新，没有就新建，
            // 后台也能把岛拉起来，不依赖主线程。
            startLyricsLiveActivity(
                data.title ?? "",
                data.artist ?? "",
                line,
                next,
                Date.now() - position * 1000,
                duration,
                true,
            );
        } catch {
            // 解析失败就跳过，不影响播放。
        }
    };

    // 切歌：后台也立即收掉旧歌的岛、清掉行记录，不然新歌还没取到
    // 歌词之前，后台会拿着旧歌的 items 按新歌进度继续推，歌词和
    // 进度条都跟着上一首走；切到无歌词的源时旧歌词也会赖着不走。
    RNTrackPlayer.addEventListener(Event.PlaybackActiveTrackChanged, () => {
        lastHeadlessLyricLine = "";
        lastHeadlessPushTime = 0;
        endLyricsLiveActivity();
    });

    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });

    // 播完 / 队列结束：后台也收掉灵动岛，不然锁屏留一首卡在最后的歌。
    RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {
        if (state === State.Stopped) {
            lastHeadlessLyricLine = "";
            endLyricsLiveActivity();
        }
    });
    RNTrackPlayer.addEventListener(Event.PlaybackQueueEnded, () => {
        lastHeadlessLyricLine = "";
        endLyricsLiveActivity();
    });

    RNTrackPlayer.addEventListener(Event.RemoteStop, async () => {
        RNTrackPlayer.stop();
    });

    RNTrackPlayer.addEventListener(Event.RemoteSeek, async evt => {
        TrackPlayer.seekTo(evt.position);
    });
};
