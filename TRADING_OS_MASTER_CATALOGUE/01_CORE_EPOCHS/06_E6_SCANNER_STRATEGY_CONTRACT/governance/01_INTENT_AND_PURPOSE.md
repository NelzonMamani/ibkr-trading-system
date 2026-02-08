## Intent

E6 exists to guarantee that:
- The scanner never decides trades
- The scanner never embeds strategy logic
- Strategies receive a stable, auditable fact surface
- Empty outputs are valid and correct behavior
- Strategy evolution does not require scanner refactors

This epoch locks the scanner as a **pure fact producer**.
