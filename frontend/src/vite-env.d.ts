/// <reference types="vite/client" />

// Vite's ambient types, referenced the conventional way. Added so
// `import.meta.env.DEV` type-checks - the i18n provider uses it to warn about
// a missing translation key in development and stay silent in a build.
