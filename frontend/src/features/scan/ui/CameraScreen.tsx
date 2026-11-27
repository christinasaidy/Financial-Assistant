import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useRef, useState, type ComponentRef } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, radius, touchTarget } from '@/shared/theme';
import { AppText, Button, LineIcon } from '@/shared/ui';

import type { Photo } from '../domain';

/** Opens the Reading screen with the photo. */
export function useOpenReading() {
  const router = useRouter();
  return (photo: Photo) => router.push({ pathname: '/scan/reading', params: { uri: photo.uri, type: photo.mimeType } });
}

/**
 * The camera (design/screens/09-scan-camera.png): dark, Close, "Scan receipt", flash; the viewfinder with white
 * corner brackets; a fixed tip in place of live receipt detection, which Expo Go cannot do (D051); Upload from the
 * photo library and the shutter. "Long receipt" waits for the backend to take several photos.
 */
export function CameraScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [flash, setFlash] = useState(false);
  const [busy, setBusy] = useState(false);
  const camera = useRef<ComponentRef<typeof CameraView>>(null);
  const openReading = useOpenReading();

  const shoot = async () => {
    if (busy || !camera.current) return;
    setBusy(true);
    try {
      const picture = await camera.current.takePictureAsync({ quality: 0.7 });
      if (picture?.uri) openReading({ uri: picture.uri, mimeType: 'image/jpeg' });
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    // iPhone photos are often HEIC, which the backend does not read: "Compatible" hands them over as JPEG.
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
    });
    const asset = result.canceled ? null : result.assets[0];
    if (asset) openReading({ uri: asset.uri, mimeType: asset.mimeType === 'image/png' ? 'image/png' : 'image/jpeg' });
  };

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]} testID="scan-camera">
      <StatusBar style="light" />
      <View style={styles.bar}>
        <Pressable accessibilityRole="button" accessibilityLabel="Close scanner" onPress={() => router.back()} style={styles.iconButton}>
          <LineIcon name="close" color="cameraInk" />
        </Pressable>
        <AppText weight={600} size={16} color="cameraInk" accessibilityRole="header">
          Scan receipt
        </AppText>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={flash ? 'Flash on' : 'Flash off'}
          accessibilityState={{ selected: flash }}
          onPress={() => setFlash((on) => !on)}
          style={[styles.iconButton, flash ? styles.flashOn : null]}
        >
          <LineIcon name="flash" color={flash ? 'cameraBg' : 'cameraInk'} />
        </Pressable>
      </View>

      <View style={styles.viewfinder}>
        <View style={styles.frame}>
          {permission?.granted ? (
            <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" flash={flash ? 'on' : 'off'} testID="camera-view" />
          ) : (
            <View style={styles.permission}>
              <AppText size={15} color="cameraInk" style={styles.center}>
                {permission && !permission.canAskAgain
                  ? 'Fatourati cannot use the camera. Allow it in the iPhone’s Settings, or upload a photo.'
                  : 'Fatourati needs the camera to scan your receipts.'}
              </AppText>
              {permission?.canAskAgain !== false ? <Button label="Allow the camera" onPress={() => void requestPermission()} /> : null}
            </View>
          )}
          <Corners />
          <View style={styles.pill} pointerEvents="none">
            <View style={styles.dot} />
            <AppText weight={500} size={13}>
              Hold the phone steady
            </AppText>
          </View>
        </View>
      </View>

      <AppText font="mono" size={11.5} color="cameraHint" style={styles.hint}>
        Fit the whole receipt inside the corners
      </AppText>

      <View style={styles.controls}>
        <Pressable accessibilityRole="button" accessibilityLabel="Upload a photo" onPress={() => void upload()} style={styles.side}>
          <LineIcon name="photo" size={24} color="cameraInk" />
          <AppText weight={500} size={12} color="cameraInk">
            Upload
          </AppText>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Take photo"
          accessibilityState={{ disabled: !permission?.granted || busy }}
          disabled={!permission?.granted || busy}
          onPress={() => void shoot()}
          style={({ pressed }) => [styles.shutter, { opacity: pressed || busy ? 0.7 : 1 }]}
          testID="shutter"
        >
          <View style={styles.shutterFill} />
        </Pressable>
        <View style={styles.side} />
      </View>
    </View>
  );
}

/** The four white corner brackets, 28 px with 3 px strokes (design/reference/09). */
function Corners() {
  return (
    <View style={styles.corners} pointerEvents="none">
      <View style={[styles.corner, { top: 0, left: 0, borderLeftWidth: 3, borderTopWidth: 3 }]} />
      <View style={[styles.corner, { top: 0, right: 0, borderRightWidth: 3, borderTopWidth: 3 }]} />
      <View style={[styles.corner, { bottom: 0, left: 0, borderLeftWidth: 3, borderBottomWidth: 3 }]} />
      <View style={[styles.corner, { bottom: 0, right: 0, borderRightWidth: 3, borderBottomWidth: 3 }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cameraBg },
  bar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, paddingHorizontal: 8 },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  flashOn: { backgroundColor: colors.cameraInk },
  viewfinder: { flex: 1, paddingVertical: 24, paddingHorizontal: 18 },
  frame: { flex: 1, borderRadius: 4, overflow: 'hidden', backgroundColor: colors.cameraFrame },
  permission: { flex: 1, justifyContent: 'center', padding: 28, gap: 18 },
  center: { textAlign: 'center' },
  corners: { position: 'absolute', top: 60, bottom: 30, left: 40, right: 40 },
  corner: { position: 'absolute', width: 28, height: 28, borderColor: colors.white },
  pill: {
    position: 'absolute',
    top: 6,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.cameraInk,
    borderRadius: 20,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.cobalt },
  hint: { textAlign: 'center', marginTop: 10 },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 18, paddingHorizontal: 28, paddingBottom: 34 },
  side: { width: 76, minHeight: 48, alignItems: 'center', justifyContent: 'center', gap: 6 },
  shutter: { width: 76, height: 76, borderRadius: 38, borderWidth: 4, borderColor: colors.cameraInk, alignItems: 'center', justifyContent: 'center' },
  shutterFill: { width: 60, height: 60, borderRadius: 30, backgroundColor: colors.cameraInk },
});
