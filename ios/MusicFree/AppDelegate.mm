#import "AppDelegate.h"

#import <Expo/Expo.h>
#import <React/RCTBundleURLProvider.h>
#import <React/RCTLinkingManager.h>

// RCTAppDelegate 的 loadReactNativeWindow 未公开声明，这里声明一下以便调用。
@interface AppDelegate ()
- (void)loadReactNativeWindow:(NSDictionary *)launchOptions;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions
{
  self.moduleName = @"MusicFree";

  // You can add your custom initial props in the dictionary below.
  // They will be passed down to the ViewController used by React Native.
  self.initialProps = @{};

  // Expo SDK 58：EXAppDelegateWrapper 已移除，Expo 运行时的安装改由
  // EXReactNativeFactory 在 host:didInitializeRuntime: 里完成（调
  // AppContext.setRuntime → prepareRuntime → 装 global.expo）。
  // RCTAppDelegate 会内联创建一个普通的 RCTReactNativeFactory，它从不调
  // setRuntime，于是 globalThis.expo 保持 undefined，JS 一加载
  // expo-modules-core 就在 `globalThis.expo.EventEmitter` 抛错白屏。
  // 所以这里不用 super 的实现（它会把 factory 覆盖回普通版），改用
  // Expo 的 factory，再按原样加载窗口。
  self.reactNativeFactory = [[EXReactNativeFactory alloc] initWithDelegate:self];

  [self loadReactNativeWindow:launchOptions];

  return YES;
}

- (NSURL *)sourceURLForBridge:(RCTBridge *)bridge
{
  return [self bundleURL];
}

- (NSURL *)bundleURL
{
#if DEBUG
  return [[RCTBundleURLProvider sharedSettings] jsBundleURLForBundleRoot:@".expo/.virtual-metro-entry"];
#else
  return [[NSBundle mainBundle] URLForResource:@"main" withExtension:@"jsbundle"];
#endif
}

// Linking API
- (BOOL)application:(UIApplication *)application openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenURLOptionsKey,id> *)options {
  return [super application:application openURL:url options:options] || [RCTLinkingManager application:application openURL:url options:options];
}

// Universal Links
- (BOOL)application:(UIApplication *)application continueUserActivity:(nonnull NSUserActivity *)userActivity restorationHandler:(nonnull void (^)(NSArray<id<UIUserActivityRestoring>> * _Nullable))restorationHandler {
  BOOL result = [RCTLinkingManager application:application continueUserActivity:userActivity restorationHandler:restorationHandler];
  return [super application:application continueUserActivity:userActivity restorationHandler:restorationHandler] || result;
}

// Explicitly define remote notification delegates to ensure compatibility with some third-party libraries
- (void)application:(UIApplication *)application didRegisterForRemoteNotificationsWithDeviceToken:(NSData *)deviceToken
{
  return [super application:application didRegisterForRemoteNotificationsWithDeviceToken:deviceToken];
}

// Explicitly define remote notification delegates to ensure compatibility with some third-party libraries
- (void)application:(UIApplication *)application didFailToRegisterForRemoteNotificationsWithError:(NSError *)error
{
  return [super application:application didFailToRegisterForRemoteNotificationsWithError:error];
}

// Explicitly define remote notification delegates to ensure compatibility with some third-party libraries
- (void)application:(UIApplication *)application didReceiveRemoteNotification:(NSDictionary *)userInfo fetchCompletionHandler:(void (^)(UIBackgroundFetchResult))completionHandler
{
  return [super application:application didReceiveRemoteNotification:userInfo fetchCompletionHandler:completionHandler];
}

@end
