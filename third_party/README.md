third_party cleanup note

The original cloned Voyant repositories were moved to:
../lexi-antigo/wave-04-third-party/third_party/voyanttools

Runtime does not depend on these clones; native Voyant suite implementation lives in src/analysis/voyant_suite.py.

To restore: move the folder back preserving relative path.
