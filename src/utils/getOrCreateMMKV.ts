import pathConst from "@/constants/pathConst";
import { createMMKV, type MMKV } from "react-native-mmkv";

const _mmkvCache: Record<string, MMKV> = {};

// @ts-ignore;
global.mmkv = _mmkvCache;

// Internal Method
const getOrCreateMMKV = (dbName: string, cachePath = false) => {
    if (_mmkvCache[dbName]) {
        return _mmkvCache[dbName];
    }

    // MMKV 4.x：构造函数 new MMKV() 已移除，改用 createMMKV()（其余用法不变：
    // id / path 配置、contains / getString / set / remove 均与 2.x 兼容）。
    const newStore = createMMKV({
        id: dbName,
        path: cachePath ? pathConst.mmkvCachePath : pathConst.mmkvPath,
    });

    _mmkvCache[dbName] = newStore;
    return newStore;
};

export default getOrCreateMMKV;
