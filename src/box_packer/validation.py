"""Validation rules shared by every input boundary (catalogue file, HTTP requests)."""

from typing import Annotated

from pydantic import Field

# Strict mode rejects booleans (bool is a subclass of int in Python) and numeric
# strings like "10"; allow_inf_nan rejects NaN/Infinity, which Python's json
# module accepts as literals. Integers are still accepted and coerced to float.
PositiveFinite = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
