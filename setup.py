from __future__ import annotations

import os
from setuptools import find_packages, setup

profile = os.getenv("CG_BUILD_PROFILE", "full").strip().lower()
exclude = ["tests*"]

# Core profile omits optional add-on implementation modules from the wheel.
if profile == "core":
    exclude.extend([
        "cg.addons",
        "cg.addons.*",
    ])

setup(
    package_dir={"": "core"},
    packages=find_packages(where="core", include=["cg*"], exclude=exclude),
)
