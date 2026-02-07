module.exports = (output) => {
  try {
    const result = JSON.parse(output);
    const errors = [];

    if (!Array.isArray(result.suggestions)) {
      errors.push("suggestions must be an array");
    } else {
      for (let i = 0; i < result.suggestions.length; i++) {
        const s = result.suggestions[i];
        if (typeof s.original !== "string" || !s.original) {
          errors.push(`suggestions[${i}].original must be a non-empty string`);
        }
        if (typeof s.improved !== "string" || !s.improved) {
          errors.push(`suggestions[${i}].improved must be a non-empty string`);
        }
        if (typeof s.reason !== "string" || !s.reason) {
          errors.push(`suggestions[${i}].reason must be a non-empty string`);
        }
      }
    }

    if (typeof result.summary !== "string" || !result.summary) {
      errors.push("summary must be a non-empty string");
    }

    if (errors.length > 0) {
      return { pass: false, score: 0, reason: errors.join("; ") };
    }
    return { pass: true, score: 1, reason: "Valid ImproveResult schema" };
  } catch (e) {
    return { pass: false, score: 0, reason: `JSON parse error: ${e.message}` };
  }
};
