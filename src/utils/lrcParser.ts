const timeReg = /\[[\d:.]+\]/g;
// 歌词杂符号清理：只保留中英文语法里出现的字符。
// 保留：所有字母、变音符号、数字、空白，以及下面这些歌词里有意义的标点。
// 用户白名单（2026-11-28）：撇号 '、逗号 ,、句号 .、感叹号 !、问号 ?、
// 星号 *（歌词打码靠它，删掉就半句看不懂）。用户又补了一句让我自己
// 定：再留几个歌词里确实有用的——省略号 …（拖尾）、破折号 — –（停顿）、
// 中圆点 ·（外国人名里的分隔，如约翰·列侬）、顿号 、（中文并列）。
// 其余一律删：^ ` | \ < > { } 引号、冒号、分号、括号、斜杠、
// @ # $ % & + = _ ~ 等。
const LYRIC_PUNCT = "'\u2019,\uff0c\u3001.\u3002\uff0e!\uff01?\uff1f*\uff0a\u2026\u2014\u2013\u00b7";

let LYRIC_CLEAN_RE: RegExp | null = null;
try {
    const punct = LYRIC_PUNCT.replace(/([\]\\^-])/g, "\\$1");
    LYRIC_CLEAN_RE = new RegExp(
        `[^\\p{L}\\p{M}\\p{N}\\p{Z}${punct}]`,
        "gu",
    );
} catch {
    LYRIC_CLEAN_RE = null;
}

