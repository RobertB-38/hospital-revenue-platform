# Copilot: prepared interview answer

**Fact first.** Copilot is not available on Fabric trial capacities, so this project could not use it. The answer
below is how I would use it on a paid capacity, and where I would not trust it.

## Where Copilot would speed up this project

| Task in this build | How Copilot helps | What I still check myself |
|---|---|---|
| Writing DAX measures | Draft a measure from a description, e.g. "debtors over 90 days as a share of debtors". | The filter context. A semi-additive balance summed across months is the classic wrong answer. |
| Notebook code | Draft PySpark transforms and explain unfamiliar code. | Joins and de-duplication. Reconciliation checks prove totals still match. |
| Report pages | Suggest a first page layout from the semantic model. | That every visual answers one finance question, and labels say "synthetic". |
| Self-service for finance users | Users ask questions in plain English over the semantic model. | Only works well if the model has clear names, descriptions and display folders. That is why every measure here has a description. |
| Documentation | Draft descriptions for tables and measures. | Accuracy against the code. |

## Where I would not rely on it

- **Month-end figures.** Anything signed off must come from tested measures and the locked Warehouse close, not a generated answer.
- **Patient data.** Prompts and outputs inherit the user's permissions; row-level security must be right first.
  Copilot in Fabric respects the user's access, but a badly secured model means a badly secured Copilot.

## One-line version

"Copilot makes the build faster and helps finance users ask their own questions, but the semantic model has to be
well named, documented and secured first. Month-end numbers still come from tested measures and the locked close."
