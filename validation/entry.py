"""Start an editable checkout without importing evaluator code into that process."""
import os
import sys
sys.path.insert(0, os.path.join(os.environ["TG_SOURCE"], "src"))
from truegate.cli import main
raise SystemExit(main())

