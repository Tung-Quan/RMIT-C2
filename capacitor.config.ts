import type { CapacitorConfig } from "@capacitor/cli";

const allowLocalHttpForAndroid =
  process.env.CAPACITOR_LOCAL_ANDROID_HTTP === "1";

const config: CapacitorConfig = {
  appId: "com.fairenrol.app",
  appName: "FairEnrol",
  webDir: "dist",
  backgroundColor: "#f4f6f1",
  server: {
    androidScheme: "https",
    iosScheme: "https",
  },
  android: {
    allowMixedContent: allowLocalHttpForAndroid,
  },
  ios: {
    contentInset: "automatic",
    backgroundColor: "#f4f6f1",
  },
};

export default config;
