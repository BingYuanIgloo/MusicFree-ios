import pathConst from "@/constants/pathConst";
import { createMMKV, type MMKV } from "react-native-mmkv";

const _mmkvCache: Record<string, MMKV> = {};

let _mmkvFallback = false;
/** 原生 MMKV 不可用时是否已降级为内存存储（数据不持久化，仅当次有效） */
export function isMMKVFallback() {
    return _mmkvFallback;
}

// @ts-ignore;
global.mmkv = _mmkvCache;

/**
 * 内存版 MMKV（与 react-native-mmkv 4.x 常用接口一致）：
 * 原生模块加载失败时兜底，保证 App 能启动；数据仅保存在内存，重启后丢失。
 */
type MMKVListener = (key: string) => void;
class MemoryMMKV {
    readonly id: string;
    private store = new Map<string, string | number | boolean | Uint8Array>();
    private listeners = new Set<MMKVListener>();

    constructor(id: string) {
        this.id = id;
    }

    private emit(key: string) {
        this.listeners.forEach(fn => {
            try {
                fn(key);
            } catch {}
        });
    }

    contains(key: string) {
        return this.store.has(key);
    }
    getString(key: string) {
        const v = this.store.get(key);
        return typeof v === "string" ? v : undefined;
    }
    setString(key: string, value: string) {
        this.store.set(key, value);
        this.emit(key);
    }
    getNumber(key: string) {
        const v = this.store.get(key);
        return typeof v === "number" ? v : undefined;
    }
    setNumber(key: string, value: number) {
        this.store.set(key, value);
        this.emit(key);
    }
    getBoolean(key: string) {
        const v = this.store.get(key);
        return typeof v === "boolean" ? v : undefined;
    }
    setBoolean(key: string, value: boolean) {
        this.store.set(key, value);
        this.emit(key);
    }
    getBuffer(key: string) {
        const v = this.store.get(key);
        return v instanceof Uint8Array ? v : undefined;
    }
    setBuffer(key: string, value: Uint8Array) {
        this.store.set(key, value);
        this.emit(key);
    }
    set(key: string, value: string | number | boolean | Uint8Array) {
        this.store.set(key, value);
        this.emit(key);
    }
    delete(key: string) {
        this.store.delete(key);
        this.emit(key);
    }
    remove(key: string) {
        this.delete(key);
    }
    clear() {
        this.store.clear();
    }
    getAllKeys() {
        return [...this.store.keys()];
    }
    addOnValueChangedListener(listener: MMKVListener) {
        this.listeners.add(listener);
        return () => {
            this.listeners.delete(listener);
        };
    }
    removeOnValueChangedListener(listener: MMKVListener) {
        this.listeners.delete(listener);
    }
}

// Internal Method
const getOrCreateMMKV = (dbName: string, cachePath = false) => {
    if (_mmkvCache[dbName]) {
        return _mmkvCache[dbName];
    }

    let newStore: MMKV;
    try {
        // MMKV 4.x：构造函数 new MMKV() 已移除，改用 createMMKV()（其余用法不变：
        // id / path 配置、contains / getString / set / remove 均与 2.x 兼容）。
        newStore = createMMKV({
            id: dbName,
            path: cachePath ? pathConst.mmkvCachePath : pathConst.mmkvPath,
        });
    } catch (e) {
        // 原生模块不可用（例如新架构下未正确链接）：降级为内存存储，App 继续启动。
        console.warn(`[MusicFree] MMKV 原生模块不可用(${dbName})，已降级为内存存储`, e);
        _mmkvFallback = true;
        newStore = new MemoryMMKV(dbName) as unknown as MMKV;
    }

    _mmkvCache[dbName] = newStore;
    return newStore;
};

export default getOrCreateMMKV;
