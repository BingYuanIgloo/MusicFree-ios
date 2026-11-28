/**
 * 诊断日志：拦截 console + 全局 JS 报错，存一个环形缓冲（最多 500 条），
 * 诊断面板实时显示，错误标红，一键复制。
 * 在 bootstrap 里最先 installAppLogger()，这样启动后的日志都能抓到。
 */
import { GlobalState } from "@/utils/stateMapper";

export type AppLogLevel = "log" | "info" | "warn" | "error";

export interface AppLogEntry {
    id: number;
    time: number;
    level: AppLogLevel;
    text: string;
}

const MAX_LOGS = 500;

let logs: AppLogEntry[] = [];
let nextId = 1;
let installed = false;

const logsStore = new GlobalState<AppLogEntry[]>([]);

function formatArg(arg: unknown): string {
    if (typeof arg === "string") {
        return arg;
    }
    try {
        return JSON.stringify(arg) ?? String(arg);
    } catch {
        return String(arg);
    }
}

function push(level: AppLogLevel, text: string) {
    logs.push({ id: nextId++, time: Date.now(), level, text });
    if (logs.length > MAX_LOGS) {
        logs = logs.slice(logs.length - MAX_LOGS);
    }
    logsStore.setValue([...logs]);
}

/** 在 bootstrap 最先调用。重复调用无害。 */
export function installAppLogger() {
    if (installed) {
        return;
    }
    installed = true;
    const origLog = console.log.bind(console);
    const origInfo = console.info.bind(console);
    const origWarn = console.warn.bind(console);
    const origError = console.error.bind(console);

    console.log = (...args: unknown[]) => {
        push("log", args.map(formatArg).join(" "));
        origLog(...args);
    };
    console.info = (...args: unknown[]) => {
        push("info", args.map(formatArg).join(" "));
        origInfo(...args);
    };
    console.warn = (...args: unknown[]) => {
        push("warn", args.map(formatArg).join(" "));
        origWarn(...args);
    };
    console.error = (...args: unknown[]) => {
        push("error", args.map(formatArg).join(" "));
        origError(...args);
    };

    try {
        const prevHandler = (global as any).ErrorUtils?.getGlobalHandler?.();
        (global as any).ErrorUtils?.setGlobalHandler?.(
            (err: any, isFatal?: boolean) => {
                push(
                    "error",
                    `[全局错误${isFatal ? "（致命）" : ""}] ${err?.message ?? String(err)}\n${err?.stack ?? ""}`,
                );
                if (prevHandler) {
                    prevHandler(err, isFatal);
                }
            },
        );
    } catch {}
}

/** 供诊断面板订阅（实时刷新）。 */
export function useAppLogs() {
    return logsStore.useValue();
}

export function getAppLogs(): AppLogEntry[] {
    return [...logs];
}

export function clearAppLogs() {
    logs = [];
    logsStore.setValue([]);
}

/** 复制用的纯文本：时间 + 级别 + 内容。 */
export function appLogsToText(): string {
    return logs
        .map(e => {
            const d = new Date(e.time);
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            const ss = String(d.getSeconds()).padStart(2, "0");
            return `[${hh}:${mm}:${ss}] [${e.level.toUpperCase()}] ${e.text}`;
        })
        .join("\n");
}

export function appLog(level: AppLogLevel, text: string) {
    push(level, text);
}
