module.exports = (output) => {
  try {
    const result = JSON.parse(output);
    const errors = [];

    if (!Array.isArray(result.issues)) {
      errors.push("issues must be an array");
    } else {
      const validTypes = ["hyperbole", "bias", "unsourced", "unclear", "grammar", "other"];
      const validSeverities = ["low", "medium", "high"];
      for (let i = 0; i < result.issues.length; i++) {
        const issue = result.issues[i];
        if (!validTypes.includes(issue.type)) {
          errors.push(`issues[${i}].type "${issue.type}" not in ${validTypes}`);
        }
        if (typeof issue.description !== "string" || !issue.description) {
          errors.push(`issues[${i}].description must be a non-empty string`);
        }
        if (!validSeverities.includes(issue.severity)) {
          errors.push(`issues[${i}].severity "${issue.severity}" not in ${validSeverities}`);
        }
      }
    }

    if (typeof result.summary !== "string" || !result.summary) {
      errors.push("summary must be a non-empty string");
    }

    const validQualities = ["poor", "fair", "good", "excellent"];
    if (!validQualities.includes(result.overall_quality)) {
      errors.push(`overall_quality "${result.overall_quality}" not in ${validQualities}`);
    }

    if (errors.length > 0) {
      return { pass: false, score: 0, reason: errors.join("; ") };
    }
    return { pass: true, score: 1, reason: "Valid ReviewResult schema" };
  } catch (e) {
    return { pass: false, score: 0, reason: `JSON parse error: ${e.message}` };
  }
};
