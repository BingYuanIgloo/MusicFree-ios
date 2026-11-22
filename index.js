/**
 * @format
 */

// 启动安全网：全局 JS 错误尽早接管，避免白屏无提示。
// 注意：import 会被提升到最前面执行，所以这里先于入口模块加载完成。
if (typeof ErrorUtils !== "undefined" && ErrorUtils.setGlobalHandler) {
    ErrorUtils.setGlobalHandler(error => {
        console.error("[MusicFree] 未捕获的 JS 错误", error);
    });
}

import {AppRegistry} from 'react-native';
import {name as appName} from './app.json';

let Pages;
try {
    Pages = require('./src/entry').default;
    const TrackPlayer = require('@rntp/player').default;
    try {
        // v5：registerPlaybackSession 要在 registerComponent 之前调用；
        // 注册失败不影响打开（播放服务可稍后重试）。
        TrackPlayer.registerPlaybackSession(() => require('./src/service/index')());
    } catch (e) {
        console.warn('[MusicFree] 播放服务注册失败（不影响打开）', e);
    }
} catch (e) {
    // 入口模块加载失败（例如原生存储模块异常）：绝不白屏，直接显示错误。
    console.error('[MusicFree] 入口加载失败', e);
    const React = require('react');
    const {View, Text, ScrollView, TouchableOpacity} = require('react-native');
    const message = String((e && e.message) || e);
    const stack = String((e && e.stack) || '');
    Pages = function BootErrorScreen() {
        const [copied, setCopied] = React.useState(false);
        const fullText = message + '\n\n' + stack;
        const onCopy = () => {
            try {
                const ClipboardModule = require('@react-native-clipboard/clipboard');
                const Clipboard = ClipboardModule.default || ClipboardModule;
                Clipboard.setString(fullText);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            } catch (err) {
                console.warn('[MusicFree] 复制报错信息失败', err);
            }
        };
        return (
            <View style={{flex: 1, backgroundColor: '#fff', padding: 24, justifyContent: 'center'}}>
                <Text style={{fontSize: 18, fontWeight: 'bold', marginBottom: 12}}>MusicFree 启动失败</Text>
                <Text style={{color: '#c00', marginBottom: 12}}>{message}</Text>
                <ScrollView>
                    <Text style={{color: '#666', fontSize: 12}}>{stack}</Text>
                </ScrollView>
                <TouchableOpacity
                    onPress={onCopy}
                    style={{marginTop: 16, backgroundColor: '#1677ff', borderRadius: 8, paddingVertical: 12, alignItems: 'center'}}>
                    <Text style={{color: '#fff', fontSize: 16, fontWeight: 'bold'}}>
                        {copied ? '已复制 ✓' : '一键复制报错信息'}
                    </Text>
                </TouchableOpacity>
                <Text style={{marginTop: 12, color: '#666', textAlign: 'center'}}>复制后把文字发给开发者，截图也可以。</Text>
            </View>
        );
    };
}

AppRegistry.registerComponent(appName, () => Pages);
