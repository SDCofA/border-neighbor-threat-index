(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.BNTIFreshness = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const MINUTE = 60 * 1000;

  function formatAge(minutes) {
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${Math.floor(minutes)}m ago`;
    const hours = Math.floor(minutes / 60);
    const remainder = Math.floor(minutes % 60);
    return remainder ? `${hours}h ${remainder}m ago` : `${hours}h ago`;
  }

  function evaluate(generatedAt, now = new Date(), targetMinutes = 120) {
    const generated = generatedAt ? new Date(generatedAt) : null;
    const nowDate = now instanceof Date ? now : new Date(now);
    if (!generated || Number.isNaN(generated.getTime()) || Number.isNaN(nowDate.getTime())) {
      return { level: 'unknown', label: 'Update time unavailable', ageMinutes: null };
    }

    const ageMinutes = (nowDate.getTime() - generated.getTime()) / MINUTE;
    if (ageMinutes < -5) {
      return { level: 'unknown', label: 'Clock check needed', ageMinutes };
    }
    if (ageMinutes <= targetMinutes + 30) {
      return { level: 'current', label: `Current · ${formatAge(Math.max(ageMinutes, 0))}`, ageMinutes };
    }
    if (ageMinutes <= targetMinutes * 4) {
      return { level: 'delayed', label: `Refresh delayed · ${formatAge(ageMinutes)}`, ageMinutes };
    }
    return { level: 'stale', label: `Stale snapshot · ${formatAge(ageMinutes)}`, ageMinutes };
  }

  return { evaluate, formatAge };
});
