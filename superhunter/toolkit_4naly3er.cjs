// Run the pinned rule engine against the AST emitted by NQC's own solc.
const fs = require("node:fs");
const path = require("node:path");
const [checkout, input] = process.argv.slice(2);
const upstream = (name) => require(path.join(checkout, "src", name));
const analyze = upstream("analyze").default;
const issues = upstream("issues").default;
const files = JSON.parse(fs.readFileSync(input, "utf8"));
for (const type of Object.values(upstream("types").IssueTypes)) {
    process.stdout.write(analyze(files, issues.filter(issue => issue.type === type)));
}
