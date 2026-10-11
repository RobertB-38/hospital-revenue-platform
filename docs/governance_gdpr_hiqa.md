# Governance note: GDPR, HIQA and HSE (one page)

**Scope.** This demonstrator uses only synthetic data (Synthea, plus invented financial assumptions). No real patient,
MIMIC or hospital data is used. The controls below are built as they would be for real data.

## GDPR and the Data Protection Act 2018 (Ireland)

| Requirement | How the build handles it |
|---|---|
| Health data is special-category data (GDPR Article 9) and needs a lawful basis plus an Article 9 condition | For a hospital's own management reporting this is normally Article 9(2)(h), the management of health services, under the Data Protection Act 2018. Confirmed by the hospital's DPO, not by the BI team. |
| Data minimisation (Article 5(1)(c)) | Names, address, full date of birth, Eircode routing key and insurer membership number exist only in the landing files. Silver selects none of them. A test in `tests/` fails if a later change adds them back. Birth year and county are the only demographics kept. |
| Pseudonymised data is still personal data (Recital 26) | The MRN is replaced by a salted SHA-256 key. The salt is a notebook parameter here; in production it comes from Azure Key Vault. Whoever holds the salt can re-identify, so access to the salt is the control. Gold is treated as personal data, not anonymous data. |
| Security of processing (Article 32) | Data stays in the Fabric North Europe region (Ireland). Workspace roles limit who sees bronze. Row-level security roles limit each site manager to their site (defined in the model, not yet tested with a second user). I run the test suite locally before committing. Running it in Azure DevOps with a branch policy on `main` is the next step and is not set up yet. |
| Accountability and DPIA (Articles 5(2) and 35) | Large-scale processing of health data normally needs a Data Protection Impact Assessment before go-live. This repo supplies the inputs: data dictionary, data flow, controls, retention points. |
| Retention | Bronze is the audit copy. In production set a retention period with the DPO and delete raw files after it. Trial data is deleted when the trial ends. |
| Regulator | Data Protection Commission (DPC). |

## HIQA

- HIQA sets national standards and inspects health services. Its main licensing powers cover public services and
  some regulated areas (for example, HIQA inspects medical exposure to ionising radiation in private hospitals).
- A Patient Safety (Licensing) Bill that would require private hospitals to be licensed has been proposed for years.
  As far as I could find it had not passed by mid-2025, so check its current status before quoting it.
- What matters for a BI team either way: data quality and information governance. The checks in this build
  (manifest totals, reconciliation, quarantine log, documented definitions in `data_dictionary.md`) are the
  evidence an auditor or accreditor (JCI for this kind of hospital) would ask for.

## HSE

- The HSE Healthcare Pricing Office publishes DRG prices for public hospitals. They are a useful public benchmark
  for cost per case. They are **not** private hospital prices, and this build does not present them as such.
- Private hospitals also deliver care purchased by the National Treatment Purchase Fund (NTPF). A real build would
  add NTPF as a payer, with its own remittance rules.

## Rules this project follows

1. Never claim to use MEDITECH. The staging layer only imitates a hospital-system flat-file export.
2. Every invented figure is labelled synthetic: in the data (`is_synthetic*` columns), in the report header and in the README.
3. Credentialed MIMIC-IV data is never used. Its licence restricts it to research and forbids sharing.
