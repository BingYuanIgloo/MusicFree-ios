/**
 * iOS 本地音乐元数据读取（纯 JS 解析，不依赖原生模块）
 *
 * iOS 上没有 Mp3Util 原生模块（只有 Android 有），这里把文件读成 ascii
 * 字符串（每字符一个字节）后直接解析音频标签：
 *  - MP3: ID3v2（TIT2/TPE1/TALB/TLEN/USLT/APIC）+ ID3v1 兜底
 *  - FLAC: STREAMINFO（时长）+ Vorbis Comment（标题/歌手/专辑/歌词）+ PICTURE（封面）
 *  - M4A/MP4: mvhd（时长）+ ilst（©nam/©ART/aART/©alb/©lyr/covr）
 * 其他格式（WMA/WAV/OGG/AAC/APE/Opus）返回空对象，调用方用文件名兜底。
 *
 * 所有入口永不抛错：读不到、解析失败都返回空结果。
 * 时长单位与 Android 原生一致：毫秒字符串。
 * 封面写入缓存文件后返回 file:// URI，与 Android 原生返回值格式一致。
 */
import type { IBasicMeta } from "@/native/mp3Util";
import pathConst from "@/constants/pathConst";
import CryptoJs from "crypto-js";
import { exists, mkdir, readFile, stat, writeFile } from "react-native-fs";

// 超过这个大小的文件不解析（避免一次性读入过大文件）
const MAX_PARSE_SIZE = 128 * 1024 * 1024;

interface ICoverData {
    mime: string;
    /** 封面图片字节（ascii 字符串，每字符一字节） */
    bytes: string;
}

interface IParsedMeta {
    meta: IBasicMeta;
    lyric: string;
    cover: ICoverData | null;
}

function emptyParsed(): IParsedMeta {
    return { meta: {}, lyric: "", cover: null };
}

// ---------- 二进制读取工具（操作 ascii 字符串，每字符一字节） ----------

function b(s: string, i: number): number {
    return s.charCodeAt(i) & 0xff;
}

function u16be(s: string, i: number): number {
    return (b(s, i) << 8) | b(s, i + 1);
}

function u32be(s: string, i: number): number {
    return (
        b(s, i) * 0x1000000 +
        ((b(s, i + 1) << 16) | (b(s, i + 2) << 8) | b(s, i + 3))
    );
}

function u32le(s: string, i: number): number {
    return (
        b(s, i) |
        (b(s, i + 1) << 8) |
        (b(s, i + 2) << 16) |
        b(s, i + 3) * 0x1000000
    );
}

function synchsafe(s: string, i: number): number {
    return (b(s, i) << 21) | (b(s, i + 1) << 14) | (b(s, i + 2) << 7) | b(s, i + 3);
}

function ascii(s: string, off: number, len: number): string {
    let out = "";
    for (let i = 0; i < len; i++) {
        out += String.fromCharCode(b(s, off + i));
    }
    return out;
}

function decodeUtf8(s: string, off: number, len: number): string {
    let out = "";
    let chunk: number[] = [];
    const flush = () => {
        if (chunk.length) {
            out += String.fromCharCode.apply(null, chunk as any);
            chunk = [];
        }
    };
    let i = off;
    const end = Math.min(off + len, s.length);
    while (i < end) {
        const c = b(s, i);
        let cp = 0;
        let n = 0;
        if (c < 0x80) {
            cp = c;
            n = 1;
        } else if ((c & 0xe0) === 0xc0) {
            cp = c & 0x1f;
            n = 2;
        } else if ((c & 0xf0) === 0xe0) {
            cp = c & 0x0f;
            n = 3;
        } else if ((c & 0xf8) === 0xf0) {
            cp = c & 0x07;
            n = 4;
        } else {
            i++;
            continue;
        }
        if (i + n > end) {
            break;
        }
        let ok = true;
        for (let j = 1; j < n; j++) {
            const cc = b(s, i + j);
            if ((cc & 0xc0) !== 0x80) {
                ok = false;
                break;
            }
            cp = (cp << 6) | (cc & 0x3f);
        }
        if (!ok) {
            i++;
            continue;
        }
        i += n;
        if (cp >= 0x10000) {
            cp -= 0x10000;
            chunk.push(0xd800 + (cp >> 10), 0xdc00 + (cp & 0x3ff));
        } else {
            chunk.push(cp);
        }
        if (chunk.length >= 8192) {
            flush();
        }
    }
    flush();
    return out;
}

