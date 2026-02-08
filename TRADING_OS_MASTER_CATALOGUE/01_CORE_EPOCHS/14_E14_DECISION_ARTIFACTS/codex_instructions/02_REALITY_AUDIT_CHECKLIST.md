## Reality Audit Checklist

1. Identify existing artefact models (intent, risk_decision, execution_result).
2. Identify where artefacts are written (DB tables, jsonl logs).
3. Confirm that:
   - No-trade decisions emit artefacts
   - Rejections emit artefacts
   - Execution outcomes emit artefacts
4. Confirm artefacts include references:
   - strategy id + version
   - snapshot ids
   - risk decision ids

Write an audit summary and gaps.