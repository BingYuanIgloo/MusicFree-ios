import { NativeModules, Platform } from "react-native";
import {
    getIosBasicMeta,
    getIosMediaCoverImg,
    getIosMediaLyric,
    getIosMediaMeta,
} from "@/utils/iosMediaMeta";

export interface IBasicMeta {
    album?: string;
    artist?: string;
    author?: string;
    duration?: string;
    title?: string;
}

export interface IWritableMeta extends IBasicMeta {
    lyric?: string;
    comment?: string;
}

interface IMp3Util {
    getBasicMeta: (fileName: string) => Promise<IBasicMeta>;
    getMediaMeta: (fileNames: string[]) => Promise<IBasicMeta[]>;
    getMediaCoverImg: (mediaPath: string) => Promise<string>;
    /** 读取内嵌歌词 */
    getLyric: (mediaPath: string) => Promise<string>;
    /** 写入meta信息 */
    setMediaTag: (filePath: string, meta: IWritableMeta) => Promise<void>;
    getMediaTag: (filePath: string) => Promise<IWritableMeta>;
}

const NativeMp3Util = NativeModules.Mp3Util as IMp3Util | undefined;

// iOS 没有 Mp3Util 原生模块：用纯 JS 解析 ID3/FLAC/MP4 标签代替
// （Android 走原生模块，不受影响）
const iosMp3Util: IMp3Util = {
    getBasicMeta: getIosBasicMeta,
    getMediaMeta: getIosMediaMeta,
    getMediaCoverImg: getIosMediaCoverImg,
    getLyric: getIosMediaLyric,
    // iOS 暂不支持写入标签
    setMediaTag: async () => {},
    getMediaTag: async () => ({}),
};

const Mp3Util: IMp3Util =
    NativeMp3Util ??
    (Platform.OS === "ios" ? iosMp3Util : ({} as IMp3Util));

export default Mp3Util;