function decodeUtf16(s: string, off: number, len: number, be: boolean): string {
    let out = "";
    let chunk: number[] = [];
    const flush = () => {
        if (chunk.length) {
            out += String.fromCharCode.apply(null, chunk as any);
            chunk = [];
        }
    };
    const end = Math.min(off + len, s.length);
    for (let i = off; i + 1 < end; i += 2) {
        const u = be ? u16be(s, i) : b(s, i) | (b(s, i + 1) << 8);
        chunk.push(u);
        if (chunk.length >= 8192) {
            flush();
        }
    }
    flush();
    return out;
}

/** 按给定的 ID3 文本编码解码一段文本（不含首字节的编码标识） */
function decodeTextWithEncoding(
    s: string,
    off: number,
    len: number,
    enc: number,
): string {
    if (len <= 0 || off >= s.length) {
        return "";
    }
    if (enc === 0) {
        // latin1：字节值即码点
        return ascii(s, off, len).replace(/\0.*$/, "");
    }
    if (enc === 3) {
        // UTF-8
        return decodeUtf8(s, off, len).replace(/\0.*$/, "");
    }
    if (enc === 1 || enc === 2) {
        // UTF-16（1 带 BOM，2 为 BE）
        let start = off;
        let be = enc === 2;
        if (enc === 1 && len >= 2) {
            const bom = u16be(s, off);
            if (bom === 0xfeff) {
                be = true;
                start = off + 2;
            } else if (bom === 0xfffe) {
                be = false;
                start = off + 2;
            }
        }
        return decodeUtf16(s, start, off + len - start, be).replace(
            /\0.*$/,
            "",
        );
    }
    return decodeUtf8(s, off, len).replace(/\0.*$/, "");
}

/** 解码 ID3v2 文本帧（首字节为编码标识） */
function decodeId3Text(s: string, off: number, len: number): string {
    if (len <= 0 || off >= s.length) {
        return "";
    }
    return decodeTextWithEncoding(s, off + 1, len - 1, b(s, off));
}

const B64_CHARS =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function base64encode(s: string): string {
    let out = "";
    for (let i = 0; i < s.length; i += 3) {
        const a = b(s, i);
        const c2 = i + 1 < s.length ? b(s, i + 1) : 0;
        const c3 = i + 2 < s.length ? b(s, i + 2) : 0;
        out += B64_CHARS[a >> 2];
        out += B64_CHARS[((a & 3) << 4) | (c2 >> 4)];
        out +=
            i + 1 < s.length
                ? B64_CHARS[((c2 & 15) << 2) | (c3 >> 6)]
                : "=";
        out += i + 2 < s.length ? B64_CHARS[c3 & 63] : "=";
    }
    return out;
}

// ---------- MP3: ID3v2 / ID3v1 ----------

