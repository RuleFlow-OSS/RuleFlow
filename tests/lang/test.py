from src.lang import FlowLang

if __name__ == "__main__":
    import psutil
    import os
    import gc
    import timeit


    def get_mem():
        """Returns current resident set size in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024


    gc.collect()
    mem_start = get_mem()

    # Run Simulation
    code = """
    // @mem(TrieVec);
    @init("AB");
    ABA -> AAB;
    A -> ABA;

    // ==== 4-D network ====
    // BA -> AB;
    // BC -> ACB;
    // A -> ACB;
    """
    flow = FlowLang(code)
    time = timeit.timeit(lambda: flow.evolve_n(18), number=1)

    mem_end = get_mem()
    print(f"Total Memory of evolution: {mem_end - mem_start:.2f} MB")
    print(f"Total time spent: {time:.2f} seconds")
    #
    print(flow)
    # pprint([r for r in flow.rule_set.rules])  # print the rule objects
    # from core.graph import CausalGraph
    # g = CausalGraph(flow)
    # g.render_in_browser()
