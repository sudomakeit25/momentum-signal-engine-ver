// Jest setup — run before each test file.
//
// Mocks the native-only Expo modules so pure-JS logic and React-Native
// component trees can be tested without a simulator. Real behavior is
// exercised on-device.

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

// expo-router mocks — minimal surface covering Link / useRouter /
// useLocalSearchParams / Stack.Screen. Real navigation is not exercised
// in screen tests; we test the component's render output and interactions.
jest.mock("expo-router", () => {
  const React = require("react");
  const { Pressable } = require("react-native");

  const router = {
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  };

  const Link = ({ href, children, asChild, onPress }) => {
    // When asChild is passed, Link forwards to the child (a Pressable).
    // We simulate that by cloning the child with an onPress that records
    // the intended href on the router mock.
    const handler = () => {
      router.push(href);
      if (onPress) onPress();
    };
    if (asChild && React.isValidElement(children)) {
      return React.cloneElement(children, { onPress: handler });
    }
    return React.createElement(
      Pressable,
      { onPress: handler, testID: `link-${href}` },
      children,
    );
  };

  // Static search params let tests override per-case.
  let _params = {};

  return {
    __esModule: true,
    Link,
    useRouter: () => router,
    useLocalSearchParams: () => _params,
    __setSearchParams: (p) => {
      _params = p || {};
    },
    Stack: {
      Screen: () => null,
    },
    Tabs: {
      Screen: () => null,
    },
    router,
  };
});

// Safe-area context — test renderer doesn't provide native insets, so
// return zeros and pass through children.
jest.mock("react-native-safe-area-context", () => {
  const React = require("react");
  const { View } = require("react-native");
  return {
    SafeAreaProvider: ({ children }) => React.createElement(View, null, children),
    SafeAreaView: ({ children, ...rest }) =>
      React.createElement(View, rest, children),
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
  };
});
