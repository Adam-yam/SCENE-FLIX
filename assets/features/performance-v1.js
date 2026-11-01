(() => {
  const metrics = Object.create(null);
  Object.defineProperty(window, "sceneFlixPerformance", { get: () => Object.freeze({ ...metrics }) });
  function start() {
    if (!window.PerformanceObserver) return;
    const script = document.createElement("script");
    script.src = new URL("web-vitals-v6.2.3.min.js", document.querySelector('script[src$="performance-v1.js"]').src).href;
    script.onload = () => {
      const record = metric => {
        metrics[metric.name] = Object.freeze({ value: Math.round(metric.value * 1000) / 1000, rating: metric.rating });
      };
      for (const name of ["onLCP", "onINP", "onCLS"]) window.webVitals?.[name]?.(record, { reportAllChanges: true });
    };
    script.onerror = () => script.remove();
    document.head.append(script);
  }
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
})();
