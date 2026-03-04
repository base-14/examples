// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

import 'news_tab.dart';
import 'otel/otel_config.dart';
import 'otel/rum_cold_start.dart';
import 'otel/rum_session.dart';
import 'profile_tab.dart';
import 'settings_tab.dart';
import 'songs_tab.dart';
import 'widgets.dart';

Future<void> main() async {
  RumColdStart.markMainStart();

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    RumSession.instance.forceNextSample();
    RumSession.instance.recordBreadcrumb(
      'error',
      'flutter_error: ${details.exceptionAsString()}',
    );
    FlutterOTel.reportError(
      details.exceptionAsString(),
      details.exception,
      details.stack,
      attributes: {
        'app.screen.name': RumSession.instance.currentScreen,
        'session.id': RumSession.instance.sessionId,
        'error.breadcrumbs': RumSession.instance.getBreadcrumbString(),
      },
    );
    OTelConfig.flush();
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    RumSession.instance.forceNextSample();
    RumSession.instance.recordBreadcrumb(
      'error',
      'uncaught_error: ${error.runtimeType}',
    );
    FlutterOTel.reportError(
      'Uncaught error',
      error,
      stack,
      attributes: {
        'app.screen.name': RumSession.instance.currentScreen,
        'session.id': RumSession.instance.sessionId,
        'error.breadcrumbs': RumSession.instance.getBreadcrumbString(),
      },
    );
    OTelConfig.flush();
    return true;
  };

  await OTelConfig.initialize();
  WidgetsBinding.instance.addObserver(OTelConfig.lifecycleObserver);

  AppLifecycleListener(
    onPause: () {
      OTelConfig.flush();
      OTelConfig.pauseJankDetection();
    },
    onResume: () {
      OTelConfig.resumeJankDetection();
      RumSession.instance.refreshBatteryState();
    },
    onExitRequested: () async {
      await OTelConfig.shutdown();
      return AppExitResponse.exit;
    },
  );

  runApp(const MyAdaptingApp());
  RumColdStart.measureFirstFrame();
}

class MyAdaptingApp extends StatelessWidget {
  const MyAdaptingApp({super.key});

  @override
  Widget build(context) {
    return MaterialApp(
      title: 'Adaptive Music App',
      navigatorObservers: [OTelConfig.routeObserver],
      theme: ThemeData(
        primarySwatch: Colors.green,
      ),
      darkTheme: ThemeData.dark(),
      builder: (context, child) {
        return CupertinoTheme(
          data: const CupertinoThemeData(),
          child: Material(child: child),
        );
      },
      home: const PlatformAdaptingHomePage(),
    );
  }
}

class PlatformAdaptingHomePage extends StatefulWidget {
  const PlatformAdaptingHomePage({super.key});

  @override
  State<PlatformAdaptingHomePage> createState() =>
      _PlatformAdaptingHomePageState();
}

class _PlatformAdaptingHomePageState extends State<PlatformAdaptingHomePage> {
  final songsTabKey = GlobalKey();

  Widget _buildAndroidHomePage(BuildContext context) {
    return SongsTab(key: songsTabKey, androidDrawer: _AndroidDrawer());
  }

  Widget _buildIosHomePage(BuildContext context) {
    return CupertinoTabScaffold(
      tabBar: CupertinoTabBar(
        items: const [
          BottomNavigationBarItem(
            label: SongsTab.title,
            icon: SongsTab.iosIcon,
          ),
          BottomNavigationBarItem(
            label: NewsTab.title,
            icon: NewsTab.iosIcon,
          ),
          BottomNavigationBarItem(
            label: ProfileTab.title,
            icon: ProfileTab.iosIcon,
          ),
        ],
      ),
      tabBuilder: (context, index) {
        assert(index <= 2 && index >= 0, 'Unexpected tab index: $index');
        return switch (index) {
          0 => CupertinoTabView(
            defaultTitle: SongsTab.title,
            builder: (context) => SongsTab(key: songsTabKey),
          ),
          1 => CupertinoTabView(
            defaultTitle: NewsTab.title,
            builder: (context) => const NewsTab(),
          ),
          2 => CupertinoTabView(
            defaultTitle: ProfileTab.title,
            builder: (context) => const ProfileTab(),
          ),
          _ => const SizedBox.shrink(),
        };
      },
    );
  }

  @override
  Widget build(context) {
    return PlatformWidget(
      androidBuilder: _buildAndroidHomePage,
      iosBuilder: _buildIosHomePage,
    );
  }
}

class _AndroidDrawer extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: Colors.green),
            child: Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: Icon(
                Icons.account_circle,
                color: Colors.green.shade800,
                size: 96,
              ),
            ),
          ),
          ListTile(
            leading: SongsTab.androidIcon,
            title: const Text(SongsTab.title),
            onTap: () {
              OTelConfig.interactionTracker
                  .trackMenuSelection(context, 'drawer_menu', 'songs');
              Navigator.pop(context);
            },
          ),
          ListTile(
            leading: NewsTab.androidIcon,
            title: const Text(NewsTab.title),
            onTap: () {
              OTelConfig.interactionTracker
                  .trackMenuSelection(context, 'drawer_menu', 'news');
              Navigator.pop(context);
              Navigator.push<void>(
                context,
                MaterialPageRoute(
                  settings: const RouteSettings(name: '/news'),
                  builder: (context) => const NewsTab(),
                ),
              );
            },
          ),
          ListTile(
            leading: ProfileTab.androidIcon,
            title: const Text(ProfileTab.title),
            onTap: () {
              OTelConfig.interactionTracker
                  .trackMenuSelection(context, 'drawer_menu', 'profile');
              Navigator.pop(context);
              Navigator.push<void>(
                context,
                MaterialPageRoute(
                  settings: const RouteSettings(name: '/profile'),
                  builder: (context) => const ProfileTab(),
                ),
              );
            },
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Divider(),
          ),
          ListTile(
            leading: SettingsTab.androidIcon,
            title: const Text(SettingsTab.title),
            onTap: () {
              OTelConfig.interactionTracker
                  .trackMenuSelection(context, 'drawer_menu', 'settings');
              Navigator.pop(context);
              Navigator.push<void>(
                context,
                MaterialPageRoute(
                  settings: const RouteSettings(name: '/settings'),
                  builder: (context) => const SettingsTab(),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}