function parseId3v2(s: string): IParsedMeta {
    const result = emptyParsed();
    const ver = b(s, 3);
    const flags = b(s, 5);
    const tagSize = synchsafe(s, 6);
    const tagEnd = Math.min(10 + tagSize, s.length);
    let data = s.slice(10, tagEnd);
    if (flags & 0x80) {
        // 解除同步：0xFF 0x00 还原为 0xFF
        data = data.replace(/\xff\x00/g, "\xff");
    }
    let pos = 0;
    if (flags & 0x40) {
        // 扩展头（极少出现）：跳过
        const extSize = ver === 4 ? synchsafe(data, 0) : u32be(data, 0);
        pos = ver === 4 ? extSize : 4 + extSize;
    }
    while (pos + 10 <= data.length) {
        const id = ascii(data, pos, 4);
        if (!/^[A-Z0-9]{4}$/.test(id)) {
            break;
        }
        const size =
            ver === 4 ? synchsafe(data, pos + 4) : u32be(data, pos + 4);
        if (size <= 0 || pos + 10 + size > data.length) {
            break;
        }
        const bodyOff = pos + 10;
        if (
            id === "TIT2" ||
            id === "TPE1" ||
            id === "TALB" ||
            id === "TLEN"
        ) {
            const text = decodeId3Text(data, bodyOff, size).trim();
            if (text) {
                if (id === "TIT2") {
                    result.meta.title = text;
                } else if (id === "TPE1") {
                    result.meta.artist = text;
                } else if (id === "TALB") {
                    result.meta.album = text;
                } else if (id === "TLEN" && /^\d+$/.test(text)) {
                    // TLEN 单位已是毫秒
                    result.meta.duration = text;
                }
            }
        } else if (id === "USLT" && !result.lyric) {
            const enc = b(data, bodyOff);
            let p = bodyOff + 4; // 编码(1) + 语言(3)
            // 跳过描述（按编码以 \0 或 \0\0 结尾）
            if (enc === 0 || enc === 3) {
                while (p < bodyOff + size && b(data, p) !== 0) {
                    p++;
                }
                p++;
            } else {
                while (
                    p + 1 < bodyOff + size &&
                    !(b(data, p) === 0 && b(data, p + 1) === 0)
                ) {
                    p += 2;
                }
                p += 2;
            }
            if (p < bodyOff + size) {
                // USLT 歌词文本使用帧首的编码字节，本身不再带编码标识
                result.lyric = decodeTextWithEncoding(
                    data,
                    p,
                    bodyOff + size - p,
                    enc,
                ).trim();
            }
        } else if (id === "APIC" && !result.cover) {
            const enc = b(data, bodyOff);
            let p = bodyOff + 1;
            let mimeEnd = p;
            while (mimeEnd < bodyOff + size && b(data, mimeEnd) !== 0) {
                mimeEnd++;
            }
            const mime = ascii(data, p, mimeEnd - p);
            p = mimeEnd + 1;
            if (p >= bodyOff + size) {
                break;
            }
            p++; // 图片类型
            if (enc === 0 || enc === 3) {
                while (p < bodyOff + size && b(data, p) !== 0) {
                    p++;
                }
                p++;
            } else {
                while (
                    p + 1 < bodyOff + size &&
                    !(b(data, p) === 0 && b(data, p + 1) === 0)
                ) {
                    p += 2;
                }
                p += 2;
            }
            if (p < bodyOff + size) {
                result.cover = {
                    mime,
                    bytes: data.slice(p, bodyOff + size),
                };
            }
        }
        pos += 10 + size;
    }
    return result;
}

function parseId3v1(s: string, meta: IBasicMeta) {
    if (s.length < 128) {
        return;
    }
    const tail = s.length - 128;
    if (ascii(s, tail, 3) !== "TAG") {
        return;
    }
    const clean = (off: number, len: number) =>
        ascii(s, off, len)
            .replace(/\0.*$/, "")
            .trim();
    const title = clean(tail + 3, 30);
    const artist = clean(tail + 33, 30);
    const album = clean(tail + 63, 30);
    if (title && !meta.title) {
        meta.title = title;
    }
    if (artist && !meta.artist) {
        meta.artist = artist;
    }
    if (album && !meta.album) {
        meta.album = album;
    }
}

// ---------- FLAC ----------

function parseFlac(s: string): IParsedMeta {
    const result = emptyParsed();
    let pos = 4; // 跳过 "fLaC"
    while (pos + 4 <= s.length) {
        const header = b(s, pos);
        const isLast = (header & 0x80) !== 0;
        const type = header & 0x7f;
        const len =
            (b(s, pos + 1) << 16) | (b(s, pos + 2) << 8) | b(s, pos + 3);
        const start = pos + 4;
        const end = Math.min(start + len, s.length);
        if (type === 0 && len >= 34) {
            // STREAMINFO：采样率 20bit + 总采样数 36bit
            const sampleRate =
                (b(s, start + 10) << 12) |
                (b(s, start + 11) << 4) |
                (b(s, start + 12) >> 4);
            const totalSamples =
                (b(s, start + 13) & 0x0f) * 0x100000000 +
                u32be(s, start + 14);
            if (sampleRate > 0 && totalSamples > 0) {
                result.meta.duration = String(
                    Math.round((totalSamples * 1000) / sampleRate),
                );
            }
        } else if (type === 4) {
            // VORBIS_COMMENT
            let p = start;
            if (p + 4 > end) {
                break;
            }
            const vendorLen = u32le(s, p);
            p += 4 + vendorLen;
            if (p + 4 > end) {
                break;
            }
            const count = u32le(s, p);
            p += 4;
            for (let i = 0; i < count && p + 4 <= end; i++) {
                const clen = u32le(s, p);
                p += 4;
                const entry = decodeUtf8(s, p, Math.min(clen, end - p));
                p += clen;
                const eq = entry.indexOf("=");
                if (eq <= 0) {
                    continue;
                }
                const key = entry.slice(0, eq).toUpperCase();
                const val = entry.slice(eq + 1).trim();
                if (!val) {
                    continue;
                }
                if (key === "TITLE" && !result.meta.title) {
                    result.meta.title = val;
                } else if (key === "ARTIST" && !result.meta.artist) {
                    result.meta.artist = val;
                } else if (
                    key === "ALBUMARTIST" &&
                    !result.meta.artist
                ) {
                    result.meta.artist = val;
                } else if (key === "ALBUM" && !result.meta.album) {
                    result.meta.album = val;
                } else if (
                    (key === "LYRICS" || key === "UNSYNCEDLYRICS") &&
                    !result.lyric
                ) {
                    result.lyric = val;
                }
            }
        } else if (type === 6 && !result.cover) {
            // PICTURE
            let p = start;
            p += 4; // 图片类型
            if (p + 4 > end) {
                break;
            }
            const mimeLen = u32be(s, p);
            p += 4;
            const mime = ascii(s, p, Math.min(mimeLen, end - p));
            p += mimeLen;
            if (p + 4 > end) {
                break;
            }
            const descLen = u32be(s, p);
            p += 4 + descLen;
            p += 16; // 宽/高/色深/颜色数
            if (p + 4 > end) {
                break;
            }
            const dataLen = u32be(s, p);
            p += 4;
            result.cover = {
                mime,
                bytes: s.slice(p, Math.min(p + dataLen, end)),
            };
        }
        pos = end;
        if (isLast) {
            break;
        }
    }
    return result;
}

