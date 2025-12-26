"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-based morphological operations for quench detection.
"""

import numpy as np
from typing import Dict

try:
    import cupy as cp
except ImportError:
    cp = None


class QuenchMorphologyCUDA:
    """
    CUDA-based morphological operations for quench detection.

    Physical Meaning:
        Applies morphological operations on GPU for efficient
        noise filtering and connected component analysis.
    """

    def apply_morphological_operations_cuda(
        self, mask_gpu, cuda_available: bool, cpu_processor
    ):
        """
        Apply morphological operations using CUDA acceleration.

        Physical Meaning:
            Applies binary morphological operations on GPU for
            efficient noise filtering in 7D space-time.

        Args:
            mask_gpu: GPU array of quench regions.
            cuda_available (bool): Whether CUDA is available.
            cpu_processor: CPU processor for fallback.

        Returns:
            CuPy array: Filtered binary mask (kept on GPU).
        """
        if not cuda_available:
            # Fallback to CPU if CUDA not available
            mask_cpu = cp.asnumpy(mask_gpu) if hasattr(mask_gpu, "get") else mask_gpu
            return cp.asarray(
                cpu_processor.apply_morphological_operations(mask_cpu, False)
            )

        # Ensure mask_gpu is CuPy array
        if not hasattr(mask_gpu, "get"):
            mask_gpu = cp.asarray(mask_gpu)

        # Define structuring element for 7D operations on GPU
        # Use smaller structure for small arrays
        structure_shape = tuple(min(3, dim) for dim in mask_gpu.shape)
        structure = cp.ones(structure_shape, dtype=cp.bool_)

        # Apply binary opening to remove small noise
        filtered_mask = self._binary_opening_cuda(mask_gpu, structure)

        # Apply binary closing to fill small gaps
        filtered_mask = self._binary_closing_cuda(filtered_mask, structure)

        return filtered_mask

    def find_connected_components_cuda(
        self, mask_gpu, cuda_available: bool, cpu_processor
    ) -> Dict[int, np.ndarray]:
        """
        Find connected components using CUDA acceleration.

        Physical Meaning:
            Groups nearby quench events into connected components
            using GPU acceleration for efficient processing.

        Args:
            mask_gpu: GPU array of quench regions.
            cuda_available (bool): Whether CUDA is available.
            cpu_processor: CPU processor for fallback.

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component (transferred to CPU).
        """
        if not cuda_available:
            # Fallback to CPU if CUDA not available
            mask_cpu = cp.asnumpy(mask_gpu) if hasattr(mask_gpu, "get") else mask_gpu
            return cpu_processor.find_connected_components(mask_cpu, False)

        # Ensure mask_gpu is CuPy array
        if not hasattr(mask_gpu, "get"):
            mask_gpu = cp.asarray(mask_gpu)

        # Use GPU-based connected component labeling
        labeled_mask = self._label_components_cuda(mask_gpu)

        # Extract individual components
        components = {}
        num_components = int(cp.max(labeled_mask))

        for component_id in range(1, num_components + 1):
            component_mask = labeled_mask == component_id
            components[component_id] = cp.asnumpy(component_mask)

        return components

    def _binary_opening_cuda(self, mask_gpu, structure):
        """Apply binary opening using CUDA with proper vectorization."""
        # Erosion followed by dilation
        eroded = self._erosion_cuda_vectorized(mask_gpu, structure)
        return self._dilation_cuda_vectorized(eroded, structure)

    def _binary_closing_cuda(self, mask_gpu, structure):
        """Apply binary closing using CUDA with proper vectorization."""
        # Dilation followed by erosion
        dilated = self._dilation_cuda_vectorized(mask_gpu, structure)
        return self._erosion_cuda_vectorized(dilated, structure)

    def _erosion_cuda_vectorized(self, mask_gpu, structure):
        """
        Vectorized erosion using CUDA with proper 7D neighborhood operations.

        Physical Meaning:
            Erosion removes pixels that don't have all neighbors in the
            structuring element set to True, effectively shrinking regions
            and removing small noise components.

        Mathematical Foundation:
            Erosion: E(A) = {x | B_x ⊆ A}, where B is the structuring element
            and B_x is B translated to position x. A pixel is kept only if
            all positions covered by the structuring element are True in A.

        Args:
            mask_gpu: Binary mask on GPU.
            structure: Structuring element on GPU.

        Returns:
            CuPy array: Eroded binary mask.
        """
        # Convert to float for convolution operations
        mask_float = mask_gpu.astype(cp.float32)
        structure_float = structure.astype(cp.float32)

        # Compute convolution with structure (sum of overlapping True values)
        convolved = self._convolve_7d_cuda(mask_float, structure_float)

        # Erosion: pixel is True only if all structure elements are True
        # This means convolved value equals the number of True elements in structure
        structure_size = cp.sum(structure_float > 0)
        threshold = structure_size - 1e-6  # Small tolerance for floating point

        result = convolved >= threshold

        return result.astype(cp.bool_)

    def _dilation_cuda_vectorized(self, mask_gpu, structure):
        """
        Vectorized dilation using CUDA with proper 7D neighborhood operations.

        Physical Meaning:
            Dilation expands regions by adding pixels where at least one
            neighbor in the structuring element is True, effectively filling
            small gaps and expanding quench regions.

        Mathematical Foundation:
            Dilation: D(A) = {x | B_x ∩ A ≠ ∅}, where B is the structuring
            element and B_x is B translated to position x. A pixel is set
            to True if at least one position covered by the structuring
            element is True in A.

        Args:
            mask_gpu: Binary mask on GPU.
            structure: Structuring element on GPU.

        Returns:
            CuPy array: Dilated binary mask.
        """
        # Convert to float for convolution operations
        mask_float = mask_gpu.astype(cp.float32)
        structure_float = structure.astype(cp.float32)

        # Compute convolution with structure (sum of overlapping True values)
        convolved = self._convolve_7d_cuda(mask_float, structure_float)

        # Dilation: pixel is True if any structure element is True
        # This means convolved value is greater than zero
        threshold = 1e-6  # Small tolerance for floating point

        result = convolved > threshold

        return result.astype(cp.bool_)

    def _label_components_cuda(self, mask_gpu):
        """
        Label connected components using CUDA with proper flood-fill algorithm.

        Physical Meaning:
            Identifies connected regions in the quench mask by grouping
            spatially/phase/temporally adjacent quench events into coherent
            components representing individual quench structures.

        Mathematical Foundation:
            Uses flood-fill algorithm to identify all points reachable from
            a seed point through a path of connected True pixels, where
            connectivity is defined by 7D neighborhood (3^7 - 1 neighbors).

        Args:
            mask_gpu: Binary mask on GPU.

        Returns:
            CuPy array: Labeled mask with component IDs.
        """
        labeled = cp.zeros_like(mask_gpu, dtype=cp.int32)
        component_id = 0

        # Find all True points using vectorized operations
        true_points = cp.where(mask_gpu)
        if len(true_points[0]) == 0:
            return labeled

        # Transfer to CPU for flood-fill (more efficient for small arrays)
        # For large arrays, we could use CUDA kernels, but for now use CPU
        # flood-fill which is still efficient for typical quench detection
        mask_cpu = cp.asnumpy(mask_gpu)
        labeled_cpu = cp.asnumpy(labeled)

        # Use proper flood-fill for each unlabeled component
        visited = cp.zeros_like(mask_gpu, dtype=cp.bool_)
        visited_cpu = cp.asnumpy(visited)

        # Get all True points as list
        true_points_list = list(zip(*[cp.asnumpy(coord) for coord in true_points]))

        for point in true_points_list:
            if not visited_cpu[point]:
                component_id += 1
                # Flood-fill from this point
                self._flood_fill_cuda_impl(
                    mask_cpu, visited_cpu, labeled_cpu, point, component_id
                )

        return cp.asarray(labeled_cpu)

    def _flood_fill_cuda_impl(self, mask, visited, labeled, start_point, component_id):
        """
        Flood-fill algorithm implementation for connected component labeling.

        Physical Meaning:
            Recursively fills connected quench regions starting from a seed
            point, identifying all pixels reachable through a path of
            connected True pixels in 7D space-time.

        Args:
            mask: Binary mask (numpy array).
            visited: Visited points mask (numpy array).
            labeled: Labeled mask (numpy array).
            start_point: Starting point tuple for flood-fill.
            component_id: Component ID to assign.
        """
        stack = [start_point]

        while stack:
            point = stack.pop()

            if visited[point]:
                continue

            visited[point] = True
            labeled[point] = component_id

            # Check 7D neighbors (3^7 - 1 = 2186 neighbors)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for dz in [-1, 0, 1]:
                        for dphi1 in [-1, 0, 1]:
                            for dphi2 in [-1, 0, 1]:
                                for dphi3 in [-1, 0, 1]:
                                    for dt in [-1, 0, 1]:
                                        # Skip center point
                                        if (
                                            dx
                                            == dy
                                            == dz
                                            == dphi1
                                            == dphi2
                                            == dphi3
                                            == dt
                                            == 0
                                        ):
                                            continue

                                        neighbor = (
                                            point[0] + dx,
                                            point[1] + dy,
                                            point[2] + dz,
                                            point[3] + dphi1,
                                            point[4] + dphi2,
                                            point[5] + dphi3,
                                            point[6] + dt,
                                        )

                                        # Check bounds
                                        if (
                                            0 <= neighbor[0] < mask.shape[0]
                                            and 0 <= neighbor[1] < mask.shape[1]
                                            and 0 <= neighbor[2] < mask.shape[2]
                                            and 0 <= neighbor[3] < mask.shape[3]
                                            and 0 <= neighbor[4] < mask.shape[4]
                                            and 0 <= neighbor[5] < mask.shape[5]
                                            and 0 <= neighbor[6] < mask.shape[6]
                                        ):
                                            if mask[neighbor] and not visited[neighbor]:
                                                stack.append(neighbor)

    def _convolve_7d_cuda(self, mask_float, structure_float):
        """
        Compute 7D convolution using CUDA with block-based processing.

        Physical Meaning:
            Applies the structuring element to each pixel in the mask,
            computing the weighted sum of neighbors for morphological
            operations.

        Mathematical Foundation:
            Convolution: (f * g)(x) = Σ f(y) * g(x - y) over all y,
            where f is the mask and g is the structuring element.

        Args:
            mask_float: Input mask as float32 array on GPU.
            structure_float: Structuring element as float32 array on GPU.

        Returns:
            CuPy array: Convolved result.
        """
        # For 7D convolution, we use a block-based approach
        # Compute convolution using element-wise operations and shifts
        result = cp.zeros_like(mask_float)

        # Get structure center
        structure_center = tuple(s // 2 for s in structure_float.shape)

        # Iterate over all positions in structure
        structure_indices = cp.ndindex(structure_float.shape)
        for idx in structure_indices:
            weight = structure_float[idx]
            if weight == 0:
                continue

            # Compute offset from center
            offset = tuple(i - c for i, c in zip(idx, structure_center))

            # Create shifted mask
            shifted_mask = self._shift_7d_cuda(mask_float, offset)

            # Accumulate weighted contribution
            result += weight * shifted_mask

        return result

    def _shift_7d_cuda(self, array, offset):
        """
        Shift array by offset in 7D space using CUDA.

        Physical Meaning:
            Translates the array by the specified offset, padding with
            zeros at boundaries for convolution operations.

        Args:
            array: Input array on GPU.
            offset: Tuple of 7 offsets (one per dimension).

        Returns:
            CuPy array: Shifted array.
        """
        result = cp.zeros_like(array)

        # Compute source and destination slices
        src_slices = []
        dst_slices = []

        for dim in range(7):
            off = offset[dim]
            size = array.shape[dim]

            if off > 0:
                # Shift right: take from left, place on right
                src_slices.append(slice(0, size - off))
                dst_slices.append(slice(off, size))
            elif off < 0:
                # Shift left: take from right, place on left
                src_slices.append(slice(-off, size))
                dst_slices.append(slice(0, size + off))
            else:
                # No shift
                src_slices.append(slice(None))
                dst_slices.append(slice(None))

        # Copy shifted region
        result[tuple(dst_slices)] = array[tuple(src_slices)]

        return result
