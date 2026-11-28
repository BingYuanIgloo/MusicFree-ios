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

        // 播放状态一变就处理灵动岛：暂停/停止时结束活动（否则歌词岛
        // 在音频关掉后还一直挂着），恢复播放时用最新进度重新同步
        // （纠正进度条漂移）。没有这个监听，歌词岛只在行变化时才动。
        RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {
            if (state === State.Paused || state === State.Stopped) {
                endLyricsLiveActivity();
            } else if (state === State.Playing) {
                this.syncLiveActivity();
            }
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
        const formatLine = (item: IParsedLrcItem | null | undefined) =>
            (item?.lrc ?? "") +
            (showTranslation && item?.translation
                ? `\n${item.translation}`
                : "");

        const currentLine = formatLine(currentLyricItem);
        const items = this.lyricParser?.getLyricItems() ?? [];
        const nextLine = formatLine(items[currentLyricItem.index + 1]);

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

        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，
        // 且失败后下次行变化会重新 start，不会像 update 分支那样永久卡死。
        startLyricsLiveActivity(
            musicItem.title,
            musicItem.artist,
            currentLine,
            nextLine,
            startedAtMs,
            durationSec,
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
    }

    private setLyricAsNoLyricState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: false,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
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