export function cleanLyricLine(line: string): string {
    if (!line) {
        return line;
    }
    // 先去掉控制字符和零宽字符
    let s = line.replace(/[\u0000-\u001F\u007F\u200B\u200C\u200D\uFEFF]/g, "");
    if (LYRIC_CLEAN_RE) {
        s = s.replace(LYRIC_CLEAN_RE, "");
    } else {
        // 旧引擎不支持 \\p{...} 时的兜底：只删已知的杂符号
        s = s.replace(/[\^`|\\<>{}\u266a\u266b]/g, "");
    }
    return s;
}

const metaReg = /\[(.+):(.+)\]/g;

type LyricMeta = Record<string, any>;

interface IOptions {
    musicItem?: IMusic.IMusicItem;
    lyricSource?: ILyric.ILyricSource;
    translation?: string;
    extra?: Record<string, any>;
}

export interface IParsedLrcItem {
    /** 时间 s */
    time: number;
    /** 歌词 */
    lrc: string;
    /** 翻译 */
    translation?: string;
    /** 位置 */
    index: number;
}

export default class LyricParser {
    private _musicItem?: IMusic.IMusicItem;

    private meta: LyricMeta;
    private lrcItems: Array<IParsedLrcItem>;

    private extra: Record<string, any>;

    private lastSearchIndex = 0;

    public hasTranslation = false;
    public lyricSource?: ILyric.ILyricSource;

    get musicItem() {
        return this._musicItem;
    }

    constructor(raw: string, options?: IOptions) {
        // init
        this._musicItem = options?.musicItem;
        this.extra = options?.extra || {};
        this.lyricSource = options?.lyricSource;

        let translation = options?.translation;
        if (!raw && translation) {
            raw = translation;
            translation = undefined;
        }

        const { lrcItems, meta } = this.parseLyricImpl(raw);
        if (this.extra.offset) {
            meta.offset = (meta.offset ?? 0) + this.extra.offset;
        }
        this.meta = meta;
        this.lrcItems = lrcItems;

        if (translation) {
            this.hasTranslation = true;
            const transLrcItems = this.parseLyricImpl(translation).lrcItems;

            // 2 pointer
            let p1 = 0;
            let p2 = 0;

            while (p1 < this.lrcItems.length) {
                const lrcItem = this.lrcItems[p1];
                while (
                    transLrcItems[p2].time < lrcItem.time &&
                    p2 < transLrcItems.length - 1
                ) {
                    ++p2;
                }
                if (transLrcItems[p2].time === lrcItem.time) {
                    lrcItem.translation = transLrcItems[p2].lrc;
                } else {
                    lrcItem.translation = "";
                }

                ++p1;
            }
        }
    }

    getPosition(position: number): IParsedLrcItem | null {
        position = position - (this.meta?.offset ?? 0);
        let index;
        /** 最前面 */
        if (!this.lrcItems[0] || position < this.lrcItems[0].time) {
            this.lastSearchIndex = 0;
            return null;
        }
        for (
            index = this.lastSearchIndex;
            index < this.lrcItems.length - 1;
            ++index
        ) {
            if (
                position >= this.lrcItems[index].time &&
                position < this.lrcItems[index + 1].time
            ) {
                this.lastSearchIndex = index;
                return this.lrcItems[index];
            }
        }

        for (index = 0; index < this.lastSearchIndex; ++index) {
            if (
                position >= this.lrcItems[index].time &&
                position < this.lrcItems[index + 1].time
            ) {
                this.lastSearchIndex = index;
                return this.lrcItems[index];
            }
        }

        index = this.lrcItems.length - 1;
        this.lastSearchIndex = index;
        return this.lrcItems[index];
    }

    getLyricItems() {
        return this.lrcItems;
    }

    getMeta() {
        return this.meta;
    }

    toString(options?: {
        withTimestamp?: boolean;
        type?: "raw" | "translation";
    }) {
        const { type = "raw", withTimestamp = true } = options || {};

        if (withTimestamp) {
            return this.lrcItems
                .map(
                    item =>
                        `${this.timeToLrctime(item.time)} ${
                            type === "raw" ? item.lrc : item.translation
                        }`,
                )
                .join("\r\n");
        } else {
            return this.lrcItems
                .map(item => (type === "raw" ? item.lrc : item.translation))
                .join("\r\n");
        }
    }

    /** [xx:xx.xx] => x s */
    private parseTime(timeStr: string): number {
        let result = 0;
        const nums = timeStr.slice(1, timeStr.length - 1).split(":");
        for (let i = 0; i < nums.length; ++i) {
            result = result * 60 + +nums[i];
        }
        return result;
    }
    /** x s => [xx:xx.xx] */
    private timeToLrctime(sec: number) {
        const min = Math.floor(sec / 60);
        sec = sec - min * 60;
        const secInt = Math.floor(sec);
        const secFloat = sec - secInt;
        return `[${min.toFixed(0).padStart(2, "0")}:${secInt
            .toString()
            .padStart(2, "0")}.${secFloat.toFixed(2).slice(2)}]`;
    }

    private parseMetaImpl(metaStr: string) {
        if (metaStr === "") {
            return {};
        }
        const metaArr = metaStr.match(metaReg) ?? [];
        const meta: any = {};
        let k, v;
        for (const m of metaArr) {
            k = m.substring(1, m.indexOf(":"));
            v = m.substring(k.length + 2, m.length - 1);
            if (k === "offset") {
                meta[k] = +v / 1000;
            } else {
                meta[k] = v;
            }
        }
        return meta;
    }

    private parseLyricImpl(raw: string) {
        raw = raw.trim();
        const rawLrcItems: Array<IParsedLrcItem> = [];
        const rawLrcs = raw.split(timeReg) ?? [];
        const rawTimes = raw.match(timeReg) ?? [];
        const len = rawTimes.length;

        const meta = this.parseMetaImpl(rawLrcs[0].trim());
        rawLrcs.shift();

        let counter = 0;
        let j, lrc;
        for (let i = 0; i < len; ++i) {
            counter = 0;
            while (rawLrcs[0] === "") {
                ++counter;
                rawLrcs.shift();
            }
            lrc = cleanLyricLine(rawLrcs[0]?.trim?.() ?? "");
            for (j = i; j < i + counter; ++j) {
                rawLrcItems.push({
                    time: this.parseTime(rawTimes[j]),
                    lrc,
                    index: j,
                });
            }
            i += counter;
            if (i < len) {
                rawLrcItems.push({
                    time: this.parseTime(rawTimes[i]),
                    lrc,
                    index: j,
                });
            }
            rawLrcs.shift();
        }
        let lrcItems = rawLrcItems.sort((a, b) => a.time - b.time);
        lrcItems.forEach((item, index) => {
            item.index = index;
        });
        if (lrcItems.length === 0 && raw.length) {
            lrcItems = raw.split("\n").map((_, index) => ({
                time: 0,
                lrc: cleanLyricLine(_),
                index,
            }));
        }

        return {
            lrcItems,
            meta,
        };
    }
}
