# FieldArray - Unified Array Interface

## Overview

`FieldArray` provides a unified interface for large 7D phase field arrays that can be stored in memory or on disk transparently. This allows seamless integration between solvers, generators, and analyzers without worrying about memory constraints.

## Usage

### Basic Usage

```python
from bhlff.core.arrays import FieldArray
import numpy as np

# Create field array (automatically uses swap if > 10GB)
field = FieldArray(shape=(128, 128, 128, 8, 8, 8, 16), dtype=np.complex128)

# Access like normal numpy array
field[0, 0, 0, 0, 0, 0, 0] = 1.0

# Operations work transparently
result = field * 2.0  # Returns FieldArray
```

### With Generators

```python
from bhlff.core.sources.bvp_source_generators import BVPSourceGenerators

generators = BVPSourceGenerators(domain, config)
source = generators.generate_gaussian_source()  # Returns FieldArray

# Source may be swapped to disk automatically if large
print(f"Source swapped: {source.is_swapped}")
```

### With Solvers

```python
from bhlff.core.fft.fft_solver_7d_basic import FFTSolver7DBasic

solver = FFTSolver7DBasic(domain, parameters)
solution = solver.solve_stationary(source)  # Returns FieldArray

# Solution may be swapped to disk automatically
print(f"Solution swapped: {solution.is_swapped}")
```

### Manual Swap Control

```python
# Convert to swap explicitly
swapped = field.to_swap()

# Convert back to memory
in_memory = swapped.to_memory()

# Save to pickle for fast loading
pickle_file = field.save_pickle()

# Load from pickle
loaded = FieldArray.load_pickle(pickle_file)
```

## Features

- **Transparent swap**: Automatically uses disk storage for arrays exceeding threshold
- **Configurable threshold**: Set via `BHLFF_SWAP_THRESHOLD_GB` environment variable (default: 0.01 GB for testing)
- **NumPy compatibility**: Works like regular numpy arrays
- **Operator support**: All arithmetic operations supported
- **Pickle support**: Fast save/load with pickle
- **Memory management**: Automatic cleanup of swap files

## Configuration

### Swap Threshold

The swap threshold controls when arrays are automatically moved to disk storage:

```python
# Set via environment variable (in GB)
import os
os.environ["BHLFF_SWAP_THRESHOLD_GB"] = "0.01"  # 10 MB for testing

# Or set per-array
field = FieldArray(shape=(100, 100, 100), swap_threshold_gb=0.001)  # 1 MB
```

**Production mode**: By default, swap threshold is automatically set to **80% of available GPU memory** for optimal performance. This ensures that arrays larger than 80% of GPU memory are automatically swapped to disk.

**Testing mode**: Set `BHLFF_SWAP_THRESHOLD_GB` environment variable to a small value (e.g., 0.01 GB) for testing swap functionality on smaller arrays.

## Integration

All generators, solvers, and analyzers now return and accept `FieldArray` objects, providing seamless integration with automatic memory management.

