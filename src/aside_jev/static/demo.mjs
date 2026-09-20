export function demo(t) {
  return {
  observation: {
    title: t("Form input example"),
    url: "http://127.0.0.1:8765/",
    fields: { verification: { empty: true } },
  },
  candidates: [
    {
      id: "fill-verification",
      description: t("Fill the empty verification field with the prepared value."),
      tool: "aside_type",
      arguments: {
        selector: "#verification",
        text: "demo-value",
        replace: true,
      },
    },
    {
      id: "submit-form",
      description: t("Submit the form after completing the required fields."),
      tool: "aside_click",
      arguments: { selector: "button[type=submit]" },
    },
    {
      id: "abstain",
      description: t("Stop when there is not enough evidence to decide."),
      tool: null,
      arguments: {},
    },
  ],
};
}

// 사용자가 편집한 입력은 언어 전환으로 덮어쓰지 않는다.
export function migrateDemo(input, previous, next) {
  const result = structuredClone(input);
  for (const key of ["observation", "candidates"]) {
    if (JSON.stringify(input[key]) === JSON.stringify(previous[key])) result[key] = structuredClone(next[key]);
  }
  return result;
}
export function displayDescription(candidate, language, messages) {
  for (const locale of ["en", "ko"]) {
    const source = demo((key) => messages[locale][key] ?? key);
    const index = source.candidates.findIndex((item) => item.id === candidate.id && item.description === candidate.description && item.tool === candidate.tool && JSON.stringify(item.arguments) === JSON.stringify(candidate.arguments));
    if (index !== -1) return demo((key) => messages[language][key] ?? key).candidates[index].description;
  }
  const fallback = "No safe executable action for the current observation.";
  if (candidate.id === "abstain" && candidate.description === fallback) return messages[language][fallback];
  return candidate.description;
}
