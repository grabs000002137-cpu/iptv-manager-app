[app]

# (str) Title of your application
title = IPTV Manager

# (str) Package name
package.name = iptvmanager

# (str) Package domain (needed for android/ios packaging)
package.domain = com.iptv.manager

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,txt,json

# (str) Application versioning (method 1)
version = 1.0

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy==2.1.0,requests,pyjnius,plyer,android

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (list) Supported orientations
# Valid options are: landscape, portrait, portrait-reverse or landscape-reverse
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE,WAKE_LOCK

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

[android]

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK / AAB will support.
android.minapi = 21

# (int) Android NDK API to use. This is the minimum API your app will support, it should usually match android.minapi.
android.ndk_api = 21

# (str) Android NDK version to use
android.ndk = 25c

# (int) Android SDK version to use
android.sdk = 33

# (str) Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
# In past, was `android.arch` as we weren't supporting builds for multiple archs at the same time.
android.archs = arm64-v8a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) XML file for custom backup rules (see official auto backup documentation)
# android.backup_rules =

# (str) If you need to insert variables into your AndroidManifest.xml file,
# you can do so with the manifestPlaceholders property.
# This property takes a map of key-value pairs. (via a string)
# Usage example : android.manifest_placeholders = key:value, key2:value2
# android.manifest_placeholders = 

# (bool) Skip byte compile for .py files
# android.no-byte-compile-python = False

# (str) The format used to package the app for release mode (aab or apk or aar).
# android.release_artifact = aab

# (str) The format used to package the app for debug mode (apk or aar).
# android.debug_artifact = apk

# (bool) Whether or not to run ant automatically if it is available.
# android.ant_subprojects = False

# (bool) If True, then skip trying to update the Android sdk
# This can be useful to avoid excess Internet downloads or save time
# when an update is due and you just want to test/build your package
android.skip_update = False

# (bool) If True, then automatically accept SDK license
# agreements. This is intended for automation only. If set to False,
# the default, you will be shown the license when first running
# buildozer.
android.accept_sdk_license = True

# (str) Android entry point, default is ok for Kivy-based app
#android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Android Activity
# use that parameter together with android.entrypoint to set custom Java class instead of PythonActivity
#android.activity_class_name = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Python Service
# use that parameter to set custom Java class instead of PythonService
#android.service_class_name = org.kivy.android.PythonService

# (str) Android app theme, default is ok for Kivy-based app
# android.apptheme = "@android:style/Theme.NoTitleBar"

# (list) Pattern to whitelist for the whole project
#android.whitelist =

# (str) Path to a custom whitelist file
#android.whitelist_src =

# (str) Path to a custom blacklist file
#android.blacklist_src =

# (list) List of Java .jar files to add to the libs so that pyjnius can access
# their classes. Don't add jars that you do not need, since extra jars can slow
# down the build process. Allows wildcards matching, for example:
# OUYA-ODK/libs/*.jar
#android.add_jars = foo.jar,bar.jar,path/to/more/*.jar

# (list) List of Java files to add to the android project (can be java or a
# directory containing the files)
#android.add_src =

# (list) Android AAR archives to add
#android.add_aars =

# (list) Put these files or directories in the apk assets directory.
# Either form may be used, and assets need not be in 'source.include_exts'.
# 1) android.add_assets = file1.txt,image.png,music.ogg,/absolute/path/dir
# 2) android.add_assets.1 = path/to/dir1
#    android.add_assets.2 = path/to/dir2
#    android.add_assets.3 = path/to/file
#android.add_assets =

# (list) Put these files or directories in the apk res directory.
# The option may be used in 3 ways, the value may contain one or zero ':'
# Some examples:
# 1) A file to add to resources, legal resource names contain ['a-z','0-9','_']
# android.add_resources = file1.png:drawable/icon.png
# 2) A directory, here  'legal_name' is a legal resource name
# android.add_resources = path/to/resources/dir/:drawable/legal_name
# 3) A directory or a file, here 'legal_name' is a legal resource name
# android.add_resources = path/to/resources/dir/:drawable/
# android.add_resources = path/to/resources/file.png:drawable/legal_name
#android.add_resources =

