import { IAppConfig } from "@/types/core/config";
import { ITrackPlayer } from "@/types/core/trackPlayer";
import { IInjectable } from "@/types/infra";
import LyricParser, { IParsedLrcItem } from "@/utils/lrcParser";
import { getMediaExtraProperty, patchMediaExtra } from "@/utils/mediaExtra";
import { getMediaUniqueKey, isSameMediaItem } from "@/utils/mediaUtils";
import getOrCreateMMKV from "@/utils/getOrCreateMMKV";
import minDistance from "@/utils/minDistance";
import { atom, getDefaultStore, useAtomValue } from "jotai";
import { Plugin } from "./pluginManager";

import pathConst from "@/constants/pathConst";
import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";
import { checkAndCreateDir } from "@/utils/fileUtils";
import PersistStatus from "@/utils/persistStatus";
import CryptoJs from "crypto-js";
import { unlink, writeFile } from "react-native-fs";
import { AppState } from "react-native";
import RNTrackPlayer, { Event, State } from "react-native-track-player";
import { TrackPlayerEvents } from "@/core.defination/trackPlayer";
import { IPluginManager } from "@/types/core/pluginManager";


interface ILyricState {
    loading: boolean;
    lyrics: IParsedLrcItem[];
    hasTranslation: boolean;
    meta?: Record<string, string>;
}

const defaultLyricState = {
    loading: true,
    lyrics: [],
    hasTranslation: false,
};

const lyricStateAtom = atom<ILyricState>(defaultLyricState);
const currentLyricItemAtom = atom<IParsedLrcItem | null>(null);

// 歌词兜底缓存：某首歌一旦成功加载过歌词，就把 rawLrc + 翻译
// 持久化在这里（MMKV，key 是 platform@id）。以后插件偶尔取不到
// 歌词时，用这个兜底顶上，不让已经显示过的歌词凭空消失。
const fallbackLyricStore = getOrCreateMMKV("lyric.fallbackCache");

// 灵动岛后台同步用的歌词数据（MMKV，headless service 也能读）。
// 主线程在歌词解析好后把当前歌的 items + 标题/作者/偏移写进来，
// 后台 service 按进度算当前行推给灵动岛（主线程切后台会被挂起，
// 歌词行就停在原地不动）。无歌词时清掉，避免后台推旧歌词。
const liveActivityLyricStore = getOrCreateMMKV("lyric.liveActivity");

function loadFallbackLyric(
    musicItem: IMusic.IMusicItem,
): ILyric.ILyricSource | null {
    try {
        const raw = fallbackLyricStore.getString(
            getMediaUniqueKey(musicItem),
        );
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw) as {
            rawLrc?: string;
            translation?: string;
        };
        if (!parsed.rawLrc && !parsed.translation) {
            return null;
        }
        return {
            rawLrc: parsed.rawLrc,
            translation: parsed.translation,
        };
    } catch {
        return null;
    }
}

function saveFallbackLyric(
    musicItem: IMusic.IMusicItem,
    rawLrc?: string | null,
    translation?: string | null,
): void {
    try {
        if (!rawLrc && !translation) {
            return;
        }
        fallbackLyricStore.set(
            getMediaUniqueKey(musicItem),
            JSON.stringify({
                rawLrc: rawLrc ?? null,
                translation: translation ?? null,
            }),
        );
    } catch {
        // 兜底缓存写失败不影响歌词显示。
    }
}


class LyricManager implements IInjectable {

    private trackPlayer!: ITrackPlayer;
    private appConfig!: IAppConfig;
    private pluginManager!: IPluginManager;

    private lyricParser: LyricParser | null = null;

    /** 最近一次进度事件的位置/总时长（用来算灵动岛进度条的开始时间）。 */
    private lastProgress = { position: 0, duration: 0 };
    // 最近一次播放状态（供歌词岛播放按钮图标用）。
    private lastPlaybackPlaying = false;


    get currentLyricItem() {
        return getDefaultStore().get(currentLyricItemAtom);
    }

    get lyricState() {
        return getDefaultStore().get(lyricStateAtom);
    }

