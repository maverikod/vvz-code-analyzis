"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA batch processor for efficient GPU memory utilization with automatic swap.

This module provides batch processing utilities for 7D phase field calculations,
accumulating multiple fields on GPU and processing them in batches to maximize
GPU memory utilization up to 80% of available memory. Automatically switches
to disk-based swap when GPU memory is insufficient.

Physical Meaning:
    Batch processing enables efficient GPU utilization by accumulating multiple
    7D fields on GPU and processing them together, maximizing memory usage and
    computational throughput. This is critical for Level B tests where individual
    fields are processed sequentially, leading to low GPU memory utilization.
    When GPU memory is insufficient, automatically uses swap manager for
    transparent disk-based storage.

Theoretical Background:
    For 7D phase field calculations in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, batch processing
    allows processing multiple fields simultaneously, improving GPU utilization
    from <10% to up to 80% of available memory. Swap manager provides
    transparent fallback to disk when memory limits are exceeded.

Example:
    >>> from bhlff.utils.cuda_batch_processor import CUDABatchProcessor
    >>> processor = CUDABatchProcessor(gpu_memory_ratio=0.8)
    >>> processor.add_field(field1)
    >>> processor.add_field(field2)
    >>> results = processor.process_batch(operation_func)
"""

import logging
from typing import List, Callable, Any, Optional, Tuple, Union
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class CUDABatchProcessor:
    """
    CUDA batch processor for efficient GPU memory utilization.

    Physical Meaning:
        Accumulates multiple 7D fields on GPU and processes them in batches,
        maximizing GPU memory utilization up to 80% of available memory.
        This addresses the issue where individual fields are processed
        sequentially, leading to low GPU memory usage (<10%).

    Mathematical Foundation:
        For batch of N fields with shapes (N₀, N₁, ..., N₆):
        - Total memory: N × size(field) × dtype_size
        - Batch processing: process up to M fields simultaneously where
          M × size(field) × overhead_factor ≤ 0.8 × GPU_memory
        - Overhead factor: ~3-5x for FFT and intermediate operations

    Attributes:
        gpu_memory_ratio (float): Target GPU memory utilization (0-1).
        fields_gpu (List[cp.ndarray]): Accumulated fields on GPU.
        max_batch_size (int): Maximum number of fields per batch.
    """

    def __init__(
        self,
        gpu_memory_ratio: float = 0.8,
        dtype: type = np.complex128,
        overhead_factor: float = 4.0,
        use_swap: bool = True,
    ):
        """
        Initialize CUDA batch processor.

        Physical Meaning:
            Sets up batch processor with target GPU memory utilization ratio
            and overhead factor for intermediate operations. Automatically
            integrates with swap manager for transparent disk-based storage
            when GPU memory is insufficient.

        Args:
            gpu_memory_ratio (float): Target GPU memory utilization (0-1).
                Default: 0.8 (80% of available GPU memory).
            dtype (type): Data type for fields (default: np.complex128).
            overhead_factor (float): Memory overhead factor for intermediate
                operations (default: 4.0 for FFT and reductions).
            use_swap (bool): Whether to use swap manager for automatic
                disk-based storage when GPU memory is insufficient (default: True).
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA not available. CUDABatchProcessor requires GPU acceleration."
            )

        self.gpu_memory_ratio = gpu_memory_ratio
        self.dtype = dtype
        self.overhead_factor = overhead_factor
        self.use_swap = use_swap
        self.fields_gpu: List[Union["cp.ndarray", np.ndarray]] = []
        self.fields_swap: List[np.memmap] = []  # Fields stored on disk
        self.max_batch_size: Optional[int] = None
        self.logger = logging.getLogger(__name__)

        # Initialize swap manager if needed
        if self.use_swap:
            try:
                from bhlff.core.fft.unified.swap_manager import get_swap_manager

                self.swap_manager = get_swap_manager()
            except ImportError:
                self.logger.warning(
                    "Swap manager not available, disabling swap functionality"
                )
                self.use_swap = False
                self.swap_manager = None
        else:
            self.swap_manager = None

        # Get GPU memory info
        self._update_memory_info()

    def _update_memory_info(self) -> None:
        """
        Update GPU memory information.

        Physical Meaning:
            Queries GPU for current memory status and calculates maximum
            batch size based on available memory and target utilization ratio.
        """
        if not CUDA_AVAILABLE:
            return

        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            self.free_memory_bytes = mem_info[0]
            self.total_memory_bytes = mem_info[1]
            # Use TOTAL memory (not free) for optimal utilization
            # 80% of total memory as base, with 20% reserve covering minor overflows
            self.available_memory_bytes = int(
                self.total_memory_bytes * self.gpu_memory_ratio
            )

            self.logger.debug(
                f"GPU memory: {self.free_memory_bytes/1e9:.2f}GB free, "
                f"{self.total_memory_bytes/1e9:.2f}GB total, "
                f"{self.available_memory_bytes/1e9:.2f}GB available (80%)"
            )
        except Exception as e:
            self.logger.warning(f"Failed to get GPU memory info: {e}")
            self.free_memory_bytes = 0
            self.total_memory_bytes = 0
            self.available_memory_bytes = 0

    def add_field(self, field: np.ndarray) -> None:
        """
        Add field to batch queue with automatic swap support.

        Physical Meaning:
            Transfers field to GPU and adds it to the batch queue for
            later batch processing. If GPU memory is insufficient, automatically
            uses swap manager to store field on disk. Fields are kept on GPU
            (or disk) until batch processing is triggered.

        Args:
            field (np.ndarray): Field array to add (will be transferred to GPU
                or stored on disk if memory is insufficient).
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available")

        # Check if field should use swap (based on GPU memory)
        field_size_gb = field.nbytes / 1e9
        should_use_swap = False

        if self.use_swap and self.swap_manager is not None:
            # Check if field size exceeds available GPU memory
            if self.available_memory_bytes > 0:
                field_memory_with_overhead = field.nbytes * self.overhead_factor
                if field_memory_with_overhead > self.available_memory_bytes:
                    should_use_swap = True
                    self.logger.info(
                        f"Field size {field_size_gb:.3f}GB exceeds available GPU memory "
                        f"({self.available_memory_bytes/1e9:.3f}GB), using swap"
                    )

        if should_use_swap:
            # Store field on disk using swap manager
            swap_id = f"batch_field_{len(self.fields_swap)}"
            swap_array = self.swap_manager.create_swap_array(
                shape=field.shape,
                dtype=self.dtype,
                array_id=swap_id,
            )
            swap_array[:] = field[:]
            swap_array.flush()

            self.fields_swap.append(swap_array)
            self.fields_gpu.append(None)  # Placeholder for swap field

            self.logger.debug(
                f"Added field to batch (swap): shape={field.shape}, "
                f"swap_id={swap_id}, batch_size={len(self.fields_gpu)}"
            )
        else:
            # Transfer field to GPU
            if isinstance(field, np.ndarray):
                field_gpu = cp.asarray(field, dtype=self.dtype)
            else:
                field_gpu = field

            self.fields_gpu.append(field_gpu)
            self.fields_swap.append(None)  # Placeholder for GPU field

            self.logger.debug(
                f"Added field to batch (GPU): shape={field_gpu.shape}, "
                f"batch_size={len(self.fields_gpu)}"
            )

        # Update max batch size if this is the first field
        if self.max_batch_size is None and len(self.fields_gpu) == 1:
            self._compute_max_batch_size(field.shape)

    def _compute_max_batch_size(self, field_shape: Tuple[int, ...]) -> None:
        """
        Compute maximum batch size based on field shape and GPU memory.

        Physical Meaning:
            Calculates the maximum number of fields that can be processed
            simultaneously based on field size, GPU memory, and overhead
            factor for intermediate operations.

        Args:
            field_shape (Tuple[int, ...]): Shape of a single field.
        """
        if not CUDA_AVAILABLE:
            self.max_batch_size = 1
            return

        # Calculate memory per field (including overhead)
        bytes_per_element = np.dtype(self.dtype).itemsize
        elements_per_field = np.prod(field_shape)
        memory_per_field = elements_per_field * bytes_per_element
        memory_per_field_with_overhead = memory_per_field * self.overhead_factor

        # Calculate max batch size
        if memory_per_field_with_overhead > 0:
            self.max_batch_size = max(
                1,
                int(self.available_memory_bytes / memory_per_field_with_overhead),
            )
        else:
            self.max_batch_size = 1

        self.logger.info(
            f"Max batch size: {self.max_batch_size} fields "
            f"(field_size={memory_per_field/1e9:.2f}GB, "
            f"available={self.available_memory_bytes/1e9:.2f}GB)"
        )

    def process_batch(
        self,
        operation: Callable[[List[Union["cp.ndarray", np.ndarray]]], List[Any]],
        batch_size: Optional[int] = None,
    ) -> List[Any]:
        """
        Process accumulated fields in batches with automatic swap support.

        Physical Meaning:
            Processes accumulated fields in batches, maximizing GPU memory
            utilization. Each batch contains up to max_batch_size fields,
            processed simultaneously on GPU. Fields stored on disk via swap
            are automatically loaded to GPU for processing.

        Mathematical Foundation:
            For batch of N fields, processes in batches of size M:
            - Batch 1: fields[0:M]
            - Batch 2: fields[M:2M]
            - ...
            - Batch K: fields[(K-1)*M:N]
            where M = min(batch_size, max_batch_size)
            Swap fields are loaded to GPU on-demand for processing.

        Args:
            operation (Callable): Operation function that takes a list of
                arrays (GPU or CPU) and returns a list of results.
            batch_size (Optional[int]): Batch size override. If None,
                uses computed max_batch_size.

        Returns:
            List[Any]: List of results from batch processing.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available")

        if len(self.fields_gpu) == 0:
            return []

        # Use provided batch size or computed max
        effective_batch_size = (
            batch_size if batch_size is not None else self.max_batch_size
        )
        if effective_batch_size is None:
            effective_batch_size = 1

        results = []
        num_batches = (len(self.fields_gpu) + effective_batch_size - 1) // effective_batch_size

        self.logger.info(
            f"Processing {len(self.fields_gpu)} fields in {num_batches} batches "
            f"(batch_size={effective_batch_size}, swap_fields={sum(1 for f in self.fields_swap if f is not None)})"
        )

        # Process in batches
        for i in range(0, len(self.fields_gpu), effective_batch_size):
            batch_num = i // effective_batch_size + 1

            # Prepare batch: load swap fields to GPU if needed
            batch_fields = []
            for j in range(i, min(i + effective_batch_size, len(self.fields_gpu))):
                if self.fields_swap[j] is not None:
                    # Load swap field to GPU
                    swap_field = self.fields_swap[j]
                    field_gpu = cp.asarray(swap_field, dtype=self.dtype)
                    batch_fields.append(field_gpu)
                    self.logger.debug(
                        f"Loaded swap field {j} to GPU: shape={field_gpu.shape}"
                    )
                else:
                    # Field already on GPU
                    batch_fields.append(self.fields_gpu[j])

            self.logger.debug(
                f"Processing batch {batch_num}/{num_batches}: "
                f"{len(batch_fields)} fields"
            )

            # Process batch
            batch_results = operation(batch_fields)

            # Convert results to numpy if needed
            if isinstance(batch_results, list):
                results.extend(batch_results)
            else:
                results.append(batch_results)

            # Clean up temporary GPU arrays from swap fields
            for j, field in enumerate(batch_fields):
                if j < len(self.fields_swap) and self.fields_swap[i + j] is not None:
                    if isinstance(field, cp.ndarray):
                        del field

            # Synchronize GPU after each batch
            cp.cuda.Stream.null.synchronize()

        # Clear accumulated fields
        self.clear()

        return results

    def process_single(
        self, field: np.ndarray, operation: Callable[["cp.ndarray"], Any]
    ) -> Any:
        """
        Process single field with automatic batching.

        Physical Meaning:
            Adds field to batch and processes if batch is full, or processes
            immediately if batch is empty. This enables automatic batching
            for sequential field processing.

        Args:
            field (np.ndarray): Field to process.
            operation (Callable): Operation function for single field.

        Returns:
            Any: Result from operation.
        """
        self.add_field(field)

        # Process if batch is full
        if (
            self.max_batch_size is not None
            and len(self.fields_gpu) >= self.max_batch_size
        ):
            return self.process_batch(
                lambda batch: [operation(f) for f in batch]
            )[0]
        else:
            # Process immediately if batch not full and this is last field
            # (for now, just process immediately)
            if len(self.fields_gpu) == 1:
                result = operation(self.fields_gpu[0])
                self.clear()
                return result
            else:
                # Wait for more fields or process when batch is full
                return None

    def clear(self) -> None:
        """
        Clear accumulated fields from GPU and swap.

        Physical Meaning:
            Removes all accumulated fields from GPU memory and disk swap,
            freeing memory and disk space for subsequent operations.
        """
        if CUDA_AVAILABLE:
            for field in self.fields_gpu:
                if field is not None and isinstance(field, cp.ndarray):
                    del field
            cp.get_default_memory_pool().free_all_blocks()

        # Clean up swap fields
        if self.use_swap and self.swap_manager is not None:
            for i, swap_field in enumerate(self.fields_swap):
                if swap_field is not None:
                    swap_id = f"batch_field_{i}"
                    try:
                        self.swap_manager.cleanup(swap_id)
                    except Exception as e:
                        self.logger.warning(f"Failed to cleanup swap field {i}: {e}")

        self.fields_gpu.clear()
        self.fields_swap.clear()
        self.logger.debug("Cleared batch queue (GPU and swap)")

    def get_memory_usage(self) -> dict:
        """
        Get current GPU memory usage statistics.

        Physical Meaning:
            Returns detailed information about GPU memory usage, including
            accumulated fields size and available memory.

        Returns:
            dict: Memory usage statistics.
        """
        if not CUDA_AVAILABLE:
            return {"error": "CUDA not available"}

        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory = mem_info[0]
            total_memory = mem_info[1]
            used_memory = total_memory - free_memory

            # Calculate memory used by accumulated fields (GPU only)
            fields_memory = sum(
                f.nbytes for f in self.fields_gpu if f is not None and isinstance(f, cp.ndarray)
            )

            # Calculate swap fields memory (on disk)
            swap_fields_memory = sum(
                f.nbytes for f in self.fields_swap if f is not None
            )

            return {
                "total_memory_gb": total_memory / 1e9,
                "free_memory_gb": free_memory / 1e9,
                "used_memory_gb": used_memory / 1e9,
                "fields_memory_gb": fields_memory / 1e9,
                "swap_fields_memory_gb": swap_fields_memory / 1e9,
                "num_fields": len(self.fields_gpu),
                "num_swap_fields": sum(1 for f in self.fields_swap if f is not None),
                "max_batch_size": self.max_batch_size,
                "memory_utilization": (used_memory / total_memory) * 100
                if total_memory > 0
                else 0,
            }
        except Exception as e:
            return {"error": str(e)}