# (list) Gradle dependencies to add
#android.gradle_dependencies =

# (bool) Enable AndroidX support. Enable when 'android.gradle_dependencies'
# contains an 'androidx' package, or any package from Kotlin source.
# android.enable_androidx requires android.api >= 28
#android.enable_androidx = True

# (list) add java compile options
# this can for example be necessary when importing certain java libraries using the 'android.gradle_dependencies' option
# see https://developer.android.com/studio/write/java8-support for further information
# android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"

# (list) Gradle repositories to add {can be necessary for some android.gradle_dependencies}
# please enclose in double quotes 
# e.g. android.gradle_repositories = "google()", "jcenter()", "maven { url 'https://kotlin.bintray.com/ktor' }"
#android.gradle_repositories =

# (list) packaging options to add 
# see https://google.github.io/android-gradle-dsl/current/com.android.build.gradle.internal.dsl.PackagingOptions.html
# can be necessary to solve conflicts in gradle_dependencies
# please enclose in double quotes 
# e.g. android.add_packaging_options = "exclude 'META-INF/common.kotlin_module'", "exclude 'META-INF/*.kotlin_module'"
#android.add_packaging_options =

# (list) Java classes to add as activities to the manifest.
#android.add_activities = com.example.ExampleActivity

# (str) OUYA Console category. Should be one of GAME or APP
# If you leave this blank, OUYA support will not be enabled
#android.ouya.category = GAME

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
#android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
#android.manifest.intent_filters =

# (str) launchMode to set for the main activity
#android.manifest.launch_mode = standard

# (str) screenOrientation to set for the main activity.
# Valid values can be found at https://developer.android.com/guide/topics/manifest/activity-element.html#screen
#android.manifest.orientation = fullSensor

# (list) Android application meta-data to set (key=value format)
#android.meta_data =

# (str) Path to a custom AndroidManifest.xml file
#android.manifest =

# (int) overrides automatic versionCode computation (used in build.gradle)
# this is not the same as app version and should only be edited if you know what you're doing
# android.numeric_version = 1

# (bool) disables the generation of the Python loadable module
# useful for apps that are embedding python as a shared library
#android.no_loadable_module = False

# (str) Path to the screen XML file to include as the launch screen.
#android.launch_screen =

# (str) Path to the splash screen drawable definition file to include as the launch screen.
#android.launch_screen_drawable =

# (list) List of service java files to add to the android project (can be java or a
# directory containing the files)
#android.add_services =

# (str) if specified, this property will specify the location of the gradle binary
# if not specified, gradle wrapper will be used (via ./gradlew)
#android.gradle_path =

# (str) Name of the certificate to use for signing the debug version
# Get a list of available identities: buildozer android list_identities
#android.debug_keystore = ~/.android/debug.keystore

# (str) The password for the keystore
#android.keystore_passwd = android

# (str) The key alias for the keystore.
#android.key_alias = androiddebugkey

# (str) The password for the key alias
#android.alias_passwd = android

# (str) Path to a custom release keystore file to create a signed release.
# If you haven't created your keystore file yet, use the keytool
# command from the JDK to create it (e.g. `keytool -genkey -v -keystore ~/my-release-key.keystore -alias alias_name -keyalg RSA -keysize 2048 -validity 10000`).
#android.release_keystore =

# (str) The password for the release keystore
#android.release_keystore_passwd =

# (str) The key alias for the release keystore.
#android.release_keyalg = 

# (str) The password for the release key alias
#android.release_alias_passwd =

# (str) The key alias for the release keystore.
#android.release_alias =

[buildozer:global]

# Here you can pass global buildozer options
# Please read the buildozer README regarding the difference between
# 'buildozer:global' and 'buildozer' section.

# (list) List of included Recipes
#global.include_recipes = []

# (str) Path to custom recipes directory  
#global.recipes_path =