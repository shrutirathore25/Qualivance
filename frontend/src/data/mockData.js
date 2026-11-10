// MOCK DATA - fictional, for UI development only. Not real AI output.
export const MOCK_ANALYSIS = {
  isMock: true,
  sourceType: "Pasted Text",
  form: {
    product_name: "",
    batch_number: "B-DEMO-014",
    incident_date: "",
    deviation_description: "Moisture result exceeds the stated maximum specification.",
    observed_result: "1.2%",
    specification: "Maximum 0.5%",
    immediate_containment: "",
  },
  investigationMethod: "5_whys",
  whys: [
    { question: "Why was the moisture result 1.2%?", answer: "Not established from the supplied report.", status: "unanswered" },
    { question: "Why was residual moisture above the limit?", answer: "", status: "unanswered" },
  ],
  potentialCauses: [
    {
      hypothesis: "Drying process did not remove sufficient moisture",
      rationale: "The result is above the limit, but the report does not say why.",
      evidence_needed: ["Dryer time/temperature logs", "Equipment maintenance records"],
      status: "unverified",
    },
  ],
  missingEvidence: ["Dryer logs", "Moisture test method and calibration records"],
  correctiveActions: [
    {
      description: "Retest retained sample using the approved method (draft suggestion).",
      rationale: "Rules out a one-off analytical error.",
      linked_cause: "Drying process did not remove sufficient moisture",
      verification: "Second analyst result and calibration record",
      status: "draft",
    },
  ],
  preventiveActions: [
    {
      description: "Review dryer end-point criteria in the batch record (draft suggestion).",
      rationale: "Reduces risk of recurrence if drying was incomplete.",
      linked_cause: "Drying process did not remove sufficient moisture",
      verification: "Moisture results of next 3 batches within limit",
      status: "draft",
    },
  ],
  uncertainties: ["Cause not established from the supplied text."],
};
