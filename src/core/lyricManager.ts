import { IAppConfig } from "@/types/core/config";
import { ITrackPlayer } from "@/types/core/trackPlayer";
import { IInjectable } from "@/types/infra";
import LyricParser, { IParsedLrcItem } from "@/utils/lrcParser";
import { getMediaExtraProperty, patchMediaExtra } from "@/utils/mediaExtra";
import { isSameMediaItem } from "@/utils/mediaUtils";
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
import RNTrackPlayer, { Event } from "react-native-track-player";
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

        this.refreshLyric(true);
    }

    /**
     * 把当前歌词行同步到灵动岛 / 锁屏 Live Activity。
     * 开关关着、没在播、无歌词行、系统关了 Live Activities 时，
     * 结束活动（如果有）。设置页和歌词面板的开关也调这个方法，
     * 这样开关当时就能立即生效，不用等下一行歌词。
     */
    syncLiveActivity() {
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

        const startedAtMs =
            Date.now() - (this.lastProgress.position || 0) * 1000;
        const durationSec = this.lastProgress.duration || 0;

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

            // 如果源不存在，恢复默认设置
            if (!lrcSource) {
                this.setLyricAsNoLyricState();
                this.lyricParser = null;
                return;
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
