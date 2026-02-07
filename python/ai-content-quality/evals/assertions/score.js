module.exports = (output) => {
  try {
    const result = JSON.parse(output);
    const errors = [];

    if (typeof result.score !== "number" || result.score < 0 || result.score > 100) {
      errors.push(`score must be 0-100, got ${result.score}`);
    }

    if (typeof result.breakdown !== "object" || result.breakdown === null) {
      errors.push("breakdown must be an object");
    } else {
      const dims = ["clarity", "accuracy", "engagement", "originality"];
      for (const dim of dims) {
        const val = result.breakdown[dim];
        if (typeof val !== "number" || val < 0 || val > 100) {
          errors.push(`breakdown.${dim} must be 0-100, got ${val}`);
        }
      }
    }

    if (typeof result.summary !== "string" || !result.summary) {
      errors.push("summary must be a non-empty string");
    }

    if (errors.length > 0) {
      return { pass: false, score: 0, reason: errors.join("; ") };
    }
    return { pass: true, score: 1, reason: "Valid ScoreResult schema" };
  } catch (e) {
    return { pass: false, score: 0, reason: `JSON parse error: ${e.message}` };
  }
};
