# MANDATORY VERIFICATION COMMANDS

Run from repo root.

1) Compile
python -m compileall -q src

2) Unit tests (if present)
pytest -q

3) Smoke run (SIM)
python -m src.main --mode SIM --cycles 1 --strategy ross_momentum

4) Smoke run (PAPER)
python -m src.main --mode PAPER --cycles 1 --strategy ross_momentum

5) Live read-only observation
python -m src.main --mode READ_ONLY --cycles 1 --strategy ross_momentum

6) Provenance checks (new verification script if needed)
python -m verification_scripts.verify_provenance_ledger --mode SIM
python -m verification_scripts.verify_provenance_ledger --mode PAPER
python -m verification_scripts.verify_provenance_ledger --mode READ_ONLY

Expected: all modes produce a ledger record set; no missing provenance linkages.

END
