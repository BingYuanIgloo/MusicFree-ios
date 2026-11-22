const {getDefaultConfig} = require('expo/metro-config');
const {mergeConfig} = require('@react-native/metro-config');

/**
 * Reference: https://github.com/software-mansion/react-native-svg/blob/main/USAGE.md
 */
const defaultConfig = getDefaultConfig(__dirname);
const {assetExts, sourceExts} = defaultConfig.resolver;
/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('metro-config').MetroConfig}
 */
const config = {
    transformer: {
        babelTransformerPath: require.resolve('react-native-svg-transformer'),
    },
    resolver: {
        assetExts: assetExts.filter(ext => ext !== 'svg'),
        sourceExts: [...sourceExts, 'svg'],
        // SDK 58 打包修法（run #14 失败原因）：Metro 解析 package.json 的
        // exports 字段时，只认 default / import / require / react-native
        // 这几个条件，不认 browser——而 nanoid 5 这类库把能在手机上跑的
        // 版本只放在 browser 条件里。结果 Metro 取了 default 分支的
        // index.js（import { webcrypto } from 'node:crypto'），而 Metro
        // 没有 node: 前缀的解析器，打包直接报错。
        // 这里把 browser 加进条件，exports 解析就和旧的
        // resolverMainFields（react-native → browser → main）一致了，
        // nanoid 会走到 index.browser.js（用全局 crypto.getRandomValues，
        // 已由 react-native-get-random-values 在 bootstrap 里补好）。
        // 已在本地用 @react-native/metro-config@0.88.1 实测：mergeConfig
        // 后 unstable_conditionNames 确为 ["react-native", "browser"]。
        unstable_conditionNames: ['react-native', 'browser'],
    },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
