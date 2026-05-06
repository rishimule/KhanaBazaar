const SUPPRESS_PATTERNS = [
  "__firefox__",
  "window.ethereum",
  "ethereum.selectedAddress",
];

const script = `
(function () {
  var patterns = ${JSON.stringify(SUPPRESS_PATTERNS)};
  function shouldSuppress(message) {
    if (typeof message !== "string") return false;
    for (var i = 0; i < patterns.length; i++) {
      if (message.indexOf(patterns[i]) !== -1) return true;
    }
    return false;
  }
  window.addEventListener("error", function (event) {
    var msg = event && (event.message || (event.error && event.error.message));
    if (shouldSuppress(msg)) {
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  }, true);
  window.addEventListener("unhandledrejection", function (event) {
    var reason = event && event.reason;
    var msg = reason && (typeof reason === "string" ? reason : reason.message);
    if (shouldSuppress(msg)) {
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  }, true);
})();
`;

export default function ThirdPartyErrorSuppressor() {
  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
