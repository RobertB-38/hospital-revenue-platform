-- A visit cannot end before it starts, and must have both dates.
SELECT account_no, admit_dttm, disch_dttm
FROM visit
WHERE disch_dttm IS NULL OR admit_dttm IS NULL OR disch_dttm < admit_dttm;
