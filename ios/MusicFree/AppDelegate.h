#import <RCTAppDelegate.h>
#import <UIKit/UIKit.h>

// SDK 58 已删除 EXAppDelegateWrapper（SDK 54 起已废弃，SDK 55 移除；
// Expo 官方模板改用 Swift 的 ExpoAppDelegate）。
// 本 App 仍用 ObjC 的 RCTAppDelegate 做父类；Expo 运行时的安装
// （global.expo）改由 AppDelegate.mm 里的 EXReactNativeFactory 完成。
// 注意：不要把父类改成 EXReactDelegateWrapper——它是 NSObject，没有
// moduleName/initialProps，也不是 UIApplicationDelegate，不能做父类。
@interface AppDelegate : RCTAppDelegate

@end
