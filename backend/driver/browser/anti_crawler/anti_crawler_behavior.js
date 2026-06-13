// Behavior simulation is intentionally disabled for crawler stability.
// Playwright actions should remain deterministic; do not auto-scroll or wrap events here.
window.behaviorSimulator = window.behaviorSimulator || {
    pause: function() {},
    resume: function() {}
};
