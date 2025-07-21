[app]
# Informations de base
title = IPTV Manager
package.name = iptvmanager
package.domain = com.iptv.manager

# Code source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,json

# Version
version = 1.0

# Dépendances principales
requirements = python3,kivy==2.1.0,requests,pyjnius,plyer,android

# Permissions Android
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE

[buildozer]
# Niveau de debug
log_level = 2

[android]
# Configuration Android
android.api = 33
android.minapi = 21
android.ndk_api = 21
android.sdk = 33
android.ndk = 25c

# Architecture (simplifiée pour compatibilité)
android.archs = arm64-v8a

# Accepter automatiquement les licences
android.accept_sdk_license = True

# Configuration Gradle optimisée
android.gradle_dependencies = 
android.add_gradle_repositories =