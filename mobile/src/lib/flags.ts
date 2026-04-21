// Feature flags. Keep this tiny and centralized so App Store builds
// can gate work-in-progress features without deleting code.

// Apple's App Store Guideline 1.2 requires user-generated content
// surfaces to ship with moderation, flagging, and user blocking. The
// community feed currently has none of that, so it is dev-only until
// the moderation primitives are in place on the backend.
export const COMMUNITY_FEED_ENABLED = __DEV__;
