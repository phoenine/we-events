// Advanced anti-detection hooks intentionally stay side-effect free.
// Do not mutate network APIs, event dispatch, scrolling, or selectors here.
window.antiDetectionBypass = window.antiDetectionBypass || {};
