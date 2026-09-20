const fs = require("fs");
const path = require("path");

module.exports = (varName, prompt, otherVars) => {
  const file = path.join(__dirname, `${otherVars.dataset}_cases.json`);
  const cases = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!(otherVars.case in cases)) {
    throw new Error(`Case "${otherVars.case}" not found in ${file}`);
  }
  return { output: cases[otherVars.case] };
};
