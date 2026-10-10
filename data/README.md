# Sample data

**Everything in `synthetic/` is synthetic.** It is written by
`scripts/generate_sample_data.py` from invented values. It is not an export
from any SAP system and contains no real company, vendor or material data.
Vendor names are made up; any resemblance to a real company is coincidental.
Tax numbers start with `SYN` so they cannot be mistaken for real ones.

| File | Contents |
|------|----------|
| `synthetic/materials.csv` | Messy material master sample |
| `synthetic/vendors.csv` | Messy vendor master sample |
| `synthetic/manifest.json` | Which defects the generator injected, and which rows it expects the cleaner to reject |

Regenerate with:

```
python scripts/generate_sample_data.py
```

The seed is fixed, so the files come out the same every time.

Do not put real exports in this repository. `data/real/` is git-ignored for
local experiments.
