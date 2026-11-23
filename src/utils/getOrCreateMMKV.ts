import pathConst from "@/constants/pathConst";
import { MMKV } from "react-native-mmkv";

const _mmkvCache: Record<string, MMKV> = {};

// @ts-ignore;
global.mmkv = _mmkvCache;

// 内存兜底: 原生 MMKV 初始化失败时 (如 native module 未正确加载),
// 用内存实现顶替, 保证应用能启动 (设置不持久化, 但不白屏)。
// 仅实现代码库实际用到的 MMKV 方法。
function createMemoryMMKV(dbName: string): MMKV {
    const store = new Map<string, string | number | boolean>();
    const listeners = new Set<(key: string) => void>();
    const notify = (key: string) => {
        listeners.forEach(fn => {
            try {
                fn(key);
            } catch { /* ignore listener errors */ }
        });
    };
    const shim = {
        id: dbName,
        getString: (key: string) => {
            const v = store.get(key);
            return typeof v === "string" ? v : undefined;
        },
        getNumber: (key: string) => {
            const v = store.get(key);
            return typeof v === "number" ? v : undefined;
        },
        getBoolean: (key: string) => {
            const v = store.get(key);
            return typeof v === "boolean" ? v : undefined;
        },
        getBuffer: () => undefined,
        set: (key: string, value: string | number | boolean) => {
            store.set(key, value);
            notify(key);
        },
        contains: (key: string) => store.has(key),
        delete: (key: string) => {
            store.delete(key);
            notify(key);
        },
        getAllKeys: () => [...store.keys()],
        clearAll: () => {
            store.clear();
        },
        addOnValueChangedListener: (fn: (key: string) => void) => {
            listeners.add(fn);
            return { remove: () => listeners.delete(fn) };
        },
    };
    return shim as unknown as MMKV;
}

// Internal Method
const getOrCreateMMKV = (dbName: string, cachePath = false) => {
    if (_mmkvCache[dbName]) {
        return _mmkvCache[dbName];
    }

    let newStore: MMKV;
    try {
        newStore = new MMKV({
            id: dbName,
            path: cachePath ? pathConst.mmkvCachePath : pathConst.mmkvPath,
        });
    } catch (e) {
        // 原生 MMKV 失败绝不能让模块加载崩掉 (否则整应用白屏):
        // 记日志, 降级为内存实现继续跑
        console.warn(`[MMKV] native init failed for "${dbName}", using in-memory fallback:`, e);
        newStore = createMemoryMMKV(dbName);
    }

    _mmkvCache[dbName] = newStore;
    return newStore;
};

export default getOrCreateMMKV;
