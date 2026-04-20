// Jest setup — run before each test file.
//
// Mocks the native-only Expo modules so pure-JS logic can be tested
// without needing a simulator. Real behavior is exercised on-device.

jest.mock("expo-device", () => ({
  isDevice: true,
}));

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    expoConfig: {
      extra: { apiBase: "https://example-backend.test" },
      version: "0.1.0",
    },
    easConfig: {},
  },
}));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  setNotificationChannelAsync: jest.fn().mockResolvedValue(undefined),
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: "granted" }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: "granted" }),
  getExpoPushTokenAsync: jest.fn().mockResolvedValue({
    data: "ExponentPushToken[fake-token]",
  }),
  addNotificationResponseReceivedListener: jest.fn().mockReturnValue({
    remove: jest.fn(),
  }),
  AndroidImportance: { DEFAULT: 3 },
}));