    injectDependencies(trackPlayerService: ITrackPlayer, appConfigService: IAppConfig, pluginManager: IPluginManager): void {
        this.trackPlayer = trackPlayerService;
        this.appConfig = appConfigService;
        this.pluginManager = pluginManager;
    }

    setup() {
        // 更新歌词
        this.trackPlayer.on(TrackPlayerEvents.CurrentMusicChanged, (musicItem) => {
            this.refreshLyric(true, true);
        });

        RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
            this.lastProgress = {
                position: evt.position ?? 0,
                duration: evt.duration ?? this.lastProgress.duration,
            };
            const parser = this.lyricParser;
            if (!parser || !this.trackPlayer.isCurrentMusic(parser.musicItem)) {
                return;
            }

            const currentLyricItem = getDefaultStore().get(currentLyricItemAtom);
            const newLyricItem = parser.getPosition(evt.position);


            if (currentLyricItem?.lrc !== newLyricItem?.lrc) {
                // 更新当前歌词状态
                getDefaultStore().set(currentLyricItemAtom, newLyricItem ?? null);
            }
        });

        // 歌词行一变就同步一次灵动岛（currentLyricItemAtom 只在行文本
        // 变化时更新，所以这里天然就是“行变化才推”，不会每秒都推）。
        getDefaultStore().sub(currentLyricItemAtom, () => {
            this.syncLiveActivity();
        });

        // 播放状态一变就处理灵动岛（单岛模式：歌词岛就是播放器）。
        // 暂停时岛留着（显示暂停态，点播放可恢复）；停止时才结束
        // 活动。每次都重同步一次，让播放按钮图标跟着状态翻。
        RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {
            if (state === State.Stopped) {
                this.lastPlaybackPlaying = false;
                endLyricsLiveActivity();
            } else if (state === State.Playing) {
                this.lastPlaybackPlaying = true;
                this.syncLiveActivity();
            } else if (state === State.Paused) {
                this.lastPlaybackPlaying = false;
                // 暂停在曲末（进度已到时长）：这首已经播完，不是中途暂停，
                // 岛留着就是“没播也有歌词条”。直接收掉；中途暂停不受影响。
                const pos = this.lastProgress.position || 0;
                const dur = this.lastProgress.duration || 0;
                if (dur > 0 && pos >= dur - 1.5) {
                    endLyricsLiveActivity();
                    return;
                }
                this.syncLiveActivity();
            }
        });

        // 播完最后一首（队列结束）也要收掉灵动岛，不然锁屏会留一首
        // 卡在最后的歌；再重播时旧活动还占着，歌词就推不出来了。
        RNTrackPlayer.addEventListener(Event.PlaybackQueueEnded, () => {
            endLyricsLiveActivity();
        });

        // 回到前台时用最新进度重新同步一次（打开软件歌词不刷新的根因：
        // 之前只有行变化才推，切回来时行没变就不推，显示就停在旧进度）。
        AppState.addEventListener("change", (nextState) => {
            if (nextState === "active") {
                this.syncLiveActivity();
            }
        });

        this.refreshLyric(true);
    }

    /**
     * 把当前歌词行同步到灵动岛 / 锁屏 Live Activity。
     * 开关关着、没在播、无歌词行、系统关了 Live Activities 时，
     * 结束活动（如果有）。设置页和歌词面板的开关也调这个方法，
     * 这样开关当时就能立即生效，不用等下一行歌词。
     */
    async syncLiveActivity() {
        if (!this.appConfig.getConfig("lyric.showStatusBarLyric")) {
            endLyricsLiveActivity();
            return;
        }
        const musicItem = this.trackPlayer.currentMusic;
        const currentLyricItem = getDefaultStore().get(currentLyricItemAtom);
        if (!musicItem || !currentLyricItem) {
            endLyricsLiveActivity();
            return;
        }
        // 不再用 areActivitiesEnabled() 挡门：系统开关关着时原生
        // Activity.request 会直接失败（已在原生侧捕获打印），
        // 开关开着时这里必须放行，不能因授权查询返回 false 就
        // 静默跳过，否则歌词永远推不到灵动岛。
        const showTranslation = PersistStatus.get("lyric.showTranslation");
        // 主句 / 翻译分开传给灵动岛（岛上分两行、不同字号显示）。
        // 有独立 translation 字段的直接用；没有的按首个中文字符切。
        const splitItem = (item: IParsedLrcItem | null | undefined) => {
            const lrc = item?.lrc ?? "";
            const trans = showTranslation ? (item?.translation ?? null) : null;
            if (trans) {
                return { main: lrc, trans };
            }
            const chars = [...lrc];
            const idx = chars.findIndex(ch => /[\u4e00-\u9fff]/.test(ch));
            if (idx <= 0) {
                return { main: lrc, trans: "" };
            }
            return {
                main: chars.slice(0, idx).join("").trim(),
                trans: chars.slice(idx).join("").trim(),
            };
        };

        const cur = splitItem(currentLyricItem);
        const items = this.lyricParser?.getLyricItems() ?? [];
        const nxt = splitItem(items[currentLyricItem.index + 1]);
        const currentLine = cur.main;
        const currentLineTrans = cur.trans;
        const nextLine = nxt.main;
        const nextLineTrans = nxt.trans;

        // 用实时进度算 startedAt，不要用缓存的 lastProgress：缓存只在
        // 进度事件里更新，暂停/切歌/切后台后就 stale，歌词进度条会和
        // 音频进度条对不上（锁屏上一个 1:41 一个 2:25 就是这么来的）。
        let position = this.lastProgress.position || 0;
        let durationSec = this.lastProgress.duration || 0;
        try {
            const progress = await RNTrackPlayer.getProgress();
            if (typeof progress?.position === "number") {
                position = progress.position;
            }
            if (typeof progress?.duration === "number") {
                durationSec = progress.duration;
            }
        } catch {
            // 拿不到实时进度就用缓存，不阻塞歌词显示。
        }
        const startedAtMs = Date.now() - position * 1000;

        // 不再清系统 Now Playing：清掉它会把锁屏媒体卡也清空
        //（只剩一个空播放框，没有封面/歌名）。歌词岛本身就是
        // 唯一的岛（原生 startActivity 只更新已有活动，不再新建）。

        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，
        // 且失败后下次行变化会重新 start，不会像 update 分支那样永久卡死。
        startLyricsLiveActivity(
            musicItem.title,
            musicItem.artist,
            currentLine,
            currentLineTrans,
            nextLine,
            nextLineTrans,
            startedAtMs,
            durationSec,
            this.lastPlaybackPlaying,
        );
    }

    associateLyric(musicItem: IMusic.IMusicItem, linkToMusicItem: ICommon.IMediaBase) {
        if (!musicItem || !linkToMusicItem) {
            return false;
        }

        // 如果当前音乐项和关联的音乐项相同，则不需要重新关联
        if (isSameMediaItem(musicItem, linkToMusicItem)) {
            patchMediaExtra(musicItem, {
                associatedLrc: undefined,
            });
            return false;
        } else {
            patchMediaExtra(musicItem, {
                associatedLrc: linkToMusicItem,
            });
            if (this.trackPlayer.isCurrentMusic(musicItem)) {
                this.refreshLyric(false);
            }
            return true;
        }
    }

    unassociateLyric(musicItem: IMusic.IMusicItem) {
        if (!musicItem) {
            return;
        }

        patchMediaExtra(musicItem, {
            associatedLrc: undefined,
        });

        if (this.trackPlayer.isCurrentMusic(musicItem)) {
            this.refreshLyric(false);
        }
    }

    async uploadLocalLyric(musicItem: IMusic.IMusicItem, lyricContent: string, type: "raw" | "translation" = "raw") {
        if (!musicItem) {
            return;
        }

        const platformHash = CryptoJs.MD5(musicItem.platform).toString(
            CryptoJs.enc.Hex,
        );
        const idHash: string = CryptoJs.MD5(musicItem.id).toString(
            CryptoJs.enc.Hex,
        );

        // 检查是否缓存文件夹存在
        await checkAndCreateDir(pathConst.localLrcPath + platformHash);
        await writeFile(pathConst.localLrcPath +
            platformHash +
            "/" +
            idHash +
            (type === "raw" ? "" : ".tran") +
            ".lrc", lyricContent, "utf8");

        if (this.trackPlayer.isCurrentMusic(musicItem)) {
            this.refreshLyric(false, false);
        }
    }

    async removeLocalLyric(musicItem: IMusic.IMusicItem) {
        if (!musicItem) {
            return;
        }

        const platformHash = CryptoJs.MD5(musicItem.platform).toString(
            CryptoJs.enc.Hex,
        );
        const idHash: string = CryptoJs.MD5(musicItem.id).toString(
            CryptoJs.enc.Hex,
        );

        const basePath =
            pathConst.localLrcPath + platformHash + "/" + idHash;

        await unlink(basePath + ".lrc").catch(() => { });
        await unlink(basePath + ".tran.lrc").catch(() => { });

        if (this.trackPlayer.isCurrentMusic(musicItem)) {
            this.refreshLyric(false, false);
        }

    }


    updateLyricOffset(musicItem: IMusic.IMusicItem, offset: number) {
        if (!musicItem) {
            return;
        }

        // 更新歌词偏移
        patchMediaExtra(musicItem, {
            lyricOffset: offset,
        });

        if (this.trackPlayer.isCurrentMusic(musicItem)) {
            this.refreshLyric(true, false);
        }
    }

    private setLyricAsLoadingState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: true,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
        // 切歌瞬间就清掉后台同步用的歌词数据：不然 headless service
        // 在新歌词还没取回来之前，会拿着旧歌的 items 按新歌的进度
        // 继续推灵动岛，歌词进度条就跟着上一首走、切到无歌词的源
        // 时旧歌词也赖着不走。
        try {
            liveActivityLyricStore.delete("current");
        } catch {
            // 清不掉也不影响主流程
        }
    }

    private setLyricAsNoLyricState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: false,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
        try {
            liveActivityLyricStore.delete("current");
        } catch {
            // 清不掉也不影响主流程
        }
    }

    private async refreshLyric(skipFetchLyricSourceIfSame: boolean = true, ignoreProgress: boolean = false) {
        const currentMusicItem = this.trackPlayer.currentMusic;

        // 如果没有当前音乐项，重置歌词状态
        if (!currentMusicItem) {
            this.setLyricAsNoLyricState();
            return;
        }

        try {
            let lrcSource: ILyric.ILyricSource | null;

            if (skipFetchLyricSourceIfSame && this.lyricParser && this.trackPlayer.isCurrentMusic(this.lyricParser.musicItem)) {
                lrcSource = this.lyricParser.lyricSource ?? null;
            } else {
                // 重置歌词状态
                this.setLyricAsLoadingState();

                lrcSource = (await this.pluginManager.getByMedia(currentMusicItem)?.methods?.getLyric(currentMusicItem)) ?? null;
            }

            // 切换到其他歌曲了, 直接返回
            if (!this.trackPlayer.isCurrentMusic(currentMusicItem)) {
                return;
            }

            // 如果歌词源不存在，并且开启自动搜索歌词
            if (!lrcSource && this.appConfig.getConfig("lyric.autoSearchLyric")) {
                // 重置歌词状态
                this.setLyricAsLoadingState();

                lrcSource = await this.searchSimilarLyric(currentMusicItem);
            }

            // 切换到其他歌曲了, 直接返回
            if (!this.trackPlayer.isCurrentMusic(currentMusicItem)) {
                return;
            }

            // 如果源不存在，先试试兜底：这首歌上次成功加载过的歌词。
            // 插件偶尔取不到歌词时，不要把已经显示过的歌词清掉；
            // 只有兜底也没有时，才恢复成无歌词状态。
            if (!lrcSource) {
                const fallback = loadFallbackLyric(currentMusicItem);
                if (fallback) {
                    lrcSource = fallback;
                } else if (
                    this.lyricParser &&
                    this.trackPlayer.isCurrentMusic(
                        this.lyricParser.musicItem,
                    ) &&
                    this.lyricParser.getLyricItems().length > 0
                ) {
                    // 内存里还有这首歌的好歌词（强制重取失败时），留着继续显示。
                    return;
                } else {
                    this.setLyricAsNoLyricState();
                    this.lyricParser = null;
                    return;
                }
            }

            this.lyricParser = new LyricParser(lrcSource.rawLrc!, {
                extra: {
                    offset: (getMediaExtraProperty(currentMusicItem, "lyricOffset") || 0) * -1,
                },
                musicItem: currentMusicItem,
                lyricSource: lrcSource,
                translation: lrcSource.translation,
            });

            getDefaultStore().set(lyricStateAtom, {
                loading: false,
                lyrics: this.lyricParser.getLyricItems(),
                hasTranslation: !!lrcSource.translation,
                meta: this.lyricParser.getMeta(),
            });

            // 记下来：这首歌的歌词成功加载过。以后插件取不到时，
            // 用这个兜底顶上，不让歌词凭空消失。
            saveFallbackLyric(
                currentMusicItem,
                lrcSource.rawLrc,
                lrcSource.translation,
            );

            const currentLyric = ignoreProgress ? (this.lyricParser.getLyricItems()?.[0] ?? null) : this.lyricParser.getPosition((await this.trackPlayer.getProgress()).position);
            getDefaultStore().set(currentLyricItemAtom, currentLyric || null);

            // 写一份给后台 service：歌词行 + 标题/作者/偏移，
            // 供后台按进度推灵动岛。
            try {
                liveActivityLyricStore.set(
                    "current",
                    JSON.stringify({
                        title: currentMusicItem.title,
                        artist: currentMusicItem.artist,
                        offset: this.lyricParser.getMeta()?.offset ?? 0,
                        items: this.lyricParser.getLyricItems().map((it) => ({
                            time: it.time,
                            lrc: it.lrc,
                            translation: it.translation ?? "",
                        })),
                    }),
                );
            } catch {
                // 写失败不影响主流程
            }
        } catch (err) {
            if (this.trackPlayer.isCurrentMusic(currentMusicItem)) {
                this.lyricParser = null;
                this.setLyricAsNoLyricState();
            }
        }
    }

    /**
     * 检索最接近的歌词
     * @param musicItem 
     * @returns 
     */
    private async searchSimilarLyric(musicItem: IMusic.IMusicItem) {
        const keyword = musicItem.alias || musicItem.title;
        const plugins = this.pluginManager.getSearchablePlugins("lyric");

        let distance = Infinity;
        let minDistanceMusicItem;
        let targetPlugin: Plugin | null = null;

        for (let plugin of plugins) {
            // 如果插件不是当前音乐的插件，或者当前音乐不是正在播放的音乐，则跳过
            if (
                !this.trackPlayer.isCurrentMusic(musicItem)
            ) {
                return null;
            }

            if (plugin.name === musicItem.platform) {
                // 如果插件是当前音乐的插件，则跳过
                continue;
            }

            const results = await plugin.methods
                .search(keyword, 1, "lyric")
                .catch(() => null);

            // 取前两个
            const firstTwo = results?.data?.slice(0, 2) || [];

            for (let item of firstTwo) {
                if (
                    item.title === keyword &&
                    item.artist === musicItem.artist
                ) {
                    distance = 0;
                    minDistanceMusicItem = item;
                    targetPlugin = plugin;
                    break;
                } else {
                    const dist =
                        minDistance(keyword, musicItem.title) +
                        minDistance(item.artist, musicItem.artist);
                    if (dist < distance) {
                        distance = dist;
                        minDistanceMusicItem = item;
                        targetPlugin = plugin;
                    }
                }
            }

            if (distance === 0) {
                break;
            }
        }

        if (minDistanceMusicItem && targetPlugin) {
            return await targetPlugin.methods
                .getLyric(minDistanceMusicItem)
                .catch(() => null);
        }

        return null;
    }

}

const lyricManager = new LyricManager();
export default lyricManager;


export const useLyricState = () => useAtomValue(lyricStateAtom);
export const useCurrentLyricItem = () => useAtomValue(currentLyricItemAtom);