// ---------- M4A / MP4 ----------

interface IAtomRange {
    start: number;
    end: number;
}

/** 在 [start, end) 内找第一个指定类型的 atom，返回其内容范围 */
function findAtom(
    s: string,
    start: number,
    end: number,
    type: string,
): IAtomRange | null {
    let p = start;
    while (p + 8 <= end) {
        let size = u32be(s, p);
        const atomType = ascii(s, p + 4, 4);
        let headerLen = 8;
        if (size === 1) {
            // 64 位长度
            if (p + 16 > end) {
                return null;
            }
            size = u32be(s, p + 8) * 0x100000000 + u32be(s, p + 12);
            headerLen = 16;
        } else if (size === 0) {
            size = end - p;
        }
        if (size < headerLen || p + size > end) {
            return null;
        }
        if (atomType === type) {
            return { start: p + headerLen, end: p + size };
        }
        p += size;
    }
    return null;
}

function parseMp4(s: string): IParsedMeta {
    const result = emptyParsed();
    const moov = findAtom(s, 0, s.length, "moov");
    if (!moov) {
        return result;
    }
    const mvhd = findAtom(s, moov.start, moov.end, "mvhd");
    if (mvhd) {
        const ver = b(s, mvhd.start);
        let timescale = 0;
        let duration = 0;
        if (ver === 0) {
            timescale = u32be(s, mvhd.start + 12);
            duration = u32be(s, mvhd.start + 16);
        } else {
            timescale = u32be(s, mvhd.start + 20);
            duration =
                u32be(s, mvhd.start + 24) * 0x100000000 +
                u32be(s, mvhd.start + 28);
        }
        if (timescale > 0 && duration > 0) {
            result.meta.duration = String(
                Math.round((duration * 1000) / timescale),
            );
        }
    }
    const udta = findAtom(s, moov.start, moov.end, "udta");
    if (!udta) {
        return result;
    }
    const metaAtom = findAtom(s, udta.start, udta.end, "meta");
    if (!metaAtom) {
        return result;
    }
    // meta 内容前 4 字节是版本/标志
    const ilst = findAtom(s, metaAtom.start + 4, metaAtom.end, "ilst");
    if (!ilst) {
        return result;
    }
    let p = ilst.start;
    while (p + 8 <= ilst.end) {
        const size = u32be(s, p);
        const type = ascii(s, p + 4, 4);
        if (size < 8 || p + size > ilst.end) {
            break;
        }
        const dataAtom = findAtom(s, p + 8, p + size, "data");
        if (dataAtom) {
            const payloadOff = dataAtom.start + 8; // 类型(4) + 地区(4)
            const payloadLen = dataAtom.end - payloadOff;
            if (payloadLen > 0) {
                if (
                    type === "©nam" ||
                    type === "©ART" ||
                    type === "aART" ||
                    type === "©alb" ||
                    type === "©lyr"
                ) {
                    const text = decodeUtf8(
                        s,
                        payloadOff,
                        payloadLen,
                    ).trim();
                    if (text) {
                        if (type === "©nam" && !result.meta.title) {
                            result.meta.title = text;
                        } else if (
                            type === "©ART" &&
                            !result.meta.artist
                        ) {
                            result.meta.artist = text;
                        } else if (
                            type === "aART" &&
                            !result.meta.artist
                        ) {
                            result.meta.artist = text;
                        } else if (
                            type === "©alb" &&
                            !result.meta.album
                        ) {
                            result.meta.album = text;
                        } else if (type === "©lyr" && !result.lyric) {
                            result.lyric = text;
                        }
                    }
                } else if (type === "covr" && !result.cover) {
                    const dataType = u32be(s, dataAtom.start + 4);
                    let mime = "image/jpeg";
                    if (dataType === 14) {
                        mime = "image/png";
                    } else if (
                        payloadLen >= 8 &&
                        b(s, payloadOff) === 0x89 &&
                        ascii(s, payloadOff + 1, 3) === "PNG"
                    ) {
                        mime = "image/png";
                    }
                    result.cover = {
                        mime,
                        bytes: s.slice(payloadOff, dataAtom.end),
                    };
                }
            }
        }
        p += size;
    }
    return result;
}

