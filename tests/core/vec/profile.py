import timeit
import psutil
import os
import gc
from src.core.vec import TrieVec, Vec, Cell


def get_mem():
    """Returns current resident set size in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def profile_vec_efficiency(v: type[Vec | TrieVec]):
    print(f"=== {v.__name__} Performance & Space Profiler ===")

    # Configuration
    N = 100_000  # Number of cells
    BRANCHES = 500
    DATA = [Cell(str(i % 10)) for i in range(N)]
    PATTERN = b"ABCDE"



    # 1. Memory Usage: Structural Sharing
    print(f"\n[1] Memory Scaling: {BRANCHES} Branches of {N} Cells")
    gc.collect()
    mem_start = get_mem()

    # Create initial vec
    base_vec = v(DATA)
    branches = []
    for i in range(BRANCHES):
        new_branch = base_vec.branch()
        # Perform a small point update to ensure it's a unique state
        new_branch[i % N] = Cell("X")
        branches.append(new_branch)

    mem_end = get_mem()
    print(f"Total Memory for {BRANCHES} branches: {mem_end - mem_start:.2f} MB")
    print(f"Avg overhead per branch: {(mem_end - mem_start) / BRANCHES * 1024:.2f} KB")
    # Reference: Standard list would take ~N * BRANCHES * pointer_size



    # 2. Edit Efficiency: Point Update vs Structural
    print(f"\n[2] Edit Latency ({N} items)")

    def point_update():
        # Triggers Evolver
        base_vec[500] = Cell("Z")

    def structural_update():
        # Triggers PVector slice/sandwich
        base_vec[500:501] = (Cell("Y"), Cell("Y"))

    t_point = timeit.timeit(point_update, number=1000)
    t_struct = timeit.timeit(structural_update, number=1000)

    print(f"Point Update (1000 ops): {t_point:.4f}s")
    print(f"Structural Update (1000 ops): {t_struct:.4f}s")



    # 3. Search Efficiency: Regex on search_buffer
    print(f"\n[3] Find Performance (Regex on {N} cells)")

    # Ensure pattern exists
    base_vec[1000:1005] = [Cell(c) for c in 'ABCDE']

    def run_find():
        return list(base_vec.finditer(PATTERN))

    t_find = timeit.timeit(run_find, number=100)
    print(f"Regex Find (100 runs): {t_find:.4f}s")


if __name__ == "__main__":
    # profile_vec_efficiency(Vec)
    profile_vec_efficiency(Vec)
