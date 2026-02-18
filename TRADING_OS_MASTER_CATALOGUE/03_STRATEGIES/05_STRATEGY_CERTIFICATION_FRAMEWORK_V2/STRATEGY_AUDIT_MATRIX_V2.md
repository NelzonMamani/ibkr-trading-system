# STRATEGY_AUDIT_MATRIX_V2

For each strategy (P01–P20), verify:

| Section | Control | Required | Status |
|---------|---------|----------|--------|

Sections:

A1 Strategy ID present
A2 Timeframe authority declared
A3 Intrabar doctrine declared

B1 Universe defined
B2 Selection filters declared
B3 Liquidity constraints declared
B4 Session semantics declared
B5 Scanner leakage guard present

C1 Setup families enumerated
C2 Setup ↔ Trigger mapping explicit
C3 Setup timeframe scope defined

D1 Canonical conditions only
D2 Regime permission declared
D3 Time-of-day condition declared

E1 Confirmation IDs enumerated
E2 Required vs optional marked
E3 Spread confirmation present
E4 Liquidity confirmation present
E5 Exhaustion guard present

F1 Trigger doctrine declared
F2 Break-and-hold doctrine present
F3 Retest doctrine present
F4 Anti-fakeout clause present

G1 Order type policy declared
G2 Add-to-winner policy declared
G3 Averaging-down policy declared
G4 Partial policy declared
G5 Intrabar execution model declared (if applicable)

H1 Initial risk model defined
H2 Max R defined
H3 Daily loss cap defined
H4 Position sizing formula defined

I1 Hard stop doctrine defined
I2 Momentum weakness exit defined
I3 Structure failure exit defined

J1 Halt detection guard
J2 Spread blowout guard
J3 Data staleness guard

K1 Data field contract declared
K2 Volume authority defined
K3 Reference price authority defined

L1 Deterministic primitives only
L2 Completeness test exists
L3 No silent defaults

M1 Version tag present
M2 Certification timestamp present

FAIL if any REQUIRED control missing.

END
