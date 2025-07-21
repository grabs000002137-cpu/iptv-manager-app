[app]
title = IPTV Manager
package.name = iptvmanager
package.domain = com.iptv.manager
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,json
version = 1.0
requirements = python3,kivy==2.1.0,requests,pyjnius,plyer,android

[buildozer]
log_level = 2

[android]
android.api = 33
android.minapi = 21
android.ndk_api = 21
android.sdk = 33
android.ndk = 25c
android.archs = arm64-v8a
android.accept_sdk_license = True
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE
