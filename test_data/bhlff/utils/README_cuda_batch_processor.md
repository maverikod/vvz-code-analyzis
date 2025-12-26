# CUDA Batch Processor

## Overview

The `CUDABatchProcessor` provides efficient GPU memory utilization by accumulating multiple 7D fields on GPU and processing them in batches, maximizing memory usage up to 80% of available GPU memory. When GPU memory is insufficient, it automatically uses the swap manager for transparent disk-based storage.

## Problem Solved

In Level B tests, individual fields are processed sequentially, leading to low GPU memory utilization (<10%). The batch processor addresses this by:

1. **Accumulating fields**: Multiple fields are kept on GPU (or disk) until batch processing
2. **Batch processing**: Fields are processed simultaneously in batches
3. **Automatic swap**: Large fields are automatically stored on disk when GPU memory is insufficient
4. **Memory optimization**: Uses up to 80% of available GPU memory

## Usage

### Basic Usage

```python
from bhlff.utils.cuda_batch_processor import CUDABatchProcessor
import numpy as np

# Initialize batch processor
processor = CUDABatchProcessor(
    gpu_memory_ratio=0.8,  # Use 80% of GPU memory
    dtype=np.complex128,
    use_swap=True,  # Enable automatic swap
)

# Add fields to batch
field1 = np.random.rand(64, 64, 64, 16, 16, 16, 100).astype(np.complex128)
field2 = np.random.rand(64, 64, 64, 16, 16, 16, 100).astype(np.complex128)

processor.add_field(field1)
processor.add_field(field2)

# Process batch
def operation(fields):
    # Process fields simultaneously on GPU
    results = []
    for field in fields:
        # Your operation here
        result = cp.abs(field)  # Example
        results.append(cp.asnumpy(result))
    return results

results = processor.process_batch(operation)
```

### Automatic Swap

When a field exceeds available GPU memory, it is automatically stored on disk:

```python
# Large field that exceeds GPU memory
large_field = np.random.rand(512, 512, 512, 32, 32, 32, 64).astype(np.complex128)

# Automatically uses swap if needed
processor.add_field(large_field)

# Field is loaded to GPU on-demand during batch processing
results = processor.process_batch(operation)
```

### Memory Usage Statistics

```python
# Get memory usage statistics
stats = processor.get_memory_usage()
print(f"GPU memory utilization: {stats['memory_utilization']:.2f}%")
print(f"Fields on GPU: {stats['fields_memory_gb']:.2f}GB")
print(f"Fields on disk: {stats['swap_fields_memory_gb']:.2f}GB")
```

## Integration with Level B Analyzers

The `LevelBPowerLawAnalyzer` automatically uses the batch processor when CUDA is available:

```python
from bhlff.models.level_b.stepwise.analyzer import LevelBPowerLawAnalyzer

analyzer = LevelBPowerLawAnalyzer(use_cuda=True)

# Batch processor is automatically initialized
# Fields are processed efficiently with optimal GPU memory usage
result = analyzer.analyze_power_law_tail(field, beta, center)
```

## Configuration

### Environment Variables

- `BHLFF_SWAP_THRESHOLD_GB`: Swap threshold in GB (default: 80% of GPU memory)
- `BHLFF_DISABLE_CUDA`: Disable CUDA (set to "1")

### Parameters

- `gpu_memory_ratio` (float): Target GPU memory utilization (0-1, default: 0.8)
- `dtype` (type): Data type for fields (default: np.complex128)
- `overhead_factor` (float): Memory overhead factor for intermediate operations (default: 4.0)
- `use_swap` (bool): Enable automatic swap (default: True)

## Performance Benefits

- **GPU memory utilization**: Increases from <10% to up to 80%
- **Batch processing**: Multiple fields processed simultaneously
- **Automatic swap**: Transparent disk-based storage for large fields
- **Vectorized operations**: Efficient GPU operations on batches

## Technical Details

### Memory Management

- Fields are kept on GPU until batch processing
- Large fields are automatically stored on disk via swap manager
- Swap fields are loaded to GPU on-demand during batch processing
- Memory is freed after batch processing

### Batch Size Calculation

The maximum batch size is calculated based on:
- Field size (elements × dtype size)
- Available GPU memory (80% of free memory)
- Overhead factor (4.0 for FFT and reductions)

### Swap Integration

The batch processor integrates with the swap manager:
- Automatically detects when fields exceed GPU memory
- Creates swap arrays using `SwapManager.create_swap_array()`
- Loads swap fields to GPU on-demand during batch processing
- Cleans up swap files after processing