// ---------- 入口 ----------

function stripFileScheme(filePath: string): string {
    return filePath.replace(/^file:\/\//, "");
}

function parseAudioFile(content: string, ext: string): IParsedMeta {
    const lowerExt = ext.toLowerCase();
    if (content.length >= 3 && ascii(content, 0, 3) === "ID3") {
        const result = parseId3v2(content);
        parseId3v1(content, result.meta);
        return result;
    }
    if (content.length >= 4 && ascii(content, 0, 4) === "fLaC") {
        return parseFlac(content);
    }
    if (content.length >= 8 && ascii(content, 4, 4) === "ftyp") {
        return parseMp4(content);
    }
    // 无 ID3v2 的 MP3 仍可能有 ID3v1
    if (lowerExt === ".mp3") {
        const result = emptyParsed();
        parseId3v1(content, result.meta);
        return result;
    }
    return emptyParsed();
}

async function readAudioFile(filePath: string): Promise<IParsedMeta> {
    const plainPath = stripFileScheme(filePath);
    try {
        const fileStat = await stat(plainPath);
        if (!fileStat || fileStat.size > MAX_PARSE_SIZE) {
            return emptyParsed();
        }
        const content = await readFile(plainPath, "ascii");
        const dot = plainPath.lastIndexOf(".");
        const ext = dot === -1 ? "" : plainPath.slice(dot);
        return parseAudioFile(content, ext);
    } catch {
        return emptyParsed();
    }
}

/** 批量读取元数据：返回值与入参数组一一对应，失败项为空对象 */
export async function getIosMediaMeta(
    filePaths: string[],
): Promise<IBasicMeta[]> {
    const metas: IBasicMeta[] = [];
    for (const filePath of filePaths) {
        const parsed = await readAudioFile(filePath);
        metas.push(parsed.meta);
    }
    return metas;
}

/** 读取单个文件的元数据（失败返回空对象） */
export async function getIosBasicMeta(
    filePath: string,
): Promise<IBasicMeta> {
    const parsed = await readAudioFile(filePath);
    return parsed.meta;
}

/** 读取内嵌歌词（没有则返回空字符串） */
export async function getIosMediaLyric(
    filePath: string,
): Promise<string> {
    const parsed = await readAudioFile(filePath);
    return parsed.lyric;
}

/** 读取封面：写入缓存文件后返回 file:// URI，没有封面返回空字符串 */
export async function getIosMediaCoverImg(
    filePath: string,
): Promise<string> {
    try {
        const parsed = await readAudioFile(filePath);
        if (!parsed.cover || !parsed.cover.bytes) {
            return "";
        }
        const ext = parsed.cover.mime.includes("png") ? "png" : "jpg";
        const hash = CryptoJs.MD5(stripFileScheme(filePath)).toString(
            CryptoJs.enc.Hex,
        );
        const coverDir = pathConst.imageCachePath;
        const coverPath = `${coverDir}/${hash}.${ext}`;
        if (!(await exists(coverPath))) {
            try {
                await mkdir(coverDir);
            } catch {}
            await writeFile(
                coverPath,
                base64encode(parsed.cover.bytes),
                "base64",
            );
        }
        return `file://${coverPath}`;
    } catch {
        return "";
    }
}
