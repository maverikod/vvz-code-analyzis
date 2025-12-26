"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Mathematical mixin for FieldArray operations.

Provides NumPy interoperability, indexing, and arithmetic helpers
shared by FieldArray while keeping the main class file compact and
within the 400-line requirement.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class FieldArrayMathMixin:
    """
    Add NumPy protocol and arithmetic operators to FieldArray.
    """

    @property
    def array(self) -> Any:
        """Expose underlying storage (np.ndarray or np.memmap)."""
        return self._array

    def __array__(self) -> np.ndarray:
        """NumPy array interface."""
        return self._array

    def __getitem__(self, key):
        """Array indexing."""
        return self._array[key]

    def __setitem__(self, key, value):
        """Array assignment."""
        self._array[key] = value
        if isinstance(self._array, np.memmap):
            self._array.flush()

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """NumPy ufunc support."""
        arrays = []
        for inp in inputs:
            if isinstance(inp, FieldArrayMathMixin):
                arrays.append(inp._array)
            else:
                arrays.append(inp)
        result = getattr(ufunc, method)(*arrays, **kwargs)
        if isinstance(result, np.ndarray):
            from .field_array import FieldArray  # local import to avoid cycle

            return FieldArray(
                array=result,
                swap_threshold_gb=self._swap_threshold_gb,
            )
        return result

    def __mul__(self, other):
        """Multiplication operator."""
        if isinstance(other, FieldArrayMathMixin):
            result = self._array * other._array
        else:
            result = self._array * other
        from .field_array import FieldArray

        return FieldArray(
            array=result,
            swap_threshold_gb=self._swap_threshold_gb,
        )

    def __rmul__(self, other):
        """Right multiplication operator."""
        result = other * self._array
        from .field_array import FieldArray

        return FieldArray(
            array=result,
            swap_threshold_gb=self._swap_threshold_gb,
        )

    def __add__(self, other):
        """Addition operator."""
        if isinstance(other, FieldArrayMathMixin):
            result = self._array + other._array
        else:
            result = self._array + other
        from .field_array import FieldArray

        return FieldArray(
            array=result,
            swap_threshold_gb=self._swap_threshold_gb,
        )

    def __sub__(self, other):
        """Subtraction operator."""
        if isinstance(other, FieldArrayMathMixin):
            result = self._array - other._array
        else:
            result = self._array - other
        from .field_array import FieldArray

        return FieldArray(
            array=result,
            swap_threshold_gb=self._swap_threshold_gb,
        )

    def __truediv__(self, other):
        """Division operator."""
        if isinstance(other, FieldArrayMathMixin):
            result = self._array / other._array
        else:
            result = self._array / other
        from .field_array import FieldArray

        return FieldArray(
            array=result,
            swap_threshold_gb=self._swap_threshold_gb,
        )

